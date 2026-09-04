import json
from datetime import date

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from database.connection import get_connection, get_cursor
from database.schema import create_tables
from models.journal_entry import JournalEntry, JournalEntryLine
from models.payroll import Employee
from services.payroll_recording import (
    accept_payroll_batch, add_pay_stub, create_pay_run, discard_pay_run,
    linked_import_row_count, stage_payroll_rows, update_payroll_import_row,
)
from tests.conftest import page_path


def _employee(client_id, name):
    employee = Employee(client_id=client_id, name=name, start_date=date(2026, 1, 1))
    employee.save()
    return employee


def _staged_row(name, gross_pay_cents=100000):
    return {
        "employee_name_raw": name, "department_raw": None,
        "pay_period_start": "2026-09-01", "pay_period_end": "2026-09-15",
        "pay_date": "2026-09-20", "gross_pay_cents": gross_pay_cents,
        "deductions": [], "net_pay_cents": gross_pay_cents,
    }


def test_discard_page_survives_rerun_and_selects_remaining_run(
    client_id, monkeypatch,
):
    import utils.client_selector as selector

    monkeypatch.setattr(selector, "render_client_selector", lambda: client_id)
    monkeypatch.setattr(st, "page_link", lambda *args, **kwargs: None)
    employee = _employee(client_id, "Payroll Tester")
    first = create_pay_run(client_id, date(2026, 8, 1), date(2026, 8, 15),
                           date(2026, 8, 20))
    second = create_pay_run(client_id, date(2026, 8, 16), date(2026, 8, 31),
                            date(2026, 9, 5))
    add_pay_stub(first.id, employee.id, 50000, [], 50000)
    add_pay_stub(second.id, employee.id, 75000, [], 75000)

    page = AppTest.from_file(
        page_path("pages/20_Payroll_Recording.py"), default_timeout=30
    )
    page.session_state["payroll_run_id"] = second.id
    page.session_state["payroll_run_selection"] = second.id
    page.run()
    page.button(key=f"discard_pay_run_{second.id}").click().run()
    page.button(key=f"confirm_discard_pay_run_{second.id}").click().run()

    assert not page.exception
    assert any("Discarded draft with 1 pay stubs." in item.value for item in page.success)
    assert page.selectbox(key="payroll_run_selection").value == first.id

    page.button(key=f"discard_pay_run_{first.id}").click().run()
    page.button(key=f"confirm_discard_pay_run_{first.id}").click().run()

    assert not page.exception
    assert any(item.value == "No pay runs recorded yet." for item in page.info)


