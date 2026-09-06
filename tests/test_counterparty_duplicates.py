import asyncio
from dataclasses import asdict
from datetime import date, timedelta
import json
import sqlite3

import pytest

from database import connection as dbconn
from database import schema
from database.connection import get_connection, init_database
from models.account import Account
from models.client import Client
from models.journal_entry import JournalEntry, JournalEntryLine
from services import ar_ap, mcp_tools
from services.duplicate_detection import propose_duplicates
from tests.counterparty_fixtures import (attribution_coverage, duplicate_metrics,
                                         seed_counterparty_book, seed_duplicate_evaluation)


def _snapshot(conn):
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ) if not row[0].startswith("sqlite_")]
    return {table: [tuple(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
            for table in tables}


def _reproducible_snapshot(conn):
    excluded = {"schema_migrations", "book_identity", "audit_log", "sqlite_sequence"}
    result = {}
    for table in _snapshot(conn):
        if table in excluded:
            continue
        columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')
                   if not row[1].endswith("_at")]
        names = ", ".join(f'"{name}"' for name in columns)
        result[table] = [tuple(row) for row in conn.execute(f'SELECT {names} FROM "{table}" ORDER BY rowid')]
    return result


def _assert_attribution(conn, book):
    for row in conn.execute(
        "SELECT l.journal_entry_id, l.counterparty_id, c.kind, c.source_id "
        "FROM journal_entry_lines l LEFT JOIN counterparties c ON c.id = l.counterparty_id "
        "JOIN journal_entries j ON j.id = l.journal_entry_id WHERE j.client_id = ?",
        (book.client_id,),
    ):
        if row["journal_entry_id"] in book.source_entries:
            assert (row["kind"], row["source_id"]) == book.source_entries[row["journal_entry_id"]]
        else:
            assert row["journal_entry_id"] in book.manual_entries
            assert row["counterparty_id"] is None


def test_service_fixture_reproducible_and_coverage_reported(db, tmp_path, monkeypatch, record_property):
    snapshots = []
    for suffix, seed in (("first", 1729), ("repeat", 1729), ("different", 1730)):
        monkeypatch.setattr(dbconn, "DATABASE_PATH", tmp_path / f"{suffix}.db")
        init_database()
        book = seed_counterparty_book(seed=seed)
        conn = get_connection()
        try:
            _assert_attribution(conn, book)
            for table in ("customers", "vendors", "invoices", "bills", "payments",
                          "bill_payments_v2", "payment_allocations", "bill_payment_allocations",
                          "credit_memos", "credit_applications"):
                assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 10
        finally:
            conn.close()
        assert book.coverage == {"line_count": 120, "attributed_lines": 100, "coverage": 5 / 6}
        labels = seed_duplicate_evaluation(book)
        conn = get_connection()
        try:
            snapshots.append((_reproducible_snapshot(conn), labels))
        finally:
            conn.close()
    assert snapshots[0] == snapshots[1]
    assert snapshots[0] != snapshots[2]
    record_property("attribution_coverage", json.dumps(book.coverage))
    print("Attribution coverage:", json.dumps(book.coverage))


def test_migration_upgrades_existing_service_book(db, tmp_path, monkeypatch, record_property):
    book = seed_counterparty_book()
    _add_source_variants(book)
    live = get_connection()
    old = sqlite3.connect(tmp_path / "existing.db")
    old.row_factory = sqlite3.Row
    try:
        migration_dir = tmp_path / "old_migrations"
        migration_dir.mkdir()
        for path in sorted(schema.MIGRATIONS_DIR.glob("*.sql")):
            if path.name < "909_counterparties.sql":
                (migration_dir / path.name).write_text(path.read_text())
        with monkeypatch.context() as patch:
            patch.setattr(schema, "MIGRATIONS_DIR", migration_dir)
            schema.create_tables(old)
        # Replay service-produced records into the actual pre-909 schema.
        # Omit the new metadata, retaining all original IDs and financial values.
        for table, rows in _snapshot(old).items():
            if table == "schema_migrations":
                continue
            old.execute(f'DELETE FROM "{table}"')
            columns = [row[1] for row in old.execute(f'PRAGMA table_info("{table}")')]
            names = ", ".join(f'"{name}"' for name in columns)
            records = live.execute(f'SELECT {names} FROM "{table}"').fetchall()
            old.executemany(f'INSERT INTO "{table}" ({names}) VALUES ({", ".join("?" for _ in columns)})',
                            [tuple(row) for row in records])
        old.commit()
        before = _snapshot(old)
        assert "counterparty_id" not in {row[1] for row in old.execute("PRAGMA table_info(journal_entry_lines)")}
        old.execute("PRAGMA foreign_keys = ON")
        schema.create_tables(old)
        _assert_attribution(old, book)
        for table, rows in before.items():
            if table == "schema_migrations":
                continue
            after = [tuple(row) for row in old.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
            if table == "journal_entry_lines":
                after = [row[:-1] for row in after]
            assert after == rows
        assert old.execute("PRAGMA foreign_key_check").fetchall() == []
        after = _snapshot(old)
        schema.create_tables(old)
        assert _snapshot(old) == after
        counts = old.execute("SELECT COUNT(*), COUNT(counterparty_id) FROM journal_entry_lines").fetchone()
        assert counts[1] > 100
        assert counts[0] - counts[1] == 2 * len(book.manual_entries)
        record_property("backfill_coverage", f"{counts[1]}/{counts[0]}; every sourced line; manual 0/20")
    finally:
        live.close()
        old.close()


def _add_source_variants(book):
    from services.inventory import create_item, record_movement

    customer = ar_ap.create_customer(book.client_id, "Source variants customer")
    vendor = ar_ap.create_vendor(book.client_id, "Source variants vendor")
    day = date(2026, 1, 1)
    inventory = Account(client_id=book.client_id, account_number="1200",
                        name="Inventory", type="Asset").save()
    tax = Account(client_id=book.client_id, account_number="2200",
                  name="Sales Tax", type="Liability").save()
    item_id = create_item(book.client_id, "SYNTHETIC", "Synthetic stock", inventory, book.accounts["expense"])
    record_movement(item_id, day, "purchase", 2, unit_cost_cents=100)
    invoice = ar_ap.create_invoice(book.client_id, customer.id, [{
        "description": "Inventory sale", "quantity": 1, "unit_price_cents": 1000,
        "revenue_account_id": book.accounts["revenue"], "inventory_item_id": item_id,
    }], day, day, tax_rate="0.10")
    invoice = ar_ap.post_invoice(invoice.id, book.accounts["ar"], tax)
    bill = ar_ap.create_bill(book.client_id, vendor.id, [{
        "description": "Purchase", "quantity": 1, "unit_price_cents": 1000,
        "expense_account_id": book.accounts["expense"],
    }], day, day)
    bill = ar_ap.post_bill(bill.id, book.accounts["ap"])
    memo = ar_ap.create_credit_memo(book.client_id, customer.id, [{
        "description": "Credit", "quantity": 1, "unit_price_cents": 100,
        "revenue_account_id": book.accounts["revenue"],
    }], day, original_invoice_id=invoice.id)
    memo = ar_ap.post_credit_memo(memo.id, book.accounts["ar"])
    for kind, party, document, record, refund, void, table, refunds in (
        ("customer", customer, invoice, ar_ap.record_customer_payment, ar_ap.refund_customer_credit,
         ar_ap.void_payment, "payments", "payment_refunds"),
        ("vendor", vendor, bill, ar_ap.record_vendor_payment, ar_ap.refund_vendor_credit,
         ar_ap.void_vendor_payment, "bill_payments_v2", "bill_payment_refunds"),
    ):
        payment_id = record(book.client_id, party.id, day, 200, book.accounts["cash"], [])
        refund_id = refund(payment_id, 100, book.accounts["cash"], day)
        voided_payment = record(book.client_id, party.id, day, 200, book.accounts["cash"], [])
        void(voided_payment, day)
        conn = get_connection()
        try:
            for row in conn.execute(
                f"SELECT journal_entry_id, voided_journal_entry_id FROM {table} WHERE id IN (?, ?)",
                (payment_id, voided_payment),
            ):
                for entry_id in row:
                    if entry_id is not None:
                        book.source_entries[entry_id] = (kind, party.id)
            entry_id = conn.execute(f"SELECT journal_entry_id FROM {refunds} WHERE id = ?",
                                    (refund_id,)).fetchone()[0]
            book.source_entries[entry_id] = (kind, party.id)
        finally:
            conn.close()
    for document, kind, party, void in (
        (memo, "customer", customer, ar_ap.void_credit_memo),
        (invoice, "customer", customer, ar_ap.void_invoice),
        (bill, "vendor", vendor, ar_ap.void_bill),
    ):
        book.source_entries[document.journal_entry_id] = (kind, party.id)
        book.source_entries[void(document.id, day)] = (kind, party.id)
    conn = get_connection()
    try:
        for row in conn.execute("SELECT journal_entry_id FROM inventory_movements WHERE source_id = ?",
                                (invoice.id,)):
            book.source_entries[row[0]] = ("customer", customer.id)
        _assert_attribution(conn, book)
    finally:
        conn.close()
    for kind, party, document, table, document_field, money_field in (
        ("customer", customer, invoice, "invoice_payments", "invoice_id", "deposit_account_id"),
        ("vendor", vendor, bill, "bill_payments", "bill_id", "payment_account_id"),
    ):
        legacy_entry = JournalEntry(
            client_id=book.client_id, entry_date=day, description="Legacy payment",
            lines=[JournalEntryLine(account_id=book.accounts["cash"], debit=1),
                   JournalEntryLine(account_id=book.accounts["ar"], credit=1)],
        )
        legacy_entry.save()
        conn = get_connection()
        try:
            conn.execute(
                f"INSERT INTO {table} ({document_field}, payment_date, amount_cents, "
                f"{money_field}, journal_entry_id) VALUES (?, ?, 100, ?, ?)",
                (document.id, day.isoformat(), book.accounts["cash"], legacy_entry.id),
            )
            conn.commit()
        finally:
            conn.close()
        book.source_entries[legacy_entry.id] = (kind, party.id)
        reversal = JournalEntry.reverse(legacy_entry.id, book.client_id, day)
        book.source_entries[reversal.id] = (kind, party.id)


@pytest.mark.performance
def test_service_fixture_ten_thousand_entry_coverage(db, record_property):
    book = seed_counterparty_book(party_count=1500, manual_count=2500)
    conn = get_connection()
    try:
        _assert_attribution(conn, book)
        assert conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 10000
    finally:
        conn.close()
    assert book.coverage == {"line_count": 20000, "attributed_lines": 15000, "coverage": 0.75}
    assert book.coverage["coverage"] >= 0.50
    record_property("attribution_coverage_10000_entries", json.dumps(book.coverage))
    print("10,000-entry attribution coverage:", json.dumps(book.coverage))


def test_seeded_duplicate_precision_floor_and_recall(db, record_property):
    book = seed_counterparty_book(party_count=1, manual_count=1)
    labels = seed_duplicate_evaluation(book)
    result = propose_duplicates(book.client_id)
    metrics = duplicate_metrics(labels, result["proposals"])
    assert len(labels) >= 60
    assert metrics["precision"] >= 0.98
    assert metrics["recall"] == 1.0
    assert metrics["true_positives"] == 24
    predicted = {(p["first_entry_id"], p["second_entry_id"]) for p in result["proposals"]}
    for pair in labels:
        if not pair.duplicate:
            assert (pair.first_entry_id, pair.second_entry_id) not in predicted, pair.scenario
    record_property("duplicate_metrics", json.dumps(metrics))
    record_property("labelled_pairs", json.dumps([asdict(pair) for pair in labels]))
    print("Duplicate evaluation:", json.dumps(metrics))


def test_precision_oracle_counts_unlabelled_predictions_and_empty_output():
    from tests.counterparty_fixtures import LabelledPair

    labels = [LabelledPair(1, 2, True, "positive"), LabelledPair(3, 4, False, "negative")]
    assert duplicate_metrics(labels, []) == {
        "labelled_pairs": 2, "true_positives": 0, "false_positives": 0,
        "false_negatives": 1, "precision": 0.0, "recall": 0.0,
    }
    assert duplicate_metrics(labels, [{"first_entry_id": 1, "second_entry_id": 2},
                                       {"first_entry_id": 5, "second_entry_id": 6}])["precision"] == 0.5


def test_proposals_only_no_merge_path_and_mcp_access(db, monkeypatch):
    import inspect
    import mcp_server
    from services import duplicate_detection

    book = seed_counterparty_book(party_count=1, manual_count=1)
    seed_duplicate_evaluation(book)
    conn = get_connection()
    before = _snapshot(conn)
    conn.close()
    monkeypatch.setattr(mcp_server, "_refresh_access", lambda: dbconn.ASSISTANT_ACCESS_LEVEL)
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "read")
    with pytest.raises(ValueError, match="access level"):
        mcp_server.propose_duplicates(book.client_id)
    with pytest.raises(PermissionError, match="access level"):
        mcp_tools.propose_duplicates(book.client_id)
    for level in ("propose", "post"):
        monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", level)
        result = mcp_server.propose_duplicates(book.client_id)
        assert len(result["proposals"]) == 24
        assert all(p["status"] == "proposed" for p in result["proposals"])
        conn = get_connection()
        try:
            assert _snapshot(conn) == before
        finally:
            conn.close()
    tool = next(t for t in asyncio.run(mcp_server.server.list_tools()) if t.name == "propose_duplicates")
    assert set(tool.input_schema["properties"]) == {
        "client_id", "amount_tolerance_cents", "date_window_days",
    }
    public = [name for name, fn in vars(duplicate_detection).items()
              if inspect.isfunction(fn) and fn.__module__ == duplicate_detection.__name__]
    assert public == ["propose_duplicates"]
    assert not any("merge" in t.name for t in asyncio.run(mcp_server.server.list_tools()))


@pytest.mark.parametrize("tolerance,window", [(-1, 3), (True, 3), (0.5, 3), (1, -1), (1, 367)])
def test_duplicate_parameters_rejected(tolerance, window):
    with pytest.raises(ValueError, match="must be an integer"):
        propose_duplicates(1, tolerance, window)


def test_counterparty_tenant_boundary_and_posted_immutability(db):
    book = seed_counterparty_book(party_count=1, manual_count=1)
    foreign_client = Client(name="Another client").save(seed_accounts=False)
    foreign_party = ar_ap.create_vendor(foreign_client, "Other vendor")
    conn = get_connection()
    try:
        from services.counterparties import counterparty_for_source

        with pytest.raises(ValueError, match="belong"):
            counterparty_for_source(conn.cursor(), book.client_id, "vendor", foreign_party.id)
        cp_id = counterparty_for_source(conn.cursor(), foreign_client, "vendor", foreign_party.id)
        conn.commit()
        with pytest.raises(Exception, match="journal entry client"):
            conn.execute(
                "UPDATE journal_entry_lines SET counterparty_id = ? WHERE journal_entry_id = ?",
                (cp_id, book.manual_entries[0]),
            )
        conn.rollback()
    finally:
        conn.close()
    entry = JournalEntry.get_by_id(next(iter(book.source_entries)), client_id=book.client_id)
    entry.lines[0].counterparty_id = cp_id
    with pytest.raises(ValueError, match="cannot be edited"):
        entry.save()


def test_reverse_preserves_counterparty_and_excludes_reposted_original(db):
    book = seed_counterparty_book(party_count=1, manual_count=1)
    entry_id = next(entry_id for entry_id, party in book.source_entries.items() if party[0] == "vendor")
    source = JournalEntry.get_by_id(entry_id, client_id=book.client_id)
    copies = []
    for offset in (1, 2):
        entry = JournalEntry(
            client_id=book.client_id, entry_date=source.entry_date + timedelta(days=offset),
            description="Synthetic duplicate", source_reference=source.source_reference,
            lines=[JournalEntryLine(account_id=line.account_id, debit=line.debit, credit=line.credit,
                                    counterparty_id=line.counterparty_id) for line in source.lines],
        )
        entry.save()
        copies.append(entry)
    reversal = JournalEntry.reverse(copies[0].id, book.client_id, copies[1].entry_date)
    assert [line.counterparty_id for line in reversal.lines] == [line.counterparty_id for line in source.lines]
    loaded = JournalEntry.get_by_id(reversal.id, client_id=book.client_id)
    assert [line.counterparty_id for line in loaded.lines] == [line.counterparty_id for line in source.lines]
    assert all(copies[0].id not in (p["first_entry_id"], p["second_entry_id"])
               and reversal.id not in (p["first_entry_id"], p["second_entry_id"])
               for p in propose_duplicates(book.client_id)["proposals"])


def test_distinct_payments_with_identical_generated_reference_are_excluded(db):
    book = seed_counterparty_book(party_count=1, manual_count=1)
    conn = get_connection()
    try:
        invoice = conn.execute("SELECT customer_id, invoice_date FROM invoices").fetchone()
    finally:
        conn.close()
    payment_ids = [ar_ap.record_customer_payment(
        book.client_id, invoice["customer_id"], invoice["invoice_date"], 321,
        book.accounts["cash"], [],
    ) for _ in range(2)]
    conn = get_connection()
    try:
        entries = conn.execute(
            "SELECT j.id, j.source_reference FROM payments p "
            "JOIN journal_entries j ON j.id = p.journal_entry_id WHERE p.id IN (?, ?) ORDER BY j.id",
            payment_ids,
        ).fetchall()
    finally:
        conn.close()
    assert entries[0]["source_reference"] == entries[1]["source_reference"]
    assert (entries[0]["id"], entries[1]["id"]) not in {
        (p["first_entry_id"], p["second_entry_id"]) for p in propose_duplicates(book.client_id)["proposals"]
    }
