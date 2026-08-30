import csv
import io
import json
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

from database.connection import get_connection
from models.audit_log import AuditLog
from models.fiscal_period import FiscalPeriod
from models.journal_entry import JournalEntry, JournalEntryLine
from models.payroll import PayRun, PayStub
from money import to_cents, to_dollars


CANONICAL_PAYROLL_HEADERS = [
    "employee_name", "department", "pay_period_start", "pay_period_end",
    "pay_date", "gross_pay", "deductions_json", "net_pay",
]


def create_pay_run(client_id: int, period_start: date, period_end: date,
                   pay_date: date, _conn=None) -> PayRun:
    if period_start > period_end:
        raise ValueError("Pay period start must be on or before its end.")
    owns_conn = _conn is None
    conn = _conn or get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pay_runs "
            "(client_id, pay_period_start, pay_period_end, pay_date, status) "
            "VALUES (?, ?, ?, ?, 'draft')",
            (client_id, period_start.isoformat(), period_end.isoformat(), pay_date.isoformat()),
        )
        pay_run_id = cursor.lastrowid
        AuditLog.write(
            cursor, client_id, "pay_runs", pay_run_id, "INSERT",
            new_values={"pay_period_start": period_start.isoformat(),
                        "pay_period_end": period_end.isoformat(),
                        "pay_date": pay_date.isoformat(), "status": "draft"},
        )
        if owns_conn:
            conn.commit()
    except Exception:
        if owns_conn:
            conn.rollback()
        raise
    finally:
        if owns_conn:
            conn.close()
    if owns_conn:
        return PayRun.get_by_id(pay_run_id)
    return PayRun(pay_run_id, client_id, period_start, period_end, pay_date)


def _validated_deductions(deductions: List[dict]) -> List[dict]:
    normalized = []
    for deduction in deductions:
        if set(deduction) != {"label", "amount_cents"}:
            raise ValueError("Each deduction requires a label and amount_cents.")
        label = str(deduction["label"]).strip()
        amount = deduction["amount_cents"]
        if not label:
            raise ValueError("Each deduction requires a label.")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ValueError("Deduction amounts must be non-negative integer cents.")
        normalized.append({"label": label, "amount_cents": amount})
    return normalized


def add_pay_stub(pay_run_id: int, employee_id: int, gross_pay_cents: int,
                 deductions: List[dict], net_pay_cents: int, _conn=None) -> PayStub:
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
           for value in (gross_pay_cents, net_pay_cents)):
        raise ValueError("Gross and net pay must be non-negative integer cents.")
    deductions = _validated_deductions(deductions)
    if gross_pay_cents - sum(item["amount_cents"] for item in deductions) != net_pay_cents:
        raise ValueError("Gross pay minus deductions must equal net pay.")

    owns_conn = _conn is None
    conn = _conn or get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pay_runs WHERE id = ?", (pay_run_id,))
        pay_run = cursor.fetchone()
        if not pay_run:
            raise ValueError("Pay run not found.")
        if pay_run["status"] != "draft":
            raise ValueError("Pay stubs can only be added to a draft pay run.")
        cursor.execute(
            "SELECT 1 FROM employees WHERE id = ? AND client_id = ?",
            (employee_id, pay_run["client_id"]),
        )
        if not cursor.fetchone():
            raise ValueError("Employee not found for this pay run's client.")
        encoded = json.dumps(deductions, separators=(",", ":"), sort_keys=True)
        cursor.execute(
            "INSERT INTO pay_stubs "
            "(pay_run_id, employee_id, gross_pay_cents, deductions, net_pay_cents) "
            "VALUES (?, ?, ?, ?, ?)",
            (pay_run_id, employee_id, gross_pay_cents, encoded, net_pay_cents),
        )
        stub_id = cursor.lastrowid
        AuditLog.write(
            cursor, pay_run["client_id"], "pay_stubs", stub_id, "INSERT",
            new_values={"pay_run_id": pay_run_id, "employee_id": employee_id,
                        "gross_pay_cents": gross_pay_cents, "deductions": deductions,
                        "net_pay_cents": net_pay_cents},
        )
        if owns_conn:
            conn.commit()
    except Exception:
        if owns_conn:
            conn.rollback()
        raise
    finally:
        if owns_conn:
            conn.close()
    return PayStub(stub_id, pay_run_id, employee_id, gross_pay_cents,
                   deductions, net_pay_cents)


