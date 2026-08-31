import sqlite3

import pytest

from database.schema import MIGRATIONS_DIR


MIGRATION = MIGRATIONS_DIR / "042_ar_ap_chronology.sql"


def _schema_before_chronology():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if migration.name >= MIGRATION.name:
            break
        conn.executescript(migration.read_text())
    return conn


def test_chronology_migration_backfills_effective_dates_and_enforces_writers():
    conn = _schema_before_chronology()
    conn.execute("INSERT INTO clients (id, name) VALUES (1, 'Example Co')")
    conn.execute("INSERT INTO customers (id, client_id, name) VALUES (1, 1, 'Customer')")
    conn.execute(
        "INSERT INTO vendors (id, client_id, name, normalized_name) "
        "VALUES (1, 1, 'Vendor', 'vendor')"
    )
    conn.execute(
        "INSERT INTO accounts (id, client_id, account_number, name, type) "
        "VALUES (1, 1, '1100', 'Receivable', 'Asset')"
    )
    for entry_id, entry_date in ((1, "2026-01-10"), (2, "2026-01-05")):
        conn.execute(
            "INSERT INTO journal_entries (id, client_id, entry_date, description) "
            "VALUES (?, 1, ?, 'Existing entry')", (entry_id, entry_date),
        )
    for invoice_id, invoice_date in ((1, "2026-01-15"), (2, "2026-01-12")):
        conn.execute(
            "INSERT INTO invoices "
            "(id, client_id, customer_id, invoice_date, due_date, status, control_account_id) "
            "VALUES (?, 1, 1, ?, '2026-02-15', 'posted', 1)",
            (invoice_id, invoice_date),
        )
    conn.execute(
        "INSERT INTO invoices "
        "(id, client_id, customer_id, invoice_date, due_date, status, control_account_id) "
        "VALUES (3, 1, 1, '2026-03-10', '2026-03-09', 'draft', 1)"
    )
    conn.execute(
        "INSERT INTO bills "
        "(id, client_id, vendor_id, bill_date, due_date, status, control_account_id) "
        "VALUES (1, 1, 1, '2026-01-15', '2026-01-14', 'posted', 1)"
    )
    conn.execute(
        "INSERT INTO payments "
        "(id, client_id, customer_id, payment_date, amount_cents, deposit_account_id, "
        "control_account_id, journal_entry_id) VALUES (1, 1, 1, '2026-01-10', 2000, 1, 1, 1)"
    )
    conn.execute(
        "INSERT INTO payment_allocations "
        "(id, payment_id, invoice_id, amount_cents, applied_later) "
        "VALUES (1, 1, 1, 1000, 0), (2, 1, 2, 1000, 1)"
    )
    conn.execute(
        "INSERT INTO bill_payments_v2 "
        "(id, client_id, vendor_id, payment_date, amount_cents, payment_account_id, "
        "control_account_id, journal_entry_id) VALUES (1, 1, 1, '2026-01-10', 1000, 1, 1, 1)"
    )
    conn.execute(
        "INSERT INTO bill_payment_allocations "
        "(id, payment_id, bill_id, amount_cents, applied_later) VALUES (1, 1, 1, 1000, 1)"
    )
    conn.execute(
        "INSERT INTO credit_memos "
        "(id, client_id, customer_id, memo_date, status, control_account_id, journal_entry_id) "
        "VALUES (1, 1, 1, '2026-01-05', 'posted', 1, 2)"
    )
    conn.execute(
        "INSERT INTO credit_applications "
        "(id, credit_memo_id, invoice_id, amount_cents) VALUES (1, 1, 1, 500)"
    )
    for table_name, record_id, changed_at in (
        ("payment_allocations", 2, "2026-01-20 09:00:00"),
        ("bill_payment_allocations", 1, "2026-01-22 09:00:00"),
        ("credit_applications", 1, "2026-01-25 09:00:00"),
    ):
        conn.execute(
            "INSERT INTO audit_log "
            "(client_id, table_name, record_id, action, changed_at) "
            "VALUES (1, ?, ?, 'INSERT', ?)",
            (table_name, record_id, changed_at),
        )
    conn.commit()

    conn.executescript(MIGRATION.read_text())

    assert [row[0] for row in conn.execute(
        "SELECT application_date FROM payment_allocations ORDER BY id"
    )] == ["2026-01-15", "2026-01-20"]
    assert conn.execute(
        "SELECT application_date FROM bill_payment_allocations WHERE id = 1"
    ).fetchone()[0] == "2026-01-22"
    assert conn.execute(
        "SELECT application_date FROM credit_applications WHERE id = 1"
    ).fetchone()[0] == "2026-01-25"
    assert conn.execute("SELECT due_date FROM invoices WHERE id = 3").fetchone()[0] == "2026-03-10"
    assert conn.execute("SELECT due_date FROM bills WHERE id = 1").fetchone()[0] == "2026-01-15"
    assert [tuple(row) for row in conn.execute(
        "SELECT table_name, record_id, performed_by FROM audit_log "
        "WHERE performed_by = 'LedgerTB migration 042' ORDER BY table_name"
    )] == [
        ("bills", 1, "LedgerTB migration 042"),
        ("invoices", 3, "LedgerTB migration 042"),
    ]

    with pytest.raises(sqlite3.IntegrityError, match="due date cannot precede"):
        conn.execute(
            "INSERT INTO invoices "
            "(client_id, customer_id, invoice_date, due_date) "
            "VALUES (1, 1, '2026-03-10', '2026-03-09')"
        )
    with pytest.raises(sqlite3.IntegrityError, match="application date is invalid"):
        conn.execute(
            "UPDATE payment_allocations SET application_date = '2026-01-14' WHERE id = 1"
        )
    conn.close()
