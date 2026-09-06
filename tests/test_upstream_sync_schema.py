"""Option A preserves the schema and data of books that ran 900--902."""

import sqlite3
from contextlib import closing

import pytest

from database import schema
from database.connection import _driver


RENAMED = {
    "043_account_grouping": "900_account_grouping",
    "044_cash_flow_section": "901_cash_flow_section",
    "045_document_audits": "902_document_audits",
}


@pytest.fixture
def legacy_migrations(tmp_path):
    directory = tmp_path / "legacy_migrations"
    directory.mkdir()
    for path in schema.MIGRATIONS_DIR.glob("*.sql"):
        stem = RENAMED.get(path.stem, path.stem)
        (directory / f"{stem}.sql").write_bytes(path.read_bytes())
    return directory


def _schema_by_table(conn):
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    )]
    result = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        indexes = conn.execute(f"PRAGMA index_list({quoted})").fetchall()
        result[table] = {
            "ddl": [
                (kind, name, " ".join(sql.split()) if sql else None)
                for kind, name, sql in conn.execute(
                    "SELECT type, name, sql FROM sqlite_master "
                    "WHERE tbl_name = ? ORDER BY type, name", (table,)
                )
            ],
            "columns": conn.execute(f"PRAGMA table_xinfo({quoted})").fetchall(),
            "foreign_keys": conn.execute(
                f"PRAGMA foreign_key_list({quoted})"
            ).fetchall(),
            "indexes": sorted(tuple(row[1:]) for row in indexes),
            "index_columns": {
                row[1]: conn.execute(
                    'PRAGMA index_xinfo("' + row[1].replace('"', '""') + '")'
                ).fetchall()
                for row in indexes
            },
        }
    return result


def _business_rows(conn):
    return {
        table: conn.execute(
            'SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid'
        ).fetchall()
        for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name != 'schema_migrations' ORDER BY name"
        )
    }


def _versions(conn):
    return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}


@pytest.mark.parametrize("populated", [False, True])
@pytest.mark.parametrize("driver", [sqlite3, _driver], ids=["sqlite", "book_driver"])
def test_fresh_and_900_upgraded_books_have_identical_schema(
    legacy_migrations, monkeypatch, populated, driver,
):
    with closing(sqlite3.connect(":memory:")) as fresh, closing(
        driver.connect(":memory:")
    ) as upgraded:
        schema.create_tables(fresh)
        with monkeypatch.context() as legacy:
            legacy.setattr(schema, "MIGRATIONS_DIR", legacy_migrations)
            schema.create_tables(upgraded)
        assert set(RENAMED.values()).issubset(_versions(upgraded))
        assert not set(RENAMED).intersection(_versions(upgraded))

        if populated:
            upgraded.executescript("""
                INSERT INTO clients (id, name, entity_type)
                VALUES (1, 'Fixture Workshop', 'S-Corp');
                INSERT INTO accounts
                    (id, client_id, account_number, name, type,
                     account_grouping, cash_flow_section)
                VALUES (1, 1, '1800', 'Fixture note', 'Asset',
                        'Advances', 'operating');
                INSERT INTO audit_log (id, client_id, table_name, record_id, action)
                VALUES (1, 1, 'accounts', 1, 'INSERT');
                INSERT INTO document_audits
                    (id, client_id, doc_type, doc_key, content_hash,
                     canonicalization_version, audit_log_id)
                VALUES (1, 1, 'statement', 'fixture-2026',
                        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                        1, 1);
            """)
        before = _business_rows(upgraded)
        schema.create_tables(upgraded)
        schema.create_tables(upgraded)

        fresh_schema = _schema_by_table(fresh)
        upgraded_schema = _schema_by_table(upgraded)
        assert fresh_schema.keys() == upgraded_schema.keys()
        for table in fresh_schema:
            assert fresh_schema[table] == upgraded_schema[table], table
        after = _business_rows(upgraded)
        for table, rows in before.items():
            assert after[table] == rows, table
        assert _versions(upgraded) == _versions(fresh) | set(RENAMED.values())
        assert len(_versions(fresh)) == 52
        for conn in (fresh, upgraded):
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
            assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


@pytest.mark.parametrize("damage", [
    "missing_table", "missing_client_index", "missing_doc_key_index",
    "missing_audit_log_index", "wrong_column", "missing_check",
    "wrong_foreign_key", "wrong_index", "extra_trigger",
])
def test_document_audit_reconciliation_rejects_incomplete_or_wrong_schema(
    legacy_migrations, monkeypatch, damage,
):
    path = legacy_migrations / "902_document_audits.sql"
    sql = path.read_text()
    if damage == "wrong_column":
        sql = sql.replace("canonicalization_version INTEGER", "canonicalization_version TEXT")
    elif damage == "missing_check":
        sql = sql.replace("length(content_hash) = 64", "length(content_hash) > 0")
    elif damage == "wrong_foreign_key":
        sql = sql.replace("REFERENCES audit_log(id)", "REFERENCES clients(id)")
    elif damage == "wrong_index":
        sql = sql.replace("document_audits(doc_type, doc_key)", "document_audits(doc_key, doc_type)")
    path.write_text(sql)

    with closing(sqlite3.connect(":memory:")) as conn:
        with monkeypatch.context() as legacy:
            legacy.setattr(schema, "MIGRATIONS_DIR", legacy_migrations)
            schema.create_tables(conn)
        if damage == "missing_table":
            conn.execute("DROP TABLE document_audits")
        elif damage.startswith("missing_") and damage.endswith("_index"):
            suffix = damage.removeprefix("missing_").removesuffix("_index")
            conn.execute(f"DROP INDEX idx_document_audits_{suffix}")
        elif damage == "extra_trigger":
            conn.executescript("""
                CREATE TRIGGER document_audits_ignore BEFORE INSERT ON document_audits
                BEGIN SELECT RAISE(IGNORE); END;
            """)
        conn.commit()
        before = _schema_by_table(conn)

        for _ in range(2):
            with pytest.raises(RuntimeError, match="Cannot reconcile 902_document_audits"):
                schema.create_tables(conn)
            assert "902_document_audits" in _versions(conn)
            assert "045_document_audits" not in _versions(conn)
            assert _schema_by_table(conn) == before


def test_document_audit_reconciliation_requires_legacy_tracking(legacy_migrations, monkeypatch):
    with closing(sqlite3.connect(":memory:")) as conn:
        with monkeypatch.context() as legacy:
            legacy.setattr(schema, "MIGRATIONS_DIR", legacy_migrations)
            schema.create_tables(conn)
        conn.execute("DELETE FROM schema_migrations WHERE version = '902_document_audits'")
        conn.commit()
        with pytest.raises(sqlite3.OperationalError, match="table document_audits already exists"):
            schema.create_tables(conn)
        assert "045_document_audits" not in _versions(conn)


def test_migration_numbers_are_unique_after_option_a():
    paths = sorted(schema.MIGRATIONS_DIR.glob("*.sql"))
    numbers = [path.stem.split("_", 1)[0] for path in paths]
    assert len(numbers) == len(set(numbers))
    stems = {path.stem for path in paths}
    assert set(RENAMED).issubset(stems)
    assert not set(RENAMED.values()).intersection(stems)