def test_linked_import_row_count_returns_zero_and_two(client_id):
    first = _employee(client_id, "Count One")
    second = _employee(client_id, "Count Two")
    run = create_pay_run(client_id, date(2026, 9, 1), date(2026, 9, 15),
                         date(2026, 9, 20))
    assert linked_import_row_count(run.id) == 0
    batch_id = stage_payroll_rows(
        client_id, "gusto", "Payroll register", "register.csv",
        [_staged_row("Count One"), _staged_row("Count Two", 60000)],
    )
    with get_cursor(commit=True) as cursor:
        row_ids = [row["id"] for row in cursor.execute(
            "SELECT id FROM payroll_import_rows WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        ).fetchall()]
        cursor.executemany(
            "UPDATE payroll_import_rows SET status = 'accepted', pay_run_id = ? "
            "WHERE id = ?", [(run.id, row_id) for row_id in row_ids],
        )
    assert linked_import_row_count(run.id) == 2


def test_discard_draft_deletes_run_and_stubs_with_one_operation(client_id):
    first = _employee(client_id, "Cedar Finch")
    second = _employee(client_id, "Willow Hart")
    run = create_pay_run(client_id, date(2026, 8, 1), date(2026, 8, 15),
                         date(2026, 8, 20))
    add_pay_stub(run.id, first.id, 100000, [], 100000)
    add_pay_stub(run.id, second.id, 75000, [], 75000)

    result = discard_pay_run(run.id)

    assert result == {"pay_run_id": run.id, "stubs_deleted": 2,
                      "import_rows_reverted": 0}
    with get_cursor() as cursor:
        assert cursor.execute(
            "SELECT COUNT(*) FROM pay_runs WHERE id = ?", (run.id,)
        ).fetchone()[0] == 0
        assert cursor.execute(
            "SELECT COUNT(*) FROM pay_stubs WHERE pay_run_id = ?", (run.id,)
        ).fetchone()[0] == 0
        rows = cursor.execute(
            "SELECT table_name, old_values, new_values FROM audit_log "
            "WHERE action = 'DELETE' AND ((table_name = 'pay_runs' AND record_id = ?) "
            "OR (table_name = 'pay_stubs' AND json_extract(old_values, '$.employee_id') "
            "IN (?, ?))) ORDER BY id", (run.id, first.id, second.id),
        ).fetchall()
    assert [row["table_name"] for row in rows] == ["pay_stubs", "pay_stubs", "pay_runs"]
    assert len({json.loads(row["new_values"])["operation_id"] for row in rows}) == 1
    assert json.loads(rows[-1]["old_values"])["stub_count"] == 2


@pytest.mark.parametrize("run_state", ["posted", "journal_entry"])
def test_discard_refuses_non_discardable_run_without_changes(
    client_id, accounts, run_state,
):
    employee = _employee(client_id, f"Refusal {run_state}")
    run = create_pay_run(client_id, date(2026, 7, 1), date(2026, 7, 15),
                         date(2026, 7, 20))
    add_pay_stub(run.id, employee.id, 50000, [], 50000)
    with get_cursor(commit=True) as cursor:
        if run_state == "posted":
            cursor.execute("UPDATE pay_runs SET status = 'posted' WHERE id = ?", (run.id,))
        else:
            entry = JournalEntry(
                client_id=client_id, entry_date=date(2026, 7, 20),
                description="Draft link guard", lines=[
                    JournalEntryLine(account_id=accounts["expense"], debit=500),
                    JournalEntryLine(account_id=accounts["cash"], credit=500),
                ],
            )
            entry.save(conn=cursor.connection)
            cursor.execute(
                "UPDATE pay_runs SET journal_entry_id = ? WHERE id = ?", (entry.id, run.id),
            )
        before = tuple(cursor.execute(
            "SELECT (SELECT COUNT(*) FROM pay_runs), "
            "(SELECT COUNT(*) FROM pay_stubs), (SELECT COUNT(*) FROM audit_log)"
        ).fetchone())

    with pytest.raises(ValueError, match="unposted draft"):
        discard_pay_run(run.id)

    with get_cursor() as cursor:
        after = tuple(cursor.execute(
            "SELECT (SELECT COUNT(*) FROM pay_runs), "
            "(SELECT COUNT(*) FROM pay_stubs), (SELECT COUNT(*) FROM audit_log)"
        ).fetchone())
    assert after == before


def test_discard_accepted_batch_reverts_rows_and_batch_can_be_accepted_again(client_id):
    first = _employee(client_id, "Juniper Stone")
    second = _employee(client_id, "Aspen Vale")
    batch_id = stage_payroll_rows(
        client_id, "gusto", "Payroll register", "register.csv",
        [_staged_row("Juniper Stone"), _staged_row("Aspen Vale", 60000)],
    )
    with get_cursor() as cursor:
        row_ids = [row["id"] for row in cursor.execute(
            "SELECT id FROM payroll_import_rows WHERE batch_id = ? ORDER BY id", (batch_id,),
        ).fetchall()]
    update_payroll_import_row(row_ids[0], first.id, None)
    update_payroll_import_row(row_ids[1], second.id, None)
    first_run = accept_payroll_batch(batch_id)

    result = discard_pay_run(first_run.id)

    assert result["import_rows_reverted"] == 2
    with get_cursor() as cursor:
        rows = cursor.execute(
            "SELECT id, status, pay_run_id FROM payroll_import_rows "
            "WHERE batch_id = ? ORDER BY id", (batch_id,),
        ).fetchall()
        audits = cursor.execute(
            "SELECT table_name, old_values, new_values FROM audit_log "
            "WHERE (table_name = 'payroll_import_rows' AND action = 'UPDATE' "
            "AND json_extract(new_values, '$.reason') = 'pay run discarded') "
            "OR (action = 'DELETE' AND json_extract(new_values, '$.operation_id') "
            "IS NOT NULL) ORDER BY id"
        ).fetchall()
    assert [(row["id"], row["status"], row["pay_run_id"]) for row in rows] == [
        (row_ids[0], "pending", None), (row_ids[1], "pending", None),
    ]
    assert len(audits) == 5
    import_audits = [row for row in audits if row["table_name"] == "payroll_import_rows"]
    assert all(json.loads(row["old_values"])["pay_run_id"] == first_run.id
               for row in import_audits)
    assert len({json.loads(row["new_values"])["operation_id"] for row in audits}) == 1
    second_run = accept_payroll_batch(batch_id)
    assert second_run.id != first_run.id


def test_discard_rolls_back_when_import_row_changes(client_id, monkeypatch):
    import services.payroll_recording as payroll_recording

    employee = _employee(client_id, "Concurrent Row")
    batch_id = stage_payroll_rows(
        client_id, "gusto", "Payroll register", "register.csv",
        [_staged_row("Concurrent Row")],
    )
    with get_cursor() as cursor:
        row_id = cursor.execute(
            "SELECT id FROM payroll_import_rows WHERE batch_id = ?", (batch_id,),
        ).fetchone()["id"]
    update_payroll_import_row(row_id, employee.id, None)
    run = accept_payroll_batch(batch_id)
    real_get_connection = payroll_recording.get_connection

    class ZeroRowcountCursor:
        def __init__(self, cursor):
            self._cursor = cursor
            self.rowcount = cursor.rowcount

        def execute(self, sql, parameters=()):
            if sql.startswith("UPDATE payroll_import_rows SET status = 'pending'"):
                self._cursor.execute("SELECT 1")
                self.rowcount = 0
                return self
            result = self._cursor.execute(sql, parameters)
            self.rowcount = self._cursor.rowcount
            return result

        def __getattr__(self, name):
            return getattr(self._cursor, name)

    class PatchedConnection:
        def __init__(self, connection):
            self._connection = connection

        def cursor(self):
            return ZeroRowcountCursor(self._connection.cursor())

        def __getattr__(self, name):
            return getattr(self._connection, name)

    monkeypatch.setattr(
        payroll_recording, "get_connection",
        lambda: PatchedConnection(real_get_connection()),
    )

    with pytest.raises(
        ValueError, match="An import row changed during discard. Nothing was changed."
    ):
        discard_pay_run(run.id)

    with get_cursor() as cursor:
        assert cursor.execute(
            "SELECT COUNT(*) FROM pay_runs WHERE id = ?", (run.id,),
        ).fetchone()[0] == 1
        assert cursor.execute(
            "SELECT COUNT(*) FROM pay_stubs WHERE pay_run_id = ?", (run.id,),
        ).fetchone()[0] == 1
        row = cursor.execute(
            "SELECT status, pay_run_id FROM payroll_import_rows WHERE id = ?", (row_id,),
        ).fetchone()
    assert (row["status"], row["pay_run_id"]) == ("accepted", run.id)


def test_discard_leaves_dismissed_row_untouched(client_id):
    employee = _employee(client_id, "Rowan Crest")
    batch_id = stage_payroll_rows(
        client_id, "quickbooks", "Payroll details", "details.csv",
        [_staged_row("Rowan Crest"), _staged_row("Dismissed Rowan", 40000)],
    )
    run = create_pay_run(client_id, date(2026, 9, 1), date(2026, 9, 15),
                         date(2026, 9, 20))
    add_pay_stub(run.id, employee.id, 100000, [], 100000)
    with get_cursor(commit=True) as cursor:
        rows = cursor.execute(
            "SELECT id FROM payroll_import_rows WHERE batch_id = ? ORDER BY id", (batch_id,),
        ).fetchall()
        cursor.execute(
            "UPDATE payroll_import_rows SET status = 'accepted', pay_run_id = ? WHERE id = ?",
            (run.id, rows[0]["id"]),
        )
        cursor.execute(
            "UPDATE payroll_import_rows SET status = 'dismissed' WHERE id = ?",
            (rows[1]["id"],),
        )

    discard_pay_run(run.id)

    with get_cursor() as cursor:
        dismissed = cursor.execute(
            "SELECT status, pay_run_id FROM payroll_import_rows WHERE id = ?",
            (rows[1]["id"],),
        ).fetchone()
    assert (dismissed["status"], dismissed["pay_run_id"]) == ("dismissed", None)


def test_migration_backfills_newest_existing_run_and_ignores_deleted_run(db, client_id):
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("ALTER TABLE payroll_import_rows RENAME TO payroll_import_rows_with_link")
    conn.execute(
        "CREATE TABLE payroll_import_rows AS SELECT id, batch_id, employee_name_raw, "
        "matched_employee_id, department_raw, matched_department_id, pay_period_start, "
        "pay_period_end, pay_date, gross_pay_cents, deductions, employer_costs, "
        "net_pay_cents, raw_row, status FROM payroll_import_rows_with_link WHERE 0"
    )
    conn.execute("DROP TABLE payroll_import_rows_with_link")
    conn.execute(
        "INSERT INTO payroll_import_batches "
        "(id, client_id, provider, source_report, file_name) "
        "VALUES (1, ?, 'gusto', 'Register', 'register.csv')", (client_id,),
    )
    conn.execute(
        "INSERT INTO pay_runs "
        "(id, client_id, pay_period_start, pay_period_end, pay_date, status) "
        "VALUES (10, ?, '2026-09-01', '2026-09-15', '2026-09-20', 'draft')",
        (client_id,),
    )
    for row_id in (1, 2):
        conn.execute(
            "INSERT INTO payroll_import_rows "
            "(id, batch_id, employee_name_raw, deductions, status) "
            "VALUES (?, 1, 'Migration Employee', '[]', 'accepted')", (row_id,),
        )
    conn.execute(
        "INSERT INTO audit_log "
        "(client_id, table_name, record_id, action, new_values) "
        "VALUES (?, 'payroll_import_rows', 1, 'UPDATE', '{\"pay_run_id\":9}'), "
        "(?, 'payroll_import_rows', 1, 'UPDATE', '{\"pay_run_id\":10}'), "
        "(?, 'payroll_import_rows', 2, 'UPDATE', '{\"pay_run_id\":11}')",
        (client_id, client_id, client_id),
    )
    conn.execute(
        "DELETE FROM schema_migrations WHERE version = '904_payroll_import_row_pay_run'"
    )
    conn.commit()

    create_tables(conn)

    rows = conn.execute(
        "SELECT id, pay_run_id FROM payroll_import_rows ORDER BY id"
    ).fetchall()
    assert [(row["id"], row["pay_run_id"]) for row in rows] == [(1, 10), (2, None)]
    conn.close()
