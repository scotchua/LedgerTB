from datetime import date

import pytest

from database.connection import get_cursor
from models.account import Account
from models.department import Department
from models.fiscal_period import FiscalPeriod
from models.payroll import Employee, PayStub
from services.payroll_recording import (
    accept_payroll_batch, add_pay_stub, create_pay_run, parse_canonical_payroll_csv,
    post_pay_run, stage_payroll_rows, update_payroll_import_row,
)


def _employee(client_id, name, department_id=None):
    employee = Employee(client_id=client_id, name=name, start_date=date(2026, 1, 1),
                        department_id=department_id)
    employee.save()
    return employee


def _liability(client_id, number, name):
    account = Account(client_id=client_id, account_number=number,
                      name=name, type="Liability")
    account.save()
    return account.id


def test_multi_employee_pay_run_posts_hand_computed_balanced_entry(client_id, accounts):
    first = _employee(client_id, "Alex North")
    second = _employee(client_id, "Morgan Lake")
    federal = _liability(client_id, "2100", "Withholding A")
    benefits = _liability(client_id, "2110", "Deduction B")
    run = create_pay_run(client_id, date(2026, 2, 1), date(2026, 2, 15),
                         date(2026, 2, 20))
    add_pay_stub(run.id, first.id, 200000, [
        {"label": "Withholding A", "amount_cents": 30000},
        {"label": "Deduction B", "amount_cents": 5000},
    ], 165000)
    add_pay_stub(run.id, second.id, 150000, [
        {"label": "Withholding A", "amount_cents": 20000},
        {"label": "Deduction B", "amount_cents": 3000},
    ], 127000)

    entry = post_pay_run(
        run.id, {}, accounts["expense"], accounts["cash"],
        {"Withholding A": federal, "Deduction B": benefits},
    )

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT account_id, debit, credit FROM journal_entry_lines "
            "WHERE journal_entry_id = ? ORDER BY account_id", (entry.id,),
        )
        lines = {(row["account_id"], row["debit"], row["credit"])
                 for row in cursor.fetchall()}
    assert lines == {
        (accounts["expense"], 350000, 0),
        (accounts["cash"], 0, 292000),
        (federal, 0, 50000),
        (benefits, 0, 8000),
    }
    assert entry.is_balanced()


def test_add_pay_stub_refuses_inconsistent_arithmetic(client_id):
    employee = _employee(client_id, "Taylor Reed")
    run = create_pay_run(client_id, date(2026, 3, 1), date(2026, 3, 15),
                         date(2026, 3, 20))
    with pytest.raises(ValueError, match="Gross pay minus deductions"):
        add_pay_stub(run.id, employee.id, 100000, [
            {"label": "Recorded deduction", "amount_cents": 10000},
        ], 91000)


def test_post_pay_run_refuses_reposting(client_id, accounts):
    employee = _employee(client_id, "Jordan Pine")
    run = create_pay_run(client_id, date(2026, 4, 1), date(2026, 4, 15),
                         date(2026, 4, 20))
    add_pay_stub(run.id, employee.id, 100000, [], 100000)
    post_pay_run(run.id, {}, accounts["expense"], accounts["cash"], {})
    with pytest.raises(ValueError, match="already been posted"):
        post_pay_run(run.id, {}, accounts["expense"], accounts["cash"], {})


def test_post_pay_run_refuses_empty_run(client_id, accounts):
    run = create_pay_run(client_id, date(2026, 5, 1), date(2026, 5, 15),
                         date(2026, 5, 20))
    with pytest.raises(ValueError, match="no pay stubs"):
        post_pay_run(run.id, {}, accounts["expense"], accounts["cash"], {})


