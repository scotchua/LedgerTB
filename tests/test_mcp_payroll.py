"""Assistant-staged payroll: record provider figures, review and post in app.

Contract: propose_pay_run stages a DRAFT pay run and its stubs, never touches
the ledger, and refuses arithmetic it was handed wrong. The assistant's own
connection can insert a draft run but cannot post one, cannot add an employee,
and cannot alter what it filed.

LedgerTB does not calculate payroll. Every figure here is supplied, and the
tool's job is to refuse a set that does not foot, not to fix it.
"""
from datetime import date

import pytest

from database import connection as dbconn
from models.journal_entry import JournalEntry
from models.payroll import PayRun, PayStub
from services import mcp_tools

PERIOD = ("2026-01-01", "2026-01-15")
PAY_DATE = "2026-01-20"


def _employee(client_id, name="Officer One", department_id=None):
    from models.payroll import Employee

    employee = Employee(
        client_id=client_id, name=name, start_date=date(2025, 1, 1),
        status="active", department_id=department_id,
    )
    employee.save()
    return employee


def _stub(employee_id, gross=5000.00, net=3712.50):
    return {
        "employee_id": employee_id,
        "gross_pay": gross,
        "net_pay": net,
        "withholdings": [
            {"label": "Federal income tax", "amount": 750.00},
            {"label": "FICA", "amount": 537.50},
        ],
    }


def test_propose_pay_run_stages_a_draft_and_posts_nothing(client_id, accounts,
                                                          monkeypatch):
    employee = _employee(client_id)
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    entries_before = len(JournalEntry.get_all(client_id))

    result = mcp_tools.propose_pay_run(
        client_id, *PERIOD, PAY_DATE, [_stub(employee.id)],
        rationale="January officer payroll per provider report",
    )

    assert result["status"] == "draft"
    assert result["posted"] is False
    assert result["stubs"] == 1
    assert result["total_gross"] == 5000.00
    assert result["total_net"] == 3712.50

    run = PayRun.get_by_id(result["pay_run_id"])
    assert run.status == "draft"
    assert run.journal_entry_id is None
    # The whole point: nothing reached the ledger.
    assert len(JournalEntry.get_all(client_id)) == entries_before

    stubs = PayStub.get_all(run.id)
    assert len(stubs) == 1
    assert stubs[0].gross_pay_cents == 500000
    assert stubs[0].net_pay_cents == 371250
    assert sorted(d["label"] for d in stubs[0].deductions) == [
        "FICA", "Federal income tax"
    ]


def test_propose_and_list_pay_run_employer_costs(client_id, accounts, monkeypatch):
    employee = _employee(client_id, "Payroll Cost Employee")
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    stub = _stub(employee.id)
    stub["employer_costs"] = [
        {"label": "Employer FICA", "amount": 382.50},
        {"label": "Benefits", "amount": 100.00},
    ]

    result = mcp_tools.propose_pay_run(client_id, *PERIOD, PAY_DATE, [stub])

    stored = PayStub.get_all(result["pay_run_id"])[0]
    assert stored.employer_costs == [
        {"label": "Employer FICA", "amount_cents": 38250},
        {"label": "Benefits", "amount_cents": 10000},
    ]
    assert mcp_tools.list_pay_runs(client_id)[0]["stubs"][0]["employer_costs"] == [
        {"label": "Employer FICA", "amount": 382.50},
        {"label": "Benefits", "amount": 100.00},
    ]


@pytest.mark.parametrize("cost", [
    {"label": "", "amount": 10.00},
    {"label": "SUTA", "amount": -1.00},
])
def test_propose_pay_run_rejects_invalid_employer_cost_naming_stub(
        client_id, accounts, monkeypatch, cost):
    employee = _employee(client_id, "Invalid Cost Employee")
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    stub = _stub(employee.id)
    stub["employer_costs"] = [cost]

    with pytest.raises(ValueError, match="Stub 1"):
        mcp_tools.propose_pay_run(client_id, *PERIOD, PAY_DATE, [stub])


