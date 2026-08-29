import json
from collections import defaultdict
from datetime import date
from typing import Dict, List

from database.connection import get_connection
from models.audit_log import AuditLog
from models.journal_entry import JournalEntry, JournalEntryLine
from models.payroll import PayRun, PayStub
from money import to_dollars


def create_pay_run(client_id: int, period_start: date, period_end: date,
                   pay_date: date) -> PayRun:
    if period_start > period_end:
        raise ValueError("Pay period start must be on or before its end.")
    conn = get_connection()
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
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return PayRun.get_by_id(pay_run_id)


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
                 deductions: List[dict], net_pay_cents: int) -> PayStub:
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
           for value in (gross_pay_cents, net_pay_cents)):
        raise ValueError("Gross and net pay must be non-negative integer cents.")
    deductions = _validated_deductions(deductions)
    if gross_pay_cents - sum(item["amount_cents"] for item in deductions) != net_pay_cents:
        raise ValueError("Gross pay minus deductions must equal net pay.")

    conn = get_connection()
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
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return PayStub(stub_id, pay_run_id, employee_id, gross_pay_cents,
                   deductions, net_pay_cents)


def post_pay_run(pay_run_id: int, wages_account_id: int, cash_account_id: int,
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
        cursor.execute("SELECT * FROM pay_stubs WHERE pay_run_id = ? ORDER BY id", (pay_run_id,))
        rows = cursor.fetchall()
        if not rows:
            raise ValueError("A pay run with no pay stubs cannot be posted.")

        total_gross = sum(row["gross_pay_cents"] for row in rows)
        total_net = sum(row["net_pay_cents"] for row in rows)
        deduction_totals = defaultdict(int)
        for row in rows:
            deductions = _validated_deductions(json.loads(row["deductions"]))
            if row["gross_pay_cents"] - sum(item["amount_cents"] for item in deductions) != row["net_pay_cents"]:
                raise ValueError("A stored pay stub is arithmetically inconsistent.")
            for item in deductions:
                deduction_totals[item["label"]] += item["amount_cents"]
        missing = sorted(set(deduction_totals) - set(deduction_accounts))
        if missing:
            raise ValueError("Account mapping required for: " + ", ".join(missing))

        lines = [JournalEntryLine(
            account_id=wages_account_id, debit=to_dollars(total_gross),
            memo=f"Pay run {pay_run_id}: gross pay",
        ), JournalEntryLine(
            account_id=cash_account_id, credit=to_dollars(total_net),
            memo=f"Pay run {pay_run_id}: net pay",
        )]
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
