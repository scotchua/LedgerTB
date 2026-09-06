from database.connection import get_connection
from database.schema import create_tables
from database.schema import MIGRATIONS_DIR


def test_create_tables_builds_full_schema(db):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cur.fetchall()}
    conn.close()

    expected = {
        "accounts", "audit_log", "categorization_rules", "clients",
        "fiscal_periods", "imported_transactions", "journal_entries",
        "journal_entry_lines", "schema_migrations", "vendors",
        "bank_reconciliations", "bank_reconciliation_items",
        "import_profiles", "review_policies", "firm_branding",
        "book_identity", "client_branding", "client_branding_proposals",
        "import_batch_reversals", "document_audits",
        "journal_entry_templates", "journal_entry_template_lines",
        "recurring_schedules", "recurring_occurrences",
        "recurring_occurrence_drafts",
    }
    assert expected.issubset(tables)


def test_create_tables_records_migrations(db):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT version FROM schema_migrations ORDER BY version")
    assert [row[0] for row in cur.fetchall()] == [
        "001_initial_schema", "002_money_to_cents", "003_client_info",
        "004_bank_reconciliation", "005_audit_events", "006_import_idempotency",
        "007_import_profiles", "008_multiple_import_profiles",
        "009_activity_actor", "010_review_policies",
        "011_firm_branding", "012_draft_entries", "013_import_dismissal",
        "014_assistant_review", "015_review_action", "016_book_identity",
        "017_close_map", "018_client_branding", "019_draft_correction_links",
        "020_book_audit_events", "021_import_batch_reversal",
        # Upstream's own numbers sit where upstream put them.
        "022_client_business_context", "023_app_preferences",
        "024_recurring_journal_entries",
        "025_inventory", "026_bank_connections",
        "027_bank_connection_syncs", "028_fixed_assets",
        "029_payroll_recording", "030_vendor_email",
        "031_vendor_created_at", "032_ar_ap",
        "033_depreciation_draft_links", "034_bank_feed_remote_accounts",
        "035_shared_domain_contracts", "036_ar_ap_allocations",
        "037_payroll_import_staging", "038_invoice_inventory",
        "039_sales_tax_credit_memos", "040_email_log", "041_immutable_journal_entries",
        "042_ar_ap_chronology",
        # Option A renumbers only these three; new fork migrations stay 900+.
        "043_account_grouping", "044_cash_flow_section",
        "045_document_audits", "903_import_suggestions",
        "904_payroll_import_row_pay_run", "905_journal_entry_reversal_kind",
        "906_report_legend", "907_client_accounting_basis",
        "908_pay_stub_employer_costs", "909_counterparties"]
    conn.close()


def test_create_tables_is_idempotent(db):
    """Re-running create_tables (as init_database() does on every app start)
    must not error or re-apply an already-applied migration."""
    conn = get_connection()
    create_tables(conn)
    create_tables(conn)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM schema_migrations")
    assert cur.fetchone()[0] == 52
    conn.close()


def test_employer_cost_migration_defaults_existing_stubs_to_empty_list():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE pay_stubs ("
        "id INTEGER PRIMARY KEY, pay_run_id INTEGER NOT NULL, "
        "employee_id INTEGER NOT NULL, gross_pay_cents INTEGER NOT NULL, "
        "deductions TEXT NOT NULL, net_pay_cents INTEGER NOT NULL);"
        "INSERT INTO pay_stubs VALUES (1, 1, 1, 10000, '[]', 10000);"
    )

    conn.executescript(
        (MIGRATIONS_DIR / "908_pay_stub_employer_costs.sql").read_text()
    )

    row = conn.execute(
        "SELECT employer_costs FROM pay_stubs WHERE id = 1"
    ).fetchone()
    assert row["employer_costs"] == "[]"
    conn.close()


def test_book_identity_is_stable_across_schema_initialization(db):
    conn = get_connection()
    before = conn.execute(
        "SELECT book_id FROM book_identity WHERE id = 1"
    ).fetchone()[0]
    conn.close()

    conn = get_connection()
    create_tables(conn)
    after = conn.execute(
        "SELECT book_id FROM book_identity WHERE id = 1"
    ).fetchone()[0]
    conn.close()

    assert before == after
    assert len(before) == 32


def test_actor_columns_exist(db):
    conn = get_connection()
    cur = conn.cursor()
    for table, column in [("audit_log", "performed_by"),
                          ("journal_entries", "created_by"),
                          ("imported_transactions", "created_by"),
                          ("imported_transactions", "dismissed_at"),
                          ("imported_transactions", "dismissed_by"),
                          ("imported_transactions", "superseded_by_batch"),
                          ("imported_transactions", "reversal_journal_entry_id"),
                          ("imported_transactions", "replaces_transaction_id")]:
        cur.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in cur.fetchall()}
        assert column in columns, f"{table} missing {column}"
    conn.close()