def test_a_stub_that_does_not_foot_is_refused_by_stub_number(client_id,
                                                             accounts,
                                                             monkeypatch):
    """The caller owns the arithmetic, so the error has to say which stub."""
    employee = _employee(client_id)
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    bad = _stub(employee.id, net=4000.00)  # withholdings do not bridge the gap

    with pytest.raises(ValueError, match="Stub 1"):
        mcp_tools.propose_pay_run(client_id, *PERIOD, PAY_DATE, [bad])

    assert PayRun.get_all(client_id) == []


def test_a_failed_stub_leaves_no_half_built_pay_run(client_id, accounts,
                                                    monkeypatch):
    """A reviewer seeing a run must see the whole payroll, never part of it."""
    first = _employee(client_id, "Officer One")
    second = _employee(client_id, "Officer Two")
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")

    with pytest.raises(ValueError, match="Stub 2"):
        mcp_tools.propose_pay_run(
            client_id, *PERIOD, PAY_DATE,
            [_stub(first.id), _stub(second.id, net=1.00)],
        )

    assert PayRun.get_all(client_id) == []


def test_an_unknown_employee_names_the_remedy(client_id, accounts, monkeypatch):
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    with pytest.raises(ValueError, match="list_employees"):
        mcp_tools.propose_pay_run(client_id, *PERIOD, PAY_DATE,
                                  [_stub(99999)])


def test_empty_and_malformed_stub_lists_are_refused(client_id, accounts,
                                                    monkeypatch):
    employee = _employee(client_id)
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    with pytest.raises(ValueError, match="non-empty"):
        mcp_tools.propose_pay_run(client_id, *PERIOD, PAY_DATE, [])
    with pytest.raises(ValueError, match="Stub 1"):
        mcp_tools.propose_pay_run(client_id, *PERIOD, PAY_DATE, ["not a dict"])
    unlabelled = _stub(employee.id)
    unlabelled["withholdings"] = [{"amount": 10.00}]
    with pytest.raises(ValueError, match="label"):
        mcp_tools.propose_pay_run(client_id, *PERIOD, PAY_DATE, [unlabelled])


def test_list_pay_runs_and_list_employees_report_the_draft(client_id, accounts,
                                                           monkeypatch):
    employee = _employee(client_id)
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    result = mcp_tools.propose_pay_run(client_id, *PERIOD, PAY_DATE,
                                       [_stub(employee.id)])

    people = mcp_tools.list_employees(client_id)
    assert [p["employee_id"] for p in people] == [employee.id]
    assert people[0]["status"] == "active"

    runs = mcp_tools.list_pay_runs(client_id)
    assert len(runs) == 1
    assert runs[0]["pay_run_id"] == result["pay_run_id"]
    assert runs[0]["status"] == "draft"
    assert runs[0]["journal_entry_id"] is None
    assert runs[0]["total_gross"] == 5000.00
    assert runs[0]["stubs"][0]["withholdings"][0]["amount"] in (750.00, 537.50)
    assert mcp_tools.list_pay_runs(client_id, "posted") == []


def test_the_assistant_can_stage_a_run_but_cannot_post_or_hire(client_id,
                                                               accounts,
                                                               monkeypatch):
    """The engine, not the tool list, is what holds this line."""
    from models.payroll import Employee

    employee = _employee(client_id)
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    result = mcp_tools.propose_pay_run(client_id, *PERIOD, PAY_DATE,
                                       [_stub(employee.id)])

    # Posting a pay run flips pay_runs.status: an UPDATE, denied at every level.
    with pytest.raises(Exception):
        with dbconn.get_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE pay_runs SET status = 'posted' WHERE id = ?",
                (result["pay_run_id"],),
            )
    assert PayRun.get_by_id(result["pay_run_id"]).status == "draft"

    # Adding a person to the book stays a human decision.
    with pytest.raises(Exception):
        Employee(client_id=client_id, name="Not Hired Here",
                 start_date=date(2026, 1, 1)).save()
