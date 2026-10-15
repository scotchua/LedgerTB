"""Focused activity-feed behavior checks using invented book activity."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from models.audit_log import AuditLog
from models.journal_entry import JournalEntry
from models.transaction import ImportedTransaction
from services import activity_feed as feed


def test_parse_preserves_datetimes_and_accepts_sqlite_strings():
    stamp = datetime(2026, 4, 3, 9, 8, 7, 123456)
    assert feed._parse(stamp) is stamp
    assert feed._parse("2026-04-03T09:08:07.123456") == stamp.replace(microsecond=0)
    assert feed._parse("not a date") is None
    assert feed._parse(None) is None


def test_plural_uses_singular_only_for_one():
    assert feed._plural(1, "file") == "1 file"
    assert feed._plural(2, "file") == "2 files"


def test_account_label_uses_count_number_and_fallback():
    batch = {"account_count": 2, "account_number": "7310", "account_name": "Harbor Clearing"}
    assert feed._account_label(batch) == "2 accounts"
    batch["account_count"] = 1
    assert feed._account_label(batch) == "7310 - Harbor Clearing"
    batch["account_number"] = None
    assert feed._account_label(batch) == "Harbor Clearing"
    batch["account_name"] = None
    assert feed._account_label(batch) == "an account"


def test_import_events_report_files_and_both_unposted_statuses():
    batch = {
        "filename_count": 2, "source_filename": "harbor-april.csv",
        "pending_count": 2, "categorized_count": 1, "row_count": 4,
        "account_count": 1, "account_number": "7310",
        "account_name": "Harbor Clearing", "imported_at": "2026-04-03 09:08:07",
        "created_by": "Morgan",
    }
    with patch.object(ImportedTransaction, "get_batch_summaries", return_value=[batch]):
        events = feed._import_events(41)
    assert len(events) == 1
    assert events[0].summary == "Imported 4 transactions into 7310 - Harbor Clearing"
    assert events[0].detail == "from 2 files · 3 still to review"
    assert events[0].when == datetime(2026, 4, 3, 9, 8, 7)
    assert events[0].actor == "Morgan"

    batch.update(filename_count=1, pending_count=0, categorized_count=0)
    with patch.object(ImportedTransaction, "get_batch_summaries", return_value=[batch]):
        assert feed._import_events(41)[0].detail == "from harbor-april.csv"


def test_journal_events_name_entries_and_keep_details():
    base = {
        "id": 17, "aje_reference": "AJE-017", "description": "Harbor accrual",
        "entry_date": date(2026, 4, 30), "total_debits": 1234.5,
        "created_at": "2026-05-01 10:00:00", "created_by": "Taylor",
    }
    entries = [
        dict(base, entry_type="Adjusting"),
        dict(base, entry_type="Beginning Balance", description=None),
        dict(base, entry_type="Regular", aje_reference=None),
    ]
    with patch.object(JournalEntry, "get_hand_keyed_recent", return_value=entries) as get_recent:
        events = feed._journal_events(41, 3)
    get_recent.assert_called_once_with(41, limit=3)
    assert [event.summary for event in events] == [
        "Posted adjusting entry AJE-017", "Entered beginning balances",
        "Entered journal entry #17",
    ]
    assert events[0].detail == "Harbor accrual · dated 04/30/2026 · 1,234.50"
    assert events[1].detail == "dated 04/30/2026 · 1,234.50"
    assert events[0].actor == "Taylor"


def test_audit_events_name_exports_reversals_and_fallbacks():
    logs = {
        "EXPORT": [SimpleNamespace(table_name="harbor_summary_export", record_id=None,
                                   changed_at="2026-05-02 11:00:00", performed_by="Alex"),
                   SimpleNamespace(table_name=None, record_id=None,
                                   changed_at="2026-05-02 10:00:00", performed_by="Alex")],
        "REVERSE": [SimpleNamespace(table_name="journal_entries", record_id=23,
                                    changed_at="2026-05-01 08:00:00", performed_by="Taylor")],
        "BACKUP": [SimpleNamespace(table_name="books", record_id=None,
                                   changed_at="2026-04-30 08:00:00", performed_by="Morgan")],
    }
    with patch.object(AuditLog, "get_all", side_effect=lambda client_id, action, limit: logs.get(action, [])):
        events = feed._audit_events(41, 6)
    assert [event.summary for event in events] == [
        "Exported harbor summary", "Exported a report",
        "Backed up the books", "Reversed journal entry #23",
    ]
    assert [event.actor for event in events] == ["Alex", "Alex", "Morgan", "Taylor"]


def test_describe_when_switches_at_each_boundary():
    now = datetime(2026, 6, 20, 12, 0, 0)

    def phrase(seconds):
        return feed.describe_when(now - timedelta(seconds=seconds), now=now)

    assert feed.describe_when(now + timedelta(seconds=1), now=now) == "Jun 20, 2026"
    assert phrase(0) == "just now"
    assert phrase(89) == "just now"
    assert phrase(90) == "1 min ago"
    assert phrase(3599) == "59 min ago"
    assert phrase(3600) == "1 hour ago"
    assert phrase(86399) == "23 hours ago"
    assert phrase(86400) == "yesterday"
    assert phrase(172799) == "yesterday"
    assert phrase(172800) == "2 days ago"
    assert phrase(604799) == "6 days ago"
    assert phrase(604800) == "Jun 13, 2026"


def test_recent_activity_sorts_limits_and_keeps_missing_timestamps():
    earlier = feed.ActivityEvent(datetime(2026, 5, 1), "import", "April import")
    later = feed.ActivityEvent(datetime(2026, 5, 3), "journal", "May entry")
    missing = feed.ActivityEvent(None, "audit", "Harbor export")
    with patch.object(feed, "_import_events", return_value=[earlier]), \
         patch.object(feed, "_journal_events", return_value=[later]), \
         patch.object(feed, "_audit_events", return_value=[missing]):
        assert feed.get_recent_activity(41, limit=3) == [later, earlier, missing]
        assert feed.get_recent_activity(41, limit=2) == [later, earlier]
    seven = [feed.ActivityEvent(datetime(2026, 5, day), "journal", str(day))
             for day in range(1, 8)]
    with patch.object(feed, "_import_events", return_value=seven), \
         patch.object(feed, "_journal_events", return_value=[]), \
         patch.object(feed, "_audit_events", return_value=[]):
        assert len(feed.get_recent_activity(41)) == 6