def test_import_suggestion_schema_exists(db):
    conn = get_connection()
    columns = {row[1] for row in conn.execute(
        "PRAGMA table_info(imported_transactions)"
    ).fetchall()}
    assert {"decided_account_id", "decided_at", "decided_by",
            "decided_suggestion_id"}.issubset(columns)
    triggers = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' "
        "AND name LIKE 'import_suggestions_%'"
    ).fetchall()}
    assert triggers == {"import_suggestions_same_client", "import_suggestions_undecided"}
    conn.close()


def test_client_business_context_column_exists(db):
    conn = get_connection()
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(clients)").fetchall()
    }
    conn.close()

    assert "business_context" in columns


def test_multiple_profile_migration_preserves_existing_mapping():
    """The original one-per-account profile becomes a named legacy format."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE clients (id INTEGER PRIMARY KEY);"
        "CREATE TABLE accounts (id INTEGER PRIMARY KEY, client_id INTEGER);"
        "INSERT INTO clients VALUES (1);"
        "INSERT INTO accounts VALUES (10, 1);"
    )
    conn.executescript((MIGRATIONS_DIR / "007_import_profiles.sql").read_text())
    conn.execute(
        """
        INSERT INTO import_profiles
            (client_id, bank_account_id, date_column, description_column,
             amount_format, amount_column, sign_convention)
        VALUES (1, 10, 'Posted Date', 'Merchant', 'single', 'Net Amount', 'bank')
        """
    )
    conn.executescript(
        (MIGRATIONS_DIR / "008_multiple_import_profiles.sql").read_text()
    )

    row = conn.execute("SELECT * FROM import_profiles").fetchone()
    assert row["name"] == "Default"
    assert row["date_column"] == "Posted Date"
    assert row["amount_column"] == "Net Amount"
    assert row["header_signature"] is None
    conn.close()


def test_migration_failure_is_atomic(tmp_path, monkeypatch):
    """M10: if a migration errors partway, neither its partial DDL nor its
    version record survives -- so it is cleanly retried, never left
    applied-but-unrecorded."""
    import pytest
    from database import connection as dbc
    from database import schema as schema_mod

    monkeypatch.setattr(dbc, "DATABASE_PATH", tmp_path / "atomic.db")
    from database.crypto import derive_key
    dbc.set_active_key(derive_key("test-passphrase"))

    migdir = tmp_path / "migs"
    migdir.mkdir()
    # First statement succeeds, second (duplicate CREATE, no IF NOT EXISTS) fails.
    (migdir / "001_boom.sql").write_text(
        "CREATE TABLE will_rollback (id INTEGER);\n"
        "CREATE TABLE will_rollback (id INTEGER);\n"
    )
    monkeypatch.setattr(schema_mod, "MIGRATIONS_DIR", migdir)

    conn = dbc.get_connection()
    with pytest.raises(Exception):
        schema_mod.create_tables(conn)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = '001_boom'")
    assert cur.fetchone()[0] == 0  # not recorded
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='will_rollback'")
    assert cur.fetchone() is None  # partial DDL rolled back
    conn.close()


def test_a_migration_renumbered_after_a_book_applied_it_heals_instead_of_crashing(db):
    """Reproduces a real failure: account_grouping shipped as
    020_account_grouping.sql and was later renamed. Option A now calls it
    043_account_grouping.sql. A book that already ran it
    under the old name has the column but no tracking row for the new
    filename, so create_tables tried to add the column again and crashed
    every launch with "duplicate column name: account_grouping".
    """
    conn = get_connection()
    conn.execute(
        "DELETE FROM schema_migrations WHERE version = '043_account_grouping'"
    )
    conn.commit()

    create_tables(conn)  # must not raise

    cur = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = '043_account_grouping'"
    )
    assert cur.fetchone() is not None
    cur = conn.execute("PRAGMA table_info(accounts)")
    assert "account_grouping" in {row[1] for row in cur.fetchall()}
    conn.close()


def test_a_multi_statement_migration_never_gets_the_healing_treatment(db):
    """The narrow fix applies only to a lone ALTER TABLE ADD COLUMN. A
    migration with more than one statement could be partially applied in a
    way indistinguishable from fully applied, so a duplicate-column error
    from one of its statements must still crash rather than be marked done.
    """
    from database.schema import _added_column_if_sole_statement

    assert _added_column_if_sole_statement(
        "ALTER TABLE accounts ADD COLUMN account_grouping TEXT;"
    ) == "account_grouping"
    assert _added_column_if_sole_statement(
        "ALTER TABLE accounts ADD COLUMN cash_flow_section TEXT\n"
        "    CHECK (cash_flow_section IN ('operating', 'investing'));"
    ) == "cash_flow_section"
    assert _added_column_if_sole_statement(
        "ALTER TABLE accounts ADD COLUMN a TEXT;\n"
        "ALTER TABLE accounts ADD COLUMN b TEXT;"
    ) is None
    assert _added_column_if_sole_statement(
        "CREATE TABLE t (id INTEGER);"
    ) is None
