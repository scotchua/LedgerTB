from datetime import date

import pytest

from database.connection import get_cursor
from models.account import Account
from models.payroll import Employee
from services.payroll_recording import add_pay_stub, create_pay_run, post_pay_run


def _employee(client_id, name):
    employee = Employee(client_id=client_id, name=name, start_date=date(2026, 1, 1))
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
        run.id, accounts["expense"], accounts["cash"],
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
    post_pay_run(run.id, accounts["expense"], accounts["cash"], {})
    with pytest.raises(ValueError, match="already been posted"):
        post_pay_run(run.id, accounts["expense"], accounts["cash"], {})


def test_post_pay_run_refuses_empty_run(client_id, accounts):
    run = create_pay_run(client_id, date(2026, 5, 1), date(2026, 5, 15),
                         date(2026, 5, 20))
    with pytest.raises(ValueError, match="no pay stubs"):
        post_pay_run(run.id, accounts["expense"], accounts["cash"], {})


def test_payroll_mutations_are_audited_and_attributed(client_id, accounts):
    employee = _employee(client_id, "Casey Grove")
    employee.deactivate()
    run = create_pay_run(client_id, date(2026, 6, 1), date(2026, 6, 15),
                         date(2026, 6, 20))
    add_pay_stub(run.id, employee.id, 50000, [], 50000)
    post_pay_run(run.id, accounts["expense"], accounts["cash"], {})

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
