import json
from datetime import date

import pytest

from conftest import post_entry
from database.connection import get_connection, get_cursor
from models.fiscal_period import FiscalPeriod
from models.journal_entry import JournalEntry
from models.reports import ReportGenerator
from models.transaction import ImportedTransaction


def _entry(client_id, accounts, entry_date=date(2026, 4, 2)):
    return post_entry(client_id, entry_date, [
        (accounts["expense"], 75, 0),
        (accounts["cash"], 0, 75),
    ])


def test_void_posts_same_day_pair_links_kind_and_audit(client_id, accounts):
    original = _entry(client_id, accounts)

    reversal = JournalEntry.void(original.id, client_id)
    original = JournalEntry.get_by_id(original.id, client_id)
    reversal = JournalEntry.get_by_id(reversal.id, client_id)

    assert reversal.entry_date == original.entry_date
    assert [(line.debit, line.credit) for line in reversal.lines] == [(0, 75), (75, 0)]
    assert original.reversal_kind == reversal.reversal_kind == "void"
    assert original.reversed_by_journal_entry_id == reversal.id
    assert reversal.reverses_journal_entry_id == original.id
    with get_cursor() as cursor:
        row = cursor.execute(
            "SELECT new_values FROM audit_log WHERE action = 'REVERSE' "
            "AND record_id = ? ORDER BY id DESC LIMIT 1", (original.id,),
        ).fetchone()
    assert json.loads(row["new_values"])["kind"] == "void"


def test_reverse_defaults_kind_and_null_legacy_pair_remains_visible(client_id, accounts):
    original = _entry(client_id, accounts)
    reversal = JournalEntry.reverse(original.id, client_id)
    assert JournalEntry.get_by_id(original.id).reversal_kind == "reversal"
    assert JournalEntry.get_by_id(reversal.id).reversal_kind == "reversal"

    legacy = _entry(client_id, accounts, date(2026, 4, 3))
    legacy_reversal = _entry(client_id, accounts, date(2026, 4, 3))
    with get_connection() as conn:
        conn.execute(
            "UPDATE journal_entries SET reversed_by_journal_entry_id = ? WHERE id = ?",
            (legacy_reversal.id, legacy.id),
        )
        conn.execute(
            "UPDATE journal_entries SET reverses_journal_entry_id = ? WHERE id = ?",
            (legacy.id, legacy_reversal.id),
        )
        conn.commit()
    visible = {entry.id for entry in JournalEntry.get_all(client_id, include_voided=False)}
    assert {legacy.id, legacy_reversal.id}.issubset(visible)


def test_void_filter_list_and_summary_agree(client_id, accounts):
    voided = _entry(client_id, accounts)
    void_reversal = JournalEntry.void(voided.id, client_id)
    reversed_entry = _entry(client_id, accounts, date(2026, 4, 3))
    ordinary_reversal = JournalEntry.reverse(reversed_entry.id, client_id)

    all_entries = JournalEntry.get_all(client_id)
    visible = JournalEntry.get_all(client_id, include_voided=False)
    assert {entry.id for entry in all_entries} == {
        voided.id, void_reversal.id, reversed_entry.id, ordinary_reversal.id,
    }
    assert {entry.id for entry in visible} == {reversed_entry.id, ordinary_reversal.id}
    assert JournalEntry.get_filtered_summary(client_id)["total_count"] == len(all_entries)
    assert JournalEntry.get_filtered_summary(
        client_id, include_voided=False,
    )["total_count"] == len(visible)


def test_void_closed_period_preflight_writes_nothing(client_id, accounts):
    original = _entry(client_id, accounts, date(2025, 12, 31))
    FiscalPeriod(
        client_id=client_id, period_name="Invented FY 2025", period_type="Year",
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), is_closed=True,
    ).save()
    with get_cursor() as cursor:
        entry_count = cursor.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        audit_count = cursor.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    with pytest.raises(ValueError, match="Invented FY 2025.*Use Reverse Entry"):
        JournalEntry.void(original.id, client_id)

    with get_cursor() as cursor:
        assert cursor.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == entry_count
        assert cursor.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == audit_count


def test_void_inherits_existing_guards_without_writes(client_id, accounts):
    reversed_entry = _entry(client_id, accounts)
    JournalEntry.reverse(reversed_entry.id, client_id)
    imported = _entry(client_id, accounts, date(2026, 4, 3))
    ImportedTransaction(
        client_id=client_id, transaction_date=imported.entry_date,
        description="Invented imported posting", amount=-75,
        bank_account_id=accounts["cash"], status="Posted",
        journal_entry_id=imported.id,
    ).save()
    reconciled = _entry(client_id, accounts, date(2026, 4, 4))
    with get_connection() as conn:
        reconciliation_id = conn.execute(
            "INSERT INTO bank_reconciliations "
            "(client_id, account_id, statement_start_date, statement_end_date, "
            "statement_ending_balance, status) VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, accounts["cash"], "2026-04-01", "2026-04-30", 0, "Draft"),
        ).lastrowid
        line_id = conn.execute(
            "SELECT id FROM journal_entry_lines WHERE journal_entry_id = ? LIMIT 1",
            (reconciled.id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO bank_reconciliation_items "
            "(reconciliation_id, journal_entry_line_id) VALUES (?, ?)",
            (reconciliation_id, line_id),
        )
        conn.commit()
    before_entries = JournalEntry.count(client_id)
    with get_cursor() as cursor:
        before_audits = cursor.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    for entry_id, message in [
        (reversed_entry.id, "already reversed"),
        (imported.id, "Imported postings cannot be reversed here"),
        (reconciled.id, "selected in a bank reconciliation"),
    ]:
        with pytest.raises(ValueError, match=message):
            JournalEntry.void(entry_id, client_id)

    assert JournalEntry.count(client_id) == before_entries
    with get_cursor() as cursor:
        assert cursor.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before_audits


def test_voided_pair_cannot_be_reversed_or_voided_again(client_id, accounts):
    original = _entry(client_id, accounts)
    void_reversal = JournalEntry.void(original.id, client_id)
    message = (
        "A voided entry cannot be reversed or voided again. Enter it again if it "
        "was needed."
    )
    before_entries = JournalEntry.count(client_id)
    with get_cursor() as cursor:
        before_audits = cursor.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    for operation, entry_id in [
        (JournalEntry.void, void_reversal.id),
        (JournalEntry.reverse, original.id),
        (JournalEntry.reverse, void_reversal.id),
    ]:
        with pytest.raises(ValueError, match=message):
            operation(entry_id, client_id)

    assert JournalEntry.count(client_id) == before_entries
    with get_cursor() as cursor:
        assert cursor.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before_audits


def test_reverse_rejects_invalid_void_date_and_kind(client_id, accounts):
    original = _entry(client_id, accounts)
    with pytest.raises(ValueError, match="original entry date"):
        JournalEntry.reverse(
            original.id, client_id, reversal_date=date(2026, 4, 5), kind="void",
        )
    with pytest.raises(ValueError, match="Reversal kind"):
        JournalEntry.reverse(original.id, client_id, kind="bogus")


def test_trial_balance_is_identical_after_void(client_id, accounts):
    before = ReportGenerator.trial_balance(client_id)
    original = _entry(client_id, accounts)
    JournalEntry.void(original.id, client_id)
    after = ReportGenerator.trial_balance(client_id)

    assert after == before
