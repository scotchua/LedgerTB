import sqlite3

import pytest

from database import schema


DOCUMENT_AUDIT_SQL = (
    "CREATE TABLE document_audits (id INTEGER PRIMARY KEY, doc_key TEXT);"
    "CREATE INDEX idx_document_audits_key ON document_audits (doc_key);"
)


def _document_audit_book(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY);"
        + DOCUMENT_AUDIT_SQL
    )
    return conn


def test_reconcile_document_audits_locks_schema_during_comparison(tmp_path):
    path = tmp_path / "cedar_studio.db"
    conn = _document_audit_book(path)
    rival = sqlite3.connect(path, timeout=0)

    class ConcurrentSchemaChange:
        def __init__(self):
            self.checked = False

        def execute(self, sql, *args):
            if "FROM sqlite_master" in sql and not self.checked:
                rows = conn.execute(sql, *args).fetchall()
                self.checked = True
                try:
                    rival.execute("DROP INDEX idx_document_audits_key")
                except sqlite3.OperationalError as exc:
                    assert "locked" in str(exc)
                else:
                    rival.commit()
                return rows
            return conn.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(conn, name)

    try:
        schema._reconcile_document_audits(
            ConcurrentSchemaChange(), DOCUMENT_AUDIT_SQL, "045_document_audits"
        )
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'idx_document_audits_key'"
        ).fetchone() == ("idx_document_audits_key",)
    finally:
        rival.close()
        conn.close()


def test_reconcile_document_audits_commits_tracking_row(tmp_path):
    path = tmp_path / "maple_design.db"
    conn = _document_audit_book(path)
    try:
        schema._reconcile_document_audits(
            conn, DOCUMENT_AUDIT_SQL, "045_document_audits"
        )
    finally:
        conn.close()
    with sqlite3.connect(path) as reopened:
        assert reopened.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall() == [("045_document_audits",)]


def test_reconcile_document_audits_rolls_back_on_schema_mismatch(tmp_path):
    conn = _document_audit_book(tmp_path / "spruce_media.db")
    try:
        conn.execute("DROP INDEX idx_document_audits_key")
        with pytest.raises(RuntimeError, match="Cannot reconcile"):
            schema._reconcile_document_audits(
                conn, DOCUMENT_AUDIT_SQL, "045_document_audits"
            )
        assert not conn.in_transaction
    finally:
        conn.close()


def test_create_tables_commits_tracking_table_with_no_migrations(tmp_path, monkeypatch):
    migration_dir = tmp_path / "empty_migrations"
    migration_dir.mkdir()
    monkeypatch.setattr(schema, "MIGRATIONS_DIR", migration_dir)
    path = tmp_path / "birch_books.db"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE setup_note (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO setup_note VALUES (1)")
        schema.create_tables(conn)
        assert not conn.in_transaction
        with sqlite3.connect(path) as reopened:
            assert reopened.execute("SELECT id FROM setup_note").fetchall() == [(1,)]
            assert reopened.execute(
                "SELECT name FROM sqlite_master WHERE name = 'schema_migrations'"
            ).fetchone() == ("schema_migrations",)
    finally:
        conn.close()


def test_create_tables_accepts_migration_without_final_semicolon(tmp_path, monkeypatch):
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "001_cedar.sql").write_text(
        "CREATE TABLE cedar_account (id INTEGER PRIMARY KEY)"
    )
    monkeypatch.setattr(schema, "MIGRATIONS_DIR", migration_dir)
    with sqlite3.connect(":memory:") as conn:
        schema.create_tables(conn)
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'cedar_account'"
        ).fetchone() == ("cedar_account",)
        assert conn.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall() == [("001_cedar",)]


def test_create_tables_does_not_heal_other_sql_errors(tmp_path, monkeypatch):
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "001_ash.sql").write_text(
        "ALTER TABLE absent_account ADD COLUMN reference TEXT;"
    )
    monkeypatch.setattr(schema, "MIGRATIONS_DIR", migration_dir)
    with sqlite3.connect(":memory:") as conn:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            schema.create_tables(conn)
        assert conn.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall() == []
