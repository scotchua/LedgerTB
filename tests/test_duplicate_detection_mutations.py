"""Small, synthetic SQLite cases for duplicate proposal boundaries."""

import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "services" / "duplicate_detection.py"


def _load_service(get_connection):
    source = Path(os.environ.get("DUPLICATE_MUTATION_PATH", SOURCE))
    database = types.ModuleType("database")
    database.__path__ = []
    connection = types.ModuleType("database.connection")
    connection.get_connection = get_connection
    previous = {name: sys.modules.get(name) for name in ("database", "database.connection")}
    try:
        sys.modules["database"] = database
        sys.modules["database.connection"] = connection
        module = types.ModuleType("duplicate_detection_under_test")
        exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
        return module
    finally:
        for name, original in previous.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class ProposeDuplicatesMutationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "synthetic.db"
        self.conn = sqlite3.connect(self.path)
        self.addCleanup(self.conn.close)
        self.conn.executescript("""
            CREATE TABLE clients (id INTEGER PRIMARY KEY);
            CREATE TABLE counterparties (id INTEGER PRIMARY KEY, client_id INTEGER,
                                         display_name TEXT);
            CREATE TABLE journal_counterparty_sources (
                client_id INTEGER, journal_entry_id INTEGER, source_reference TEXT,
                reversed INTEGER);
            CREATE TABLE journal_entries (
                id INTEGER PRIMARY KEY, client_id INTEGER, entry_date TEXT,
                source_reference TEXT, reverses_journal_entry_id INTEGER,
                reversed_by_journal_entry_id INTEGER);
            CREATE TABLE journal_entry_lines (
                id INTEGER PRIMARY KEY, journal_entry_id INTEGER, counterparty_id INTEGER,
                account_id INTEGER, debit INTEGER, credit INTEGER);
            INSERT INTO clients VALUES (1), (2);
            INSERT INTO counterparties VALUES (10, 1, 'Aster Supply'),
                                              (20, 1, 'Birch Works'),
                                              (30, 2, 'Cedar Studio');
        """)
        self.opened = []

        class TrackedConnection:
            def __init__(self, connection):
                self.connection = connection
                self.closed = False

            def execute(self, *args):
                return self.connection.execute(*args)

            def close(self):
                self.closed = True
                self.connection.close()

        def get_connection():
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            tracked = TrackedConnection(conn)
            self.opened.append(tracked)
            return tracked

        self.propose = _load_service(get_connection).propose_duplicates

    def entry(self, entry_id, *, client=1, day="2026-04-10", reference=None,
              party=10, account=6000, debit=1000, credit=0, line_id=None,
              reverses=None, reversed_by=None):
        self.conn.execute(
            "INSERT INTO journal_entries VALUES (?, ?, ?, ?, ?, ?)",
            (entry_id, client, day, reference, reverses, reversed_by),
        )
        self.line(line_id or entry_id, entry_id, party, account, debit, credit)
        self.conn.commit()

    def line(self, line_id, entry_id, party, account, debit, credit):
        self.conn.execute("INSERT INTO journal_entry_lines VALUES (?, ?, ?, ?, ?, ?)",
                          (line_id, entry_id, party, account, debit, credit))
        self.conn.commit()

    def source(self, entry_id, reference, reversed=False):
        self.conn.execute("INSERT INTO journal_counterparty_sources VALUES (?, ?, ?, ?)",
                          (1, entry_id, reference, int(reversed)))
        self.conn.commit()

    def pairs(self, **kwargs):
        return {(p["first_entry_id"], p["second_entry_id"])
                for p in self.propose(1, **kwargs)["proposals"]}

    def test_propose_duplicates_rejects_invalid_bounds_and_missing_client(self):
        for tolerance, window in ((-1, 3), (10001, 3), (True, 3), (1.0, 3),
                                  (1, -1), (1, 367), (1, False)):
            with self.subTest(tolerance=tolerance, window=window):
                with self.assertRaisesRegex(ValueError, "must be an integer"):
                    self.propose(1, tolerance, window)
        with self.assertRaisesRegex(ValueError, "Client not found"):
            self.propose(999)
        self.assertEqual(self.propose(1, 0, 0)["proposals"], [])
        self.assertEqual(self.propose(1, 10000, 366)["proposals"], [])

    def test_propose_duplicates_returns_complete_grouped_proposal(self):
        self.entry(101)
        self.entry(102)
        self.line(201, 101, 10, 6000, 500, 0)
        self.line(202, 102, 10, 6000, 500, 0)
        result = self.propose(1)
        self.assertEqual((result["client_id"], result["amount_tolerance_cents"],
                          result["date_window_days"]), (1, 1, 3))
        self.assertIn("human reversal", result["note"])
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual({key: proposal[key] for key in
                          ("status", "first_entry_id", "second_entry_id",
                           "counterparty_id", "counterparty_name", "first_date",
                           "second_date")}, {
                               "status": "proposed", "first_entry_id": 101,
                               "second_entry_id": 102, "counterparty_id": 10,
                               "counterparty_name": "Aster Supply",
                               "first_date": "2026-04-10", "second_date": "2026-04-10"})
        self.assertIn("matching signed amount", proposal["reason"])
        self.assertEqual(proposal["matched_lines"], [
            {"first_line_id": 101, "second_line_id": 102,
             "first_amount_cents": 1000, "second_amount_cents": 1000},
            {"first_line_id": 201, "second_line_id": 202,
             "first_amount_cents": 500, "second_amount_cents": 500},
        ])

    def test_propose_duplicates_excludes_distinct_sources_and_reversed_entries(self):
        for first, second in ((101, 102), (201, 202), (301, 302)):
            self.entry(first, party=10 if first == 101 else 20)
            self.entry(second, party=10 if first == 101 else 20)
        self.source(101, "bill-a")
        self.source(102, "bill-b")
        self.source(201, "shared")
        self.source(202, "shared")
        self.source(301, "old", reversed=True)
        self.source(302, "old")
        self.assertNotIn((101, 102), self.pairs())
        self.assertIn((201, 202), self.pairs())
        self.assertNotIn((301, 302), self.pairs())

    def test_propose_duplicates_filters_references_after_trimming(self):
        self.entry(101, reference=" REF-A ")
        self.entry(102, reference="REF-B")
        self.assertEqual(self.pairs(), set())
        self.conn.execute("UPDATE journal_entries SET source_reference = 'REF-A' WHERE id = 102")
        self.conn.commit()
        self.assertEqual(self.pairs(), {(101, 102)})
        self.conn.execute("UPDATE journal_entries SET source_reference = NULL WHERE id = 102")
        self.conn.commit()
        self.assertEqual(self.pairs(), {(101, 102)})

    def test_propose_duplicates_observes_amount_and_date_boundaries(self):
        self.entry(101, day="2026-04-10", debit=1000)
        self.entry(102, day="2026-04-13", debit=1001)
        self.assertEqual(self.pairs(), {(101, 102)})
        self.assertEqual(self.pairs(amount_tolerance_cents=0), set())
        self.assertEqual(self.pairs(date_window_days=2), set())
        self.entry(103, day="2026-04-15", debit=1003)
        self.assertNotIn((101, 103), self.pairs())

    def test_propose_duplicates_observes_account_sign_client_and_reversal(self):
        self.entry(101)
        self.entry(102, account=7000)
        self.entry(103, debit=0, credit=1000)
        self.entry(104, client=2, party=30)
        self.entry(105, reverses=101)
        self.entry(106, reversed_by=105)
        self.assertEqual(self.pairs(), set())

    def test_propose_duplicates_reports_signed_credit_amounts(self):
        self.entry(101, debit=0, credit=1275)
        self.entry(102, debit=0, credit=1275)
        proposal = self.propose(1)["proposals"][0]
        self.assertEqual(proposal["matched_lines"], [
            {"first_line_id": 101, "second_line_id": 102,
             "first_amount_cents": -1275, "second_amount_cents": -1275},
        ])

    def test_propose_duplicates_closes_connection_on_success_and_error(self):
        self.propose(1)
        with self.assertRaisesRegex(ValueError, "Client not found"):
            self.propose(999)
        self.assertEqual(len(self.opened), 2)
        self.assertTrue(all(conn.closed for conn in self.opened))


if __name__ == "__main__":
    unittest.main()
