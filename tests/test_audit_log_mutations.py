"""Dependency-light behavioral checks for the audit log model."""

import importlib.util
import os
import sqlite3
import sys
import types
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def audit(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY, client_id INTEGER, table_name TEXT,
            record_id INTEGER, action TEXT, old_values TEXT, new_values TEXT,
            session_id TEXT, changed_at TEXT, performed_by TEXT
        )"""
    )

    @contextmanager
    def get_cursor(commit=False):
        cursor = connection.cursor()
        try:
            yield cursor
            if commit:
                connection.commit()
        finally:
            cursor.close()

    database = types.ModuleType("database")
    database.__path__ = []
    database_connection = types.ModuleType("database.connection")
    database_connection.get_cursor = get_cursor
    monkeypatch.setitem(sys.modules, "database", database)
    monkeypatch.setitem(sys.modules, "database.connection", database_connection)

    source = Path(os.environ.get(
        "AUDIT_LOG_MUTANT_FILE", Path(__file__).parents[1] / "models" / "audit_log.py"
    ))
    spec = importlib.util.spec_from_file_location("_audit_log_under_test", source)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    yield module.AuditLog, connection
    connection.close()


def _row(db, client, table, record, action, when="2026-04-01 12:00:00",
         old=None, new=None, actor="Morgan"):
    return db.execute(
        """INSERT INTO audit_log
           (client_id, table_name, record_id, action, old_values, new_values,
            session_id, changed_at, performed_by)
           VALUES (?, ?, ?, ?, ?, ?, 'session-7', ?, ?)""",
        (client, table, record, action, old, new, when, actor),
    ).lastrowid


def test_get_session_id_reuses_value(audit, monkeypatch):
    AuditLog, _ = audit
    class State(dict):
        __getattr__ = dict.__getitem__
    state = State()
    streamlit = types.ModuleType("streamlit")
    streamlit.session_state = state
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    monkeypatch.setattr("uuid.uuid4", lambda: "invented-session")
    assert AuditLog.get_session_id() == "invented-session"
    assert AuditLog.get_session_id() == "invented-session"


def test_current_session_id_selects_context(audit, monkeypatch):
    AuditLog, _ = audit
    runner = types.ModuleType("streamlit.runtime.scriptrunner")
    runner.get_script_run_ctx = lambda suppress_warning: object()
    monkeypatch.setitem(sys.modules, "streamlit.runtime", types.ModuleType("streamlit.runtime"))
    monkeypatch.setitem(sys.modules, "streamlit.runtime.scriptrunner", runner)
    monkeypatch.setattr(AuditLog, "get_session_id", lambda: "app-session")
    assert AuditLog._current_session_id() == "app-session"
    runner.get_script_run_ctx = lambda suppress_warning: None
    monkeypatch.setattr("uuid.uuid4", lambda: "request-session")
    assert AuditLog._current_session_id() == "request-session"


def test_json_serializes_dates_and_empty_values(audit):
    AuditLog, _ = audit
    assert AuditLog._json(None) is None
    assert AuditLog._json({"z": datetime(2026, 4, 1, 8), "a": 0}) == (
        '{"a": 0, "z": "2026-04-01T08:00:00"}'
    )


def test_write_rejects_unknown_action(audit):
    AuditLog, db = audit
    with pytest.raises(ValueError, match="Unsupported audit action"):
        AuditLog.write(db.cursor(), 7, "invented_accounts", 4, "ARCHIVE")
    assert db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_write_records_payload_and_supplied_session(audit, monkeypatch):
    AuditLog, db = audit
    monkeypatch.setattr("utils.actor.current_actor", lambda: "Morgan")
    log_id = AuditLog.write(db.cursor(), 7, "invented_accounts", 4, "UPDATE",
                            {"balance": 12}, {"balance": 13}, "session-7")
    row = db.execute("SELECT * FROM audit_log WHERE id = ?", (log_id,)).fetchone()
    assert (row["client_id"], row["table_name"], row["record_id"], row["action"]) == (
        7, "invented_accounts", 4, "UPDATE"
    )
    assert (row["old_values"], row["new_values"], row["session_id"], row["performed_by"]) == (
        '{"balance": 12}', '{"balance": 13}', "session-7", "Morgan"
    )
    assert abs((datetime.now() - datetime.fromisoformat(row["changed_at"])).total_seconds()) < 5


def test_log_change_returns_persisted_id(audit, monkeypatch):
    AuditLog, db = audit
    monkeypatch.setattr("utils.actor.current_actor", lambda: "Morgan")
    log_id = AuditLog.log_change(7, "invented_accounts", 4, "INSERT", new_values={"x": 1})
    assert db.execute("SELECT new_values FROM audit_log WHERE id = ?", (log_id,)).fetchone()[0] == '{"x": 1}'


def test_log_event_maps_event_fields(audit, monkeypatch):
    AuditLog, db = audit
    monkeypatch.setattr("utils.actor.current_actor", lambda: "Morgan")
    log_id = AuditLog.log_event(None, "BACKUP", "invented_backup", {"copies": 2}, 9)
    row = db.execute("SELECT * FROM audit_log WHERE id = ?", (log_id,)).fetchone()
    assert (row["client_id"], row["table_name"], row["record_id"], row["action"],
            row["new_values"]) == (None, "invented_backup", 9, "BACKUP", '{"copies": 2}')


def test_log_change_safe_returns_successful_id(audit, monkeypatch):
    AuditLog, _ = audit
    monkeypatch.setattr(AuditLog, "log_change", lambda **kwargs: 81)
    assert AuditLog.log_change_safe(7, "invented_accounts", 4, "INSERT") == 81


def test_log_change_safe_returns_none_after_failure(audit, monkeypatch):
    AuditLog, _ = audit
    def fail(**kwargs):
        raise RuntimeError("invented write failure")
    monkeypatch.setattr(AuditLog, "log_change", fail)
    assert AuditLog.log_change_safe(7, "invented_accounts", 4, "INSERT") is None


def test_get_by_id_decodes_fields_and_missing_row(audit):
    AuditLog, db = audit
    log_id = _row(db, 7, "invented_accounts", 4, "UPDATE", old='{"x": 1}', new='{"x": 2}')
    log = AuditLog.get_by_id(log_id)
    assert (log.id, log.old_values, log.new_values, log.changed_at, log.session_id) == (
        log_id, {"x": 1}, {"x": 2}, datetime(2026, 4, 1, 12), "session-7"
    )
    assert AuditLog.get_by_id(9999) is None


def test_get_earliest_date_includes_book_events_but_excludes_other_clients(audit):
    AuditLog, db = audit
    _row(db, 8, "invented_accounts", 1, "INSERT", "2026-01-01 00:00:00")
    _row(db, 7, "invented_accounts", 2, "INSERT", "2026-03-01 00:00:00")
    _row(db, None, "invented_backup", 0, "BACKUP", "2026-02-01 00:00:00")
    assert AuditLog.get_earliest_date(7) == datetime(2026, 2, 1)


def test_get_earliest_date_returns_none_for_empty_trail(audit):
    AuditLog, _ = audit
    assert AuditLog.get_earliest_date(7) is None


def test_get_history_orders_ties_and_decodes_actor(audit):
    AuditLog, db = audit
    first = _row(db, 7, "invented_accounts", 4, "INSERT", new='{"x": 1}')
    second = _row(db, 7, "invented_accounts", 4, "UPDATE", old='{"x": 1}')
    _row(db, 7, "invented_accounts", 5, "INSERT")
    logs = AuditLog.get_history("invented_accounts", 4)
    assert [log.id for log in logs] == [second, first]
    assert logs[0].old_values == {"x": 1}
    assert logs[0].performed_by == "Morgan"


def test_get_all_filters_inclusive_dates_and_pages(audit):
    AuditLog, db = audit
    _row(db, 8, "invented_accounts", 1, "INSERT")
    first = _row(db, 7, "invented_accounts", 2, "INSERT", "2026-04-01 09:00:00")
    second = _row(db, 7, "invented_accounts", 3, "UPDATE", "2026-04-01 10:00:00")
    _row(db, 7, "invented_accounts", 4, "DELETE", "2026-04-02 00:00:00")
    logs = AuditLog.get_all(7, datetime(2026, 4, 1, 9), datetime(2026, 4, 1, 10),
                            limit=1, offset=1)
    assert [log.id for log in logs] == [first]
    assert [log.id for log in AuditLog.get_all(
        7, end_date=datetime(2026, 4, 1, 10), limit=1, offset=0
    )] == [second]


def test_filter_sql_searches_old_and_new_values(audit):
    AuditLog, db = audit
    old_id = _row(db, 7, "invented_accounts", 1, "UPDATE", old='{"memo": "needle"}')
    new_id = _row(db, 7, "invented_accounts", 2, "UPDATE", new='{"memo": "needle"}')
    _row(db, 7, "invented_accounts", 3, "DELETE", old='{"memo": "needle"}')
    _row(db, 7, "other_table", 4, "UPDATE", new='{"memo": "needle"}')
    logs = AuditLog.get_all(7, table_name="invented_accounts", action="UPDATE",
                            search_term="needle")
    assert {log.id for log in logs} == {old_id, new_id}


def test_get_filtered_counts_covers_actions_and_book_events(audit):
    AuditLog, db = audit
    for action in ("INSERT", "UPDATE", "DELETE", "BACKUP"):
        _row(db, 7 if action != "BACKUP" else None, "invented_accounts", 1, action)
    _row(db, 8, "invented_accounts", 1, "INSERT")
    assert AuditLog.get_filtered_counts(7) == {
        "total": 4, "inserts": 1, "updates": 1, "deletes": 1, "events": 1
    }


def test_get_entry_changes_matches_entry_and_lines_for_one_client(audit):
    AuditLog, db = audit
    entry = _row(db, 7, "journal_entries", 4, "INSERT")
    line = _row(db, 7, "journal_entry_lines", 25, "INSERT",
                new='{"journal_entry_id": 4, "amount": 12}')
    _row(db, 8, "journal_entries", 4, "INSERT")
    _row(db, 7, "journal_entry_lines", 26, "INSERT", new='{"journal_entry_id": 5}')
    assert {log.id for log in AuditLog.get_entry_changes(7, 4)} == {entry, line}


@pytest.mark.xfail(strict=True, reason="LIKE also matches journal_entry_id 40 when querying 4")
def test_get_entry_changes_does_not_match_partial_entry_id(audit):
    AuditLog, db = audit
    _row(db, 7, "journal_entry_lines", 26, "INSERT", new='{"journal_entry_id": 40}')
    assert AuditLog.get_entry_changes(7, 4) == []


def test_format_changes_reports_only_changed_values(audit):
    AuditLog, _ = audit
    assert AuditLog(action="INSERT", new_values={"name": "Invented Co"}).format_changes() == (
        "Created with: name=Invented Co"
    )
    assert AuditLog(action="DELETE", old_values={"name": "Invented Co"}).format_changes() == (
        "Deleted: name=Invented Co"
    )
    assert AuditLog(action="UPDATE", old_values={"amount": 12, "same": 1},
                    new_values={"amount": 13, "same": 1}).format_changes() == (
        "amount: 12 -> 13"
    )
    assert AuditLog(action="UPDATE", old_values={"amount": 12},
                    new_values={"amount": 12}).format_changes() == "Updated"


def test_format_values_omits_internal_fields(audit):
    AuditLog, _ = audit
    values = {"id": 4, "created_at": "2026-04-01", "client_id": 7, "amount": 12}
    assert AuditLog()._format_values(values) == "amount=12"
