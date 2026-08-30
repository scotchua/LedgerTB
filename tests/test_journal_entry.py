from datetime import date

import pytest

from conftest import post_entry
from models.journal_entry import JournalEntry, JournalEntryLine
from models.fiscal_period import FiscalPeriod
from models.transaction import ImportedTransaction


def test_delete_entry_linked_to_imported_transaction_is_blocked(client_id, accounts):
    """Imported source history must never be left marked Posted without its entry."""
    entry = post_entry(client_id, date(2025, 5, 1), [
        (accounts["cash"], 100, 0),
        (accounts["revenue"], 0, 100),
    ])

    # An import-posted transaction referencing that entry (mirrors the posting flow).
    txn = ImportedTransaction(
        client_id=client_id,
        transaction_date=date(2025, 5, 1),
        description="ACME DEPOSIT",
        amount=100.0,
        bank_account_id=accounts["cash"],
        suggested_account_id=accounts["revenue"],
        status="Posted",
        journal_entry_id=entry.id,
    )
    txn.save()

    with pytest.raises(ValueError, match="Reverse it instead"):
        JournalEntry.delete(entry.id)

    assert JournalEntry.get_by_id(entry.id) is not None

    posted = ImportedTransaction.get_by_status(client_id, "Posted")
    assert len(posted) == 1
    assert posted[0].journal_entry_id == entry.id


def test_saved_entry_cannot_be_edited_or_deleted(client_id, accounts):
    entry = post_entry(client_id, date(2025, 5, 2), [
        (accounts["cash"], 50, 0),
        (accounts["revenue"], 0, 50),
    ])
    before = JournalEntry.get_by_id(entry.id)
    entry.description = "Rewritten"

    with pytest.raises(ValueError, match="Posted entries cannot be edited"):
        entry.save()
    with pytest.raises(ValueError, match="Posted entries cannot be deleted"):
        JournalEntry.delete(entry.id)

    after = JournalEntry.get_by_id(entry.id)
    assert after.description == before.description
    assert [(line.debit, line.credit) for line in after.lines] == [
        (line.debit, line.credit) for line in before.lines
    ]


def test_reverse_swaps_lines_links_audits_and_refuses_second(client_id, accounts):
    entry = post_entry(client_id, date(2025, 5, 4), [
        (accounts["cash"], 125, 0),
        (accounts["revenue"], 0, 125),
    ])

    reversal = JournalEntry.reverse(entry.id, client_id)
    original = JournalEntry.get_by_id(entry.id)
    reversal = JournalEntry.get_by_id(reversal.id)

    assert reversal.entry_date == entry.entry_date
    assert [(line.debit, line.credit) for line in reversal.lines] == [
        (0, 125), (125, 0)
    ]
    assert reversal.reverses_journal_entry_id == entry.id
    assert original.reversed_by_journal_entry_id == reversal.id

    from database.connection import get_cursor
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT action FROM audit_log WHERE table_name = 'journal_entries' "
            "AND record_id IN (?, ?) ORDER BY id",
            (entry.id, reversal.id),
        )
        assert [row["action"] for row in cursor.fetchall()][-2:] == ["INSERT", "REVERSE"]

    with pytest.raises(ValueError, match="already reversed"):
        JournalEntry.reverse(entry.id, client_id)


def test_closed_period_reversal_requires_and_uses_open_date(client_id, accounts):
    entry = post_entry(client_id, date(2025, 12, 31), [
        (accounts["cash"], 80, 0),
        (accounts["revenue"], 0, 80),
    ])
    FiscalPeriod(
        client_id=client_id, period_name="FY 2025", period_type="Year",
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), is_closed=True,
    ).save()

    with pytest.raises(ValueError, match="Choose a reversal date"):
        JournalEntry.reverse(entry.id, client_id)
    reversal = JournalEntry.reverse(entry.id, client_id, date(2026, 1, 2))
    assert reversal.entry_date == date(2026, 1, 2)


def test_document_controlled_entry_cannot_be_reversed(client_id, accounts):
    from database.connection import get_connection
    from models.fixed_asset import FixedAsset, FixedAssetType

    entry = post_entry(client_id, date(2025, 5, 5), [
        (accounts["expense"], 20, 0),
        (accounts["cash"], 0, 20),
    ])
    asset_type = FixedAssetType(
        client_id=client_id, name="Computer", asset_account_id=accounts["cash"],
        accumulated_depreciation_account_id=accounts["equity"],
        depreciation_expense_account_id=accounts["expense"],
        effective_life_months=36,
    )
    asset_type.save()
    asset = FixedAsset(
        client_id=client_id, fixed_asset_type_id=asset_type.id,
        description="Laptop", acquisition_date=date(2025, 1, 1),
        in_service_date=date(2025, 1, 1), cost_cents=120000,
    )
    asset.save()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO depreciation_runs "
            "(fixed_asset_id, period_start, period_end, amount_cents, journal_entry_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (asset.id, "2025-05-01", "2025-05-31", 2000, entry.id),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="depreciation run"):
        JournalEntry.reverse(entry.id, client_id)


def test_negative_journal_amounts_are_rejected(client_id, accounts):
    entry = JournalEntry(
        client_id=client_id,
        entry_date=date(2025, 5, 3),
        lines=[
            JournalEntryLine(account_id=accounts["cash"], debit=-100, credit=0),
            JournalEntryLine(account_id=accounts["revenue"], debit=0, credit=-100),
        ],
    )

    with pytest.raises(ValueError, match="cannot be negative"):
        entry.save()


def test_closed_year_entry_cannot_be_edited(client_id, accounts):
    entry = post_entry(client_id, date(2025, 12, 31), [
        (accounts["cash"], 100, 0),
        (accounts["revenue"], 0, 100),
    ])
    FiscalPeriod(
        client_id=client_id,
        period_name="FY 2025",
        period_type="Year",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        is_closed=True,
    ).save()

    entry.entry_date = date(2026, 1, 1)
    with pytest.raises(ValueError, match="Posted entries cannot be edited"):
        entry.save()

    assert JournalEntry.get_by_id(entry.id).entry_date == date(2025, 12, 31)


def test_entry_list_filters_by_search_and_account(client_id, accounts):
    """Search matches description/reference/amount; account filter matches lines."""
    transfer = post_entry(
        client_id, date(2026, 3, 21),
        [(accounts["cash"], 1200, 0), (accounts["equity"], 0, 1200)],
    )
    from database.connection import get_connection
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE journal_entries SET description = ? WHERE id = ?",
            ("Transfer from Relay #7313", transfer.id),
        )
        conn.commit()
    finally:
        conn.close()
    post_entry(
        client_id, date(2026, 2, 1),
        [(accounts["expense"], 15, 0), (accounts["credit_card"], 0, 15)],
    )

    by_text = JournalEntry.get_all(client_id, search_term="relay")
    assert [e.id for e in by_text] == [transfer.id]

    by_amount = JournalEntry.get_all(client_id, search_term="1,200.00")
    assert [e.id for e in by_amount] == [transfer.id]

    by_account = JournalEntry.get_all(client_id, account_id=accounts["credit_card"])
    assert len(by_account) == 1 and by_account[0].id != transfer.id

    # a zero search must not match the whole journal via empty line sides
    assert JournalEntry.get_all(client_id, search_term="0.00") == []

    summary = JournalEntry.get_filtered_summary(
        client_id, search_term="relay"
    )
    assert summary["total_count"] == 1
    assert summary["total_debits"] == 1200.0