def _assert_accounts(cursor, client_id: int, account_ids, allowed_types, label: str):
    account_ids = set(account_ids)
    if not account_ids:
        return
    placeholders = ",".join("?" for _ in account_ids)
    cursor.execute(
        f"SELECT id, type FROM accounts WHERE client_id = ? "
        f"AND id IN ({placeholders})", [client_id, *account_ids],
    )
    rows = cursor.fetchall()
    if {row["id"] for row in rows} != account_ids or any(
        row["type"] not in allowed_types for row in rows
    ):
        expected = " or ".join(sorted(allowed_types))
        raise ValueError(f"{label} accounts must be {expected} accounts for this client.")


def post_pay_run(pay_run_id: int, wage_accounts: Dict[str, int],
                 default_wages_account_id: Optional[int], cash_account_id: int,
                 deduction_accounts: Dict[str, int]) -> JournalEntry:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pay_runs WHERE id = ?", (pay_run_id,))
        pay_run = cursor.fetchone()
        if not pay_run:
            raise ValueError("Pay run not found.")
        if pay_run["status"] == "posted":
            raise ValueError("This pay run has already been posted.")
        cursor.execute(
            "SELECT ps.*, d.name AS department_name FROM pay_stubs ps "
            "JOIN employees e ON e.id = ps.employee_id "
            "LEFT JOIN departments d ON d.id = e.department_id "
            "WHERE ps.pay_run_id = ? ORDER BY ps.id", (pay_run_id,),
        )
        rows = cursor.fetchall()
        if not rows:
            raise ValueError("A pay run with no pay stubs cannot be posted.")

        total_net = sum(row["net_pay_cents"] for row in rows)
        wage_totals = defaultdict(int)
        deduction_totals = defaultdict(int)
        for row in rows:
            deductions = _validated_deductions(json.loads(row["deductions"]))
            if row["gross_pay_cents"] - sum(item["amount_cents"] for item in deductions) != row["net_pay_cents"]:
                raise ValueError("A stored pay stub is arithmetically inconsistent.")
            wage_totals[row["department_name"]] += row["gross_pay_cents"]
            for item in deductions:
                deduction_totals[item["label"]] += item["amount_cents"]
        missing = sorted(set(deduction_totals) - set(deduction_accounts))
        if missing:
            raise ValueError("Account mapping required for: " + ", ".join(missing))

        missing_departments = sorted(
            name for name in wage_totals
            if name is not None and name not in wage_accounts
        )
        if None in wage_totals and default_wages_account_id is None:
            missing_departments.append("No department")
        if missing_departments:
            raise ValueError(
                "Wages account mapping required for: " + ", ".join(missing_departments)
            )
        wage_account_ids = {
            wage_accounts[name] if name is not None else default_wages_account_id
            for name in wage_totals
        }
        _assert_accounts(cursor, pay_run["client_id"], wage_account_ids,
                         {"Expense"}, "Wages")
        _assert_accounts(cursor, pay_run["client_id"], deduction_accounts.values(),
                         {"Liability"}, "Deduction")

        lines = [JournalEntryLine(
            account_id=cash_account_id, credit=to_dollars(total_net),
            memo=f"Pay run {pay_run_id}: net pay",
        )]
        lines.extend(JournalEntryLine(
            account_id=(wage_accounts[name] if name is not None
                        else default_wages_account_id),
            debit=to_dollars(amount),
            memo=f"Pay run {pay_run_id}: {name or 'No department'} gross pay",
        ) for name, amount in sorted(wage_totals.items(), key=lambda item: item[0] or "")
          if amount)
        lines.extend(JournalEntryLine(
            account_id=deduction_accounts[label], credit=to_dollars(amount),
            memo=label,
        ) for label, amount in sorted(deduction_totals.items()) if amount)
        entry = JournalEntry(
            client_id=pay_run["client_id"],
            entry_date=date.fromisoformat(pay_run["pay_date"]),
            description=f"Recorded pay run for period ending {pay_run['pay_period_end']}",
            source_reference=f"Pay run {pay_run_id}", lines=lines,
        )
        entry.save(conn=conn)
        cursor.execute(
            "UPDATE pay_runs SET status = 'posted', journal_entry_id = ? "
            "WHERE id = ? AND status = 'draft'", (entry.id, pay_run_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("This pay run has already been posted.")
        AuditLog.write(
            cursor, pay_run["client_id"], "pay_runs", pay_run_id, "UPDATE",
            old_values={"status": "draft", "journal_entry_id": None},
            new_values={"status": "posted", "journal_entry_id": entry.id},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return entry


def parse_canonical_payroll_csv(content: str) -> List[dict]:
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames != CANONICAL_PAYROLL_HEADERS:
        found = ", ".join(reader.fieldnames or []) or "(none)"
        raise ValueError(
            "Canonical payroll CSV headers must be exactly: "
            + ", ".join(CANONICAL_PAYROLL_HEADERS) + f". Found: {found}."
        )
    rows = []
    for row_number, row in enumerate(reader, start=2):
        try:
            deductions = json.loads(row["deductions_json"])
            rows.append({
                "employee_name_raw": row["employee_name"],
                "department_raw": row["department"] or None,
                "pay_period_start": row["pay_period_start"],
                "pay_period_end": row["pay_period_end"],
                "pay_date": row["pay_date"],
                "gross_pay_cents": to_cents(row["gross_pay"]),
                "deductions": deductions,
                "net_pay_cents": to_cents(row["net_pay"]),
                "raw_row": row,
            })
        except Exception as exc:
            raise ValueError(f"Invalid canonical payroll CSV row {row_number}: {exc}") from exc
    if not rows:
        raise ValueError("Canonical payroll CSV must contain at least one row.")
    return rows


def _validated_staged_row(client_id: int, row: dict) -> dict:
    required = {
        "employee_name_raw", "pay_period_start", "pay_period_end", "pay_date",
        "gross_pay_cents", "deductions", "net_pay_cents",
    }
    if not required.issubset(row):
        raise ValueError("Each staged payroll row is missing required canonical fields.")
    employee_name = str(row["employee_name_raw"]).strip()
    if not employee_name:
        raise ValueError("Each staged payroll row requires an employee name.")
    try:
        period_start = date.fromisoformat(str(row["pay_period_start"]))
        period_end = date.fromisoformat(str(row["pay_period_end"]))
        pay_date = date.fromisoformat(str(row["pay_date"]))
    except ValueError as exc:
        raise ValueError("Staged payroll dates must use YYYY-MM-DD.") from exc
    if period_start > period_end:
        raise ValueError("Pay period start must be on or before its end.")
    for staged_date in (period_start, period_end, pay_date):
        closed = FiscalPeriod.get_closed_period_for_date(client_id, staged_date)
        if closed:
            raise ValueError(
                f"{closed.period_name} is closed. Payroll rows dated "
                f"{staged_date.isoformat()} cannot be staged."
            )
    gross = row["gross_pay_cents"]
    net = row["net_pay_cents"]
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
           for value in (gross, net)):
        raise ValueError("Gross and net pay must be non-negative integer cents.")
    deductions = _validated_deductions(row["deductions"])
    if gross - sum(item["amount_cents"] for item in deductions) != net:
        raise ValueError("Gross pay minus deductions must equal net pay.")
    return {
        "employee_name_raw": employee_name,
        "matched_employee_id": row.get("matched_employee_id"),
        "department_raw": str(row.get("department_raw") or "").strip() or None,
        "matched_department_id": row.get("matched_department_id"),
        "pay_period_start": period_start.isoformat(),
        "pay_period_end": period_end.isoformat(), "pay_date": pay_date.isoformat(),
        "gross_pay_cents": gross, "deductions": deductions,
        "employer_costs": row.get("employer_costs"), "net_pay_cents": net,
        "raw_row": row.get("raw_row", row),
    }


def stage_payroll_rows(client_id: int, provider: str, source_report: str,
                       file_name: str, rows: List[dict]) -> int:
    if provider not in ("gusto", "quickbooks"):
        raise ValueError("Provider must be gusto or quickbooks.")
    if not source_report.strip() or not file_name.strip():
        raise ValueError("Source report and file name are required.")
    if not rows:
        raise ValueError("At least one payroll row is required.")
    normalized = [_validated_staged_row(client_id, row) for row in rows]

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO payroll_import_batches "
            "(client_id, provider, source_report, file_name) VALUES (?, ?, ?, ?)",
            (client_id, provider, source_report.strip(), file_name.strip()),
        )
        batch_id = cursor.lastrowid
        AuditLog.write(
            cursor, client_id, "payroll_import_batches", batch_id, "INSERT",
            new_values={"provider": provider, "source_report": source_report.strip(),
                        "file_name": file_name.strip()},
        )
        for row in normalized:
            cursor.execute(
                "INSERT INTO payroll_import_rows "
                "(batch_id, employee_name_raw, matched_employee_id, department_raw, "
                "matched_department_id, pay_period_start, pay_period_end, pay_date, "
                "gross_pay_cents, deductions, employer_costs, net_pay_cents, raw_row) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (batch_id, row["employee_name_raw"], row["matched_employee_id"],
                 row["department_raw"], row["matched_department_id"],
                 row["pay_period_start"], row["pay_period_end"], row["pay_date"],
                 row["gross_pay_cents"], json.dumps(row["deductions"]),
                 json.dumps(row["employer_costs"]) if row["employer_costs"] is not None else None,
                 row["net_pay_cents"], json.dumps(row["raw_row"], default=str)),
            )
            row_id = cursor.lastrowid
            AuditLog.write(
                cursor, client_id, "payroll_import_rows", row_id, "INSERT",
                new_values={**row, "batch_id": batch_id, "status": "pending"},
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return batch_id


def get_payroll_import_rows(client_id: int, batch_id: Optional[int] = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = (
            "SELECT r.*, b.client_id, b.provider, b.file_name "
            "FROM payroll_import_rows r JOIN payroll_import_batches b ON b.id = r.batch_id "
            "WHERE b.client_id = ?"
        )
        params = [client_id]
        if batch_id is not None:
            query += " AND r.batch_id = ?"
            params.append(batch_id)
        cursor.execute(query + " ORDER BY r.id", params)
        return cursor.fetchall()


def update_payroll_import_row(row_id: int, matched_employee_id: Optional[int],
                              matched_department_id: Optional[int]) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT r.*, b.client_id FROM payroll_import_rows r "
            "JOIN payroll_import_batches b ON b.id = r.batch_id WHERE r.id = ?",
            (row_id,),
        )
        row = cursor.fetchone()
        if not row or row["status"] != "pending":
            raise ValueError("Pending payroll import row not found.")
        if matched_employee_id is not None:
            cursor.execute("SELECT 1 FROM employees WHERE id = ? AND client_id = ?",
                           (matched_employee_id, row["client_id"]))
            if not cursor.fetchone():
                raise ValueError("Matched employee is not owned by this client.")
        if matched_department_id is not None:
            cursor.execute("SELECT 1 FROM departments WHERE id = ? AND client_id = ?",
                           (matched_department_id, row["client_id"]))
            if not cursor.fetchone():
                raise ValueError("Matched department is not owned by this client.")
        old_values = {"matched_employee_id": row["matched_employee_id"],
                      "matched_department_id": row["matched_department_id"]}
        new_values = {"matched_employee_id": matched_employee_id,
                      "matched_department_id": matched_department_id}
        cursor.execute(
            "UPDATE payroll_import_rows SET matched_employee_id = ?, "
            "matched_department_id = ? WHERE id = ? AND status = 'pending'",
            (matched_employee_id, matched_department_id, row_id),
        )
        AuditLog.write(cursor, row["client_id"], "payroll_import_rows", row_id,
                       "UPDATE", old_values=old_values, new_values=new_values)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def accept_payroll_batch(batch_id: int) -> PayRun:
    pay_run_id = None
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payroll_import_batches WHERE id = ?", (batch_id,))
        batch = cursor.fetchone()
        if not batch:
            raise ValueError("Payroll import batch not found.")
        cursor.execute(
            "SELECT * FROM payroll_import_rows WHERE batch_id = ? ORDER BY id", (batch_id,),
        )
        rows = cursor.fetchall()
        pending = [row for row in rows if row["status"] == "pending"]
        if not pending:
            if rows and all(row["status"] == "accepted" for row in rows):
                raise ValueError("This payroll import batch has already been accepted.")
            raise ValueError("This payroll import batch has no pending rows to accept.")
        if len(pending) != len(rows):
            raise ValueError("Resolve dismissed rows before accepting this payroll import batch.")
        if any(row["matched_employee_id"] is None for row in pending):
            raise ValueError("Every pending row must have a matched employee before acceptance.")
        periods = {(row["pay_period_start"], row["pay_period_end"], row["pay_date"])
                   for row in pending}
        if len(periods) != 1:
            raise ValueError("A payroll import batch must contain one pay period and pay date.")
        period_start, period_end, pay_date = next(iter(periods))
        pay_run = create_pay_run(
            batch["client_id"], date.fromisoformat(period_start),
            date.fromisoformat(period_end), date.fromisoformat(pay_date), _conn=conn,
        )
        pay_run_id = pay_run.id
        for row in pending:
            add_pay_stub(
                pay_run_id, row["matched_employee_id"], row["gross_pay_cents"],
                json.loads(row["deductions"]), row["net_pay_cents"], _conn=conn,
            )
            if row["matched_department_id"] is not None:
                cursor.execute(
                    "SELECT 1 FROM departments WHERE id = ? AND client_id = ?",
                    (row["matched_department_id"], batch["client_id"]),
                )
                if not cursor.fetchone():
                    raise ValueError("Matched department is not owned by this client.")
                cursor.execute(
                    "SELECT department_id FROM employees WHERE id = ?",
                    (row["matched_employee_id"],),
                )
                employee = cursor.fetchone()
                if employee["department_id"] != row["matched_department_id"]:
                    old_department_id = employee["department_id"]
                    cursor.execute(
                        "UPDATE employees SET department_id = ? WHERE id = ? AND client_id = ?",
                        (row["matched_department_id"], row["matched_employee_id"],
                         batch["client_id"]),
                    )
                    AuditLog.write(
                        cursor, batch["client_id"], "employees",
                        row["matched_employee_id"], "UPDATE",
                        old_values={"department_id": old_department_id},
                        new_values={"department_id": row["matched_department_id"]},
                    )
            cursor.execute(
                "UPDATE payroll_import_rows SET status = 'accepted' "
                "WHERE id = ? AND status = 'pending'", (row["id"],),
            )
            if cursor.rowcount != 1:
                raise ValueError("This payroll import batch has already been accepted.")
            AuditLog.write(cursor, batch["client_id"], "payroll_import_rows", row["id"],
                           "UPDATE", old_values={"status": "pending"},
                           new_values={"status": "accepted", "pay_run_id": pay_run_id})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return PayRun.get_by_id(pay_run_id)


def dismiss_payroll_row(row_id: int, reason: str) -> None:
    reason = reason.strip()
    if not reason:
        raise ValueError("A dismissal reason is required.")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT r.*, b.client_id FROM payroll_import_rows r "
            "JOIN payroll_import_batches b ON b.id = r.batch_id WHERE r.id = ?",
            (row_id,),
        )
        row = cursor.fetchone()
        if not row or row["status"] != "pending":
            raise ValueError("Pending payroll import row not found.")
        cursor.execute("UPDATE payroll_import_rows SET status = 'dismissed' WHERE id = ?",
                       (row_id,))
        AuditLog.write(cursor, row["client_id"], "payroll_import_rows", row_id, "UPDATE",
                       old_values={"status": "pending"},
                       new_values={"status": "dismissed", "reason": reason})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
