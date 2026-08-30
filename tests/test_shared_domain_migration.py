import sqlite3

import pytest

from database.connection import get_connection
from database.schema import MIGRATIONS_DIR, create_tables


MIGRATION = MIGRATIONS_DIR / "035_shared_domain_contracts.sql"
LEGACY_STATUSES = ("draft", "posted", "paid", "partially_paid")


def _schema_rows(conn, object_type, table):
    return [
        tuple(row)
        for row in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = ? AND tbl_name = ? ORDER BY name",
            (object_type, table),
        )
    ]


def _foreign_keys(conn, table):
    return {
        (row["table"], row["from"], row["to"], row["on_update"], row["on_delete"])
        for row in conn.execute(f"PRAGMA foreign_key_list({table})")
    }


def test_shared_domain_migration_applies_fresh_and_create_tables_is_idempotent(db):
    conn = get_connection()

    assert conn.execute(
        "SELECT COUNT(*) FROM schema_migrations "
        "WHERE version = '035_shared_domain_contracts'"
    ).fetchone()[0] == 1

    create_tables(conn)
    create_tables(conn)

    assert conn.execute(
        "SELECT COUNT(*) FROM schema_migrations "
        "WHERE version = '035_shared_domain_contracts'"
    ).fetchone()[0] == 1
    conn.close()


def test_rebuild_preserves_rows_statuses_indexes_and_foreign_keys():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if migration.name >= MIGRATION.name:
            break
        conn.executescript(migration.read_text())

    conn.execute("INSERT INTO clients (id, name) VALUES (1, 'Example Co')")
    conn.execute(
        "INSERT INTO customers (id, client_id, name, email) "
        "VALUES (1, 1, 'Example Customer', 'billing@example.test')"
    )
    conn.execute(
        "INSERT INTO vendors (id, client_id, name, normalized_name, email) "
        "VALUES (1, 1, 'Example Vendor', 'example vendor', 'ap@example.test')"
    )
    conn.execute(
        "INSERT INTO journal_entries "
        "(id, client_id, entry_date, description, entry_type, created_by) "
        "VALUES (1, 1, '2026-08-01', 'Existing entry', 'Regular', 'tester')"
    )
    for row_id, status in enumerate(LEGACY_STATUSES, 1):
        conn.execute(
            "INSERT INTO invoices "
            "(id, client_id, customer_id, invoice_date, due_date, status, journal_entry_id) "
            "VALUES (?, 1, 1, '2026-08-01', '2026-08-31', ?, 1)",
            (row_id, status),
        )
        conn.execute(
            "INSERT INTO bills "
            "(id, client_id, vendor_id, bill_date, due_date, status, journal_entry_id) "
            "VALUES (?, 1, 1, '2026-08-02', '2026-09-01', ?, 1)",
            (row_id, status),
        )
    conn.commit()

    before_rows = {
        table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
        for table in ("invoices", "bills")
    }
    before_indexes = {
        table: _schema_rows(conn, "index", table) for table in ("invoices", "bills")
    }
    before_foreign_keys = {
        table: _foreign_keys(conn, table) for table in ("invoices", "bills")
    }

    conn.executescript(MIGRATION.read_text())

    for table in ("invoices", "bills"):
        rows = [tuple(row) for row in conn.execute(
            f"SELECT * FROM {table} ORDER BY id"
        )]
        assert [row[:-1] for row in rows] == before_rows[table]
        assert all(row[-1] is None for row in rows)
        assert _schema_rows(conn, "index", table) == before_indexes[table]
        void_fk = (
            "journal_entries", "voided_journal_entry_id", "id",
            "NO ACTION", "NO ACTION"
        )
        assert _foreign_keys(conn, table) == before_foreign_keys[table] | {void_fk}

    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_voided_and_all_legacy_statuses_are_accepted(db, client_id):
    conn = get_connection()
    conn.execute(
        "INSERT INTO customers (client_id, name) VALUES (?, 'Status Customer')",
        (client_id,),
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO vendors (client_id, name, normalized_name) "
        "VALUES (?, 'Status Vendor', 'status vendor')",
        (client_id,),
    )
    vendor_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for status in (*LEGACY_STATUSES, "voided"):
        conn.execute(
            "INSERT INTO invoices "
            "(client_id, customer_id, invoice_date, due_date, status) "
            "VALUES (?, ?, '2026-08-01', '2026-08-31', ?)",
            (client_id, customer_id, status),
        )
        conn.execute(
            "INSERT INTO bills "
            "(client_id, vendor_id, bill_date, due_date, status) "
            "VALUES (?, ?, '2026-08-01', '2026-08-31', ?)",
            (client_id, vendor_id, status),
        )

    assert {row[0] for row in conn.execute("SELECT status FROM invoices")} >= {
        *LEGACY_STATUSES, "voided"
    }
    assert {row[0] for row in conn.execute("SELECT status FROM bills")} >= {
        *LEGACY_STATUSES, "voided"
    }
    conn.rollback()
    conn.close()


def test_departments_are_unique_within_a_client(db, client_id):
    conn = get_connection()
    conn.execute(
        "INSERT INTO departments (client_id, name) VALUES (?, 'Operations')",
        (client_id,),
    )

    with pytest.raises(Exception, match="UNIQUE constraint failed"):
        conn.execute(
            "INSERT INTO departments (client_id, name) VALUES (?, 'Operations')",
            (client_id,),
        )
    conn.execute("INSERT INTO clients (name) VALUES ('Second Example Co')")
    other_client_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO departments (client_id, name) VALUES (?, 'Operations')",
        (other_client_id,),
    )
    conn.rollback()
    conn.close()


def test_inventory_source_link_rejects_duplicates_and_allows_nulls(
    db, client_id, accounts
):
    conn = get_connection()
    conn.execute(
        "INSERT INTO inventory_items "
        "(client_id, sku, description, inventory_account_id, cogs_account_id) "
        "VALUES (?, 'SHARED-1', 'Shared item', ?, ?)",
        (client_id, accounts["cash"], accounts["expense"]),
    )
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    movement = (
        item_id, "2026-08-01", "sale", 1, 100, "invoice", 42, 7
    )
    conn.execute(
        "INSERT INTO inventory_movements "
        "(inventory_item_id, movement_date, movement_type, quantity, unit_cost_cents, "
        "source_type, source_id, source_line_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        movement,
    )

    with pytest.raises(Exception, match="UNIQUE constraint failed"):
        conn.execute(
            "INSERT INTO inventory_movements "
            "(inventory_item_id, movement_date, movement_type, quantity, unit_cost_cents, "
            "source_type, source_id, source_line_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            movement,
        )

    conn.execute(
        "INSERT INTO inventory_movements "
        "(inventory_item_id, movement_date, movement_type, quantity) "
        "VALUES (?, '2026-08-02', 'adjustment', 1)",
        (item_id,),
    )
    conn.execute(
        "INSERT INTO inventory_movements "
        "(inventory_item_id, movement_date, movement_type, quantity) "
        "VALUES (?, '2026-08-03', 'adjustment', 1)",
        (item_id,),
    )
    assert conn.execute(
        "SELECT COUNT(*) FROM inventory_movements WHERE source_type IS NULL"
    ).fetchone()[0] == 2
    conn.rollback()
    conn.close()