def test_payroll_mutations_are_audited_and_attributed(client_id, accounts):
    employee = _employee(client_id, "Casey Grove")
    employee.deactivate()
    run = create_pay_run(client_id, date(2026, 6, 1), date(2026, 6, 15),
                         date(2026, 6, 20))
    add_pay_stub(run.id, employee.id, 50000, [], 50000)
    post_pay_run(run.id, {}, accounts["expense"], accounts["cash"], {})

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT table_name, action, performed_by FROM audit_log "
            "WHERE table_name IN ('employees', 'pay_runs', 'pay_stubs') "
            "ORDER BY id"
        )
        rows = cursor.fetchall()
    assert [(row["table_name"], row["action"]) for row in rows] == [
        ("employees", "INSERT"), ("employees", "UPDATE"),
        ("pay_runs", "INSERT"), ("pay_stubs", "INSERT"),
        ("pay_runs", "UPDATE"),
    ]
    assert all(row["performed_by"] and "(AI)" not in row["performed_by"] for row in rows)


def test_payroll_schema_contains_only_minimal_employee_fields(db):
    with get_cursor() as cursor:
        cursor.execute("PRAGMA table_info(employees)")
        columns = {row["name"] for row in cursor.fetchall()}
    # department_id (migration 035) is a GL-routing dimension, not PII; this
    # guard's purpose is keeping SSNs/bank fields out of the payroll schema.
    assert columns == {"id", "client_id", "name", "start_date", "status",
                       "created_at", "department_id"}


def test_department_routed_pay_run_posts_balanced_entry(client_id, accounts):
    sales = Department(client_id=client_id, name="Sales")
    sales.save()
    operations = Department(client_id=client_id, name="Operations")
    operations.save()
    sales_account = Account(client_id=client_id, account_number="6010",
                            name="Sales wages", type="Expense")
    sales_account.save()
    operations_account = Account(client_id=client_id, account_number="6020",
                                 name="Operations wages", type="Expense")
    operations_account.save()
    sales_employee = _employee(client_id, "Sales Employee", sales.id)
    operations_employee = _employee(client_id, "Operations Employee", operations.id)
    unassigned_employee = _employee(client_id, "Unassigned Employee")
    withholding = _liability(client_id, "2120", "Withholding")
    run = create_pay_run(client_id, date(2026, 7, 1), date(2026, 7, 15),
                         date(2026, 7, 20))
    add_pay_stub(run.id, sales_employee.id, 100000,
                 [{"label": "Withholding", "amount_cents": 10000}], 90000)
    add_pay_stub(run.id, operations_employee.id, 80000, [], 80000)
    add_pay_stub(run.id, unassigned_employee.id, 50000, [], 50000)

    entry = post_pay_run(
        run.id, {"Sales": sales_account.id, "Operations": operations_account.id},
        accounts["expense"], accounts["cash"], {"Withholding": withholding},
    )

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT account_id, debit, credit, memo FROM journal_entry_lines "
            "WHERE journal_entry_id = ?", (entry.id,),
        )
        lines = {(row["account_id"], row["debit"], row["credit"], row["memo"])
                 for row in cursor.fetchall()}
    assert lines == {
        (sales_account.id, 100000, 0, f"Pay run {run.id}: Sales gross pay"),
        (operations_account.id, 80000, 0, f"Pay run {run.id}: Operations gross pay"),
        (accounts["expense"], 50000, 0, f"Pay run {run.id}: No department gross pay"),
        (withholding, 0, 10000, "Withholding"),
        (accounts["cash"], 0, 220000, f"Pay run {run.id}: net pay"),
    }
    assert entry.is_balanced()


def test_department_without_mapping_or_fallback_posts_nothing(client_id, accounts):
    department = Department(client_id=client_id, name="Research")
    department.save()
    employee = _employee(client_id, "Research Employee", department.id)
    run = create_pay_run(client_id, date(2026, 8, 1), date(2026, 8, 15),
                         date(2026, 8, 20))
    add_pay_stub(run.id, employee.id, 100000, [], 100000)

    with pytest.raises(ValueError, match="Research"):
        post_pay_run(run.id, {}, None, accounts["cash"], {})
    with get_cursor() as cursor:
        cursor.execute("SELECT status, journal_entry_id FROM pay_runs WHERE id = ?", (run.id,))
        stored = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM journal_entries WHERE source_reference = ?",
                       (f"Pay run {run.id}",))
        count = cursor.fetchone()[0]
    assert (stored["status"], stored["journal_entry_id"], count) == ("draft", None, 0)


def _staged_row(employee_name="Staged Employee", pay_date="2026-09-20"):
    return {
        "employee_name_raw": employee_name, "department_raw": None,
        "pay_period_start": "2026-09-01", "pay_period_end": "2026-09-15",
        "pay_date": pay_date, "gross_pay_cents": 100000,
        "deductions": [{"label": "Tax", "amount_cents": 10000}],
        "net_pay_cents": 90000,
    }


def test_stage_payroll_rows_is_atomic_and_rejects_closed_period(client_id):
    with pytest.raises(ValueError, match="Gross pay minus deductions"):
        stage_payroll_rows(client_id, "gusto", "Payroll register", "payroll.csv",
                           [_staged_row(), {**_staged_row("Bad"), "net_pay_cents": 90001}])
    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM payroll_import_batches")
        assert cursor.fetchone()[0] == 0

    FiscalPeriod(
        client_id=client_id, period_name="2026", period_type="Year",
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), is_closed=True,
    ).save()
    with pytest.raises(ValueError, match="closed"):
        stage_payroll_rows(client_id, "gusto", "Payroll register", "payroll.csv",
                           [_staged_row()])
    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM payroll_import_batches")
        assert cursor.fetchone()[0] == 0


def test_accept_payroll_batch_creates_exact_draft_and_refuses_duplicate(client_id):
    first = _employee(client_id, "First Match")
    second = _employee(client_id, "Second Match")
    batch_id = stage_payroll_rows(
        client_id, "quickbooks", "Payroll details", "payroll.csv",
        [_staged_row("First Match"), {**_staged_row("Second Match"),
                                     "gross_pay_cents": 50000,
                                     "deductions": [], "net_pay_cents": 50000}],
    )
    with pytest.raises(ValueError, match="matched employee"):
        accept_payroll_batch(batch_id)
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM payroll_import_rows WHERE batch_id = ? ORDER BY id",
                       (batch_id,))
        row_ids = [row["id"] for row in cursor.fetchall()]
    update_payroll_import_row(row_ids[0], first.id, None)
    update_payroll_import_row(row_ids[1], second.id, None)

    run = accept_payroll_batch(batch_id)
    assert run.status == "draft"
    assert [(stub.employee_id, stub.gross_pay_cents, stub.net_pay_cents)
            for stub in PayStub.get_all(run.id)] == [
        (first.id, 100000, 90000), (second.id, 50000, 50000),
    ]
    with pytest.raises(ValueError, match="already been accepted"):
        accept_payroll_batch(batch_id)


def test_canonical_csv_round_trips_through_posting(client_id, accounts):
    employee = _employee(client_id, "CSV Employee")
    withholding = _liability(client_id, "2130", "Tax")
    content = (
        "employee_name,department,pay_period_start,pay_period_end,pay_date,"
        "gross_pay,deductions_json,net_pay\n"
        'CSV Employee,,2026-10-01,2026-10-15,2026-10-20,1000.00,'
        '"[{""label"":""Tax"",""amount_cents"":10000}]",900.00\n'
    )
    rows = parse_canonical_payroll_csv(content)
    batch_id = stage_payroll_rows(
        client_id, "gusto", "Canonical payroll export", "canonical.csv", rows,
    )
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM payroll_import_rows WHERE batch_id = ?", (batch_id,))
        row_id = cursor.fetchone()["id"]
    update_payroll_import_row(row_id, employee.id, None)
    run = accept_payroll_batch(batch_id)
    entry = post_pay_run(run.id, {}, accounts["expense"], accounts["cash"],
                         {"Tax": withholding})
    assert entry.is_balanced()
    assert PayStub.get_all(run.id)[0].gross_pay_cents == 100000


def test_canonical_csv_rejects_header_drift():
    with pytest.raises(ValueError, match="headers must be exactly"):
        parse_canonical_payroll_csv(
            "employee_name,pay_date,gross_pay\nEmployee,2026-10-20,100.00\n"
        )
