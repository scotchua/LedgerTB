"""Focused client model behavior using a temporary SQLite book."""

from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch
import sqlite3
import sys


_SOURCE = Path(__file__).resolve().parents[1] / "models" / "client.py"
_MUTANT_SOURCE = None


@contextmanager
def client_sandbox():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "book.db"
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY, name TEXT, entity_type TEXT,
                business_type TEXT, fiscal_year_end_month INTEGER, is_active INTEGER,
                tax_id TEXT, dba_name TEXT, address_line1 TEXT, address_city TEXT,
                address_state TEXT, address_zip TEXT, contact_name TEXT,
                contact_email TEXT, contact_phone TEXT, notes TEXT,
                business_context TEXT, accounting_basis TEXT
            );
            CREATE TABLE accounts (id INTEGER PRIMARY KEY, client_id INTEGER);
            CREATE TABLE journal_entries (id INTEGER PRIMARY KEY, client_id INTEGER);
        """)
        conn.close()

        def connect():
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            return connection

        @contextmanager
        def get_cursor():
            connection = connect()
            try:
                yield connection.cursor()
            finally:
                connection.close()

        audit_rows = []

        class AuditLog:
            @staticmethod
            def write(cursor, client_id, table, record_id, action,
                      old_values=None, new_values=None):
                audit_rows.append((client_id, table, record_id, action,
                                   old_values, new_values))

        seed_calls = []

        def seed_chart(connection, client_id, entity_type, business_type):
            seed_calls.append((client_id, entity_type, business_type))
            connection.execute("INSERT INTO accounts (client_id) VALUES (?)", (client_id,))

        database = ModuleType("database")
        database.__path__ = []
        connection = ModuleType("database.connection")
        connection.get_connection = connect
        connection.get_cursor = get_cursor
        seed_data = ModuleType("database.seed_data")
        seed_data.seed_chart_of_accounts_for_client = seed_chart
        models = ModuleType("models")
        models.__path__ = []
        audit_log = ModuleType("models.audit_log")
        audit_log.AuditLog = AuditLog
        client_module = ModuleType("models.client")
        client_module.__file__ = str(_SOURCE)
        models.client = client_module
        models.audit_log = audit_log
        modules = {
            "database": database, "database.connection": connection,
            "database.seed_data": seed_data, "models": models,
            "models.audit_log": audit_log, "models.client": client_module,
        }
        with patch.dict(sys.modules, modules):
            source = _MUTANT_SOURCE if _MUTANT_SOURCE is not None else _SOURCE.read_text()
            exec(compile(source, str(_SOURCE), "exec"), client_module.__dict__)
            client_module.Client._seed_calls = seed_calls
            yield client_module.Client, connect, audit_rows


def test_from_row_handles_legacy_optional_columns():
    with client_sandbox() as (Client, _, _):
        row = {
            "id": 7, "name": "Cedar Orbit Studio", "entity_type": "LLC",
            "fiscal_year_end_month": 9, "is_active": 0,
        }
        client = Client._from_row(row)
        assert (client.id, client.name, client.fiscal_year_end_month) == (7, "Cedar Orbit Studio", 9)
        assert client.is_active is False
        assert client.business_context is None
        assert client.accounting_basis is None


def test_get_all_filters_inactive_and_orders_by_name():
    with client_sandbox() as (Client, _, _):
        Client(name="Zephyr Paperworks").save(seed_accounts=False)
        Client(name="Amber Kite Design").save(seed_accounts=False)
        Client(name="Birch Lantern Works", is_active=False).save(seed_accounts=False)
        assert [c.name for c in Client.get_all()] == ["Amber Kite Design", "Zephyr Paperworks"]
        assert [c.name for c in Client.get_all(active_only=False)] == [
            "Amber Kite Design", "Birch Lantern Works", "Zephyr Paperworks",
        ]


def test_get_by_id_returns_none_for_missing_client():
    with client_sandbox() as (Client, _, _):
        present = Client(name="Silver Compass Press").save(seed_accounts=False)
        assert Client.get_by_id(present).name == "Silver Compass Press"
        assert Client.get_by_id(present + 1) is None


def test_save_preserves_caller_transaction_and_audit_snapshot():
    with client_sandbox() as (Client, connect, audit_rows):
        connection = connect()
        client = Client(name="Marble Finch Studio", tax_id="99-8765432")
        client_id = client.save(seed_accounts=False, conn=connection)
        assert connection.execute("SELECT name FROM clients WHERE id = ?", (client_id,)).fetchone()[0] == client.name
        connection.rollback()
        connection.close()
        assert Client.get_by_id(client_id) is None
        assert audit_rows[0][3] == "INSERT"
        assert audit_rows[0][5]["tax_id_present"] is True
        assert audit_rows[0][5]["tax_id_last4"] == "5432"


def test_save_update_records_old_and_new_values():
    with client_sandbox() as (Client, _, audit_rows):
        client = Client(name="Copper Heron Books", accounting_basis="cash")
        client.save(seed_accounts=False)
        client.name = "Copper Heron Editions"
        client.accounting_basis = "accrual"
        client.save(seed_accounts=False)
        assert Client.get_by_id(client.id).accounting_basis == "accrual"
        assert audit_rows[-1][3] == "UPDATE"
        assert audit_rows[-1][4]["name"] == "Copper Heron Books"
        assert audit_rows[-1][5]["name"] == "Copper Heron Editions"


def test_save_seeds_only_new_clients_when_requested_with_defaults():
    with client_sandbox() as (Client, connect, _):
        unseeded = Client(name="Pebble Crane Gallery")
        unseeded.save(seed_accounts=False)
        assert Client._seed_calls == []
        seeded = Client(name="Fernlight Workshop")
        seeded.save(seed_accounts=True)
        assert Client._seed_calls == [
            (seeded.id, "Sole Proprietorship", "Other"),
        ]
        seeded.name = "Fernlight Makers"
        seeded.save(seed_accounts=True)
        assert len(Client._seed_calls) == 1
        with closing(connect()) as connection:
            assert connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1


def test_categorization_context_uses_only_opted_in_fields():
    with client_sandbox() as (Client, _, _):
        client = Client(
            name="Harbor Fern Co", entity_type="LLC", business_type="Florist",
            business_context="  Seasonal wholesale orders.  ",
            notes="Private owner note", tax_id="11-1111111",
        )
        assert client.categorization_context() == (
            "Legal structure: LLC. Business or industry: Florist. "
            "Seasonal wholesale orders."
        )
        client.entity_type = None
        client.business_type = None
        client.business_context = "  "
        assert client.categorization_context() == ""


def test_deactivate_persists_inactive_state():
    with client_sandbox() as (Client, _, _):
        client = Client(name="Juniper Atlas Labs")
        client.save(seed_accounts=False)
        client.deactivate()
        assert client.is_active is False
        assert Client.get_by_id(client.id).is_active is False


def test_has_transactions_checks_requested_client_and_zero_boundary():
    with client_sandbox() as (Client, connect, _):
        first = Client(name="Orchid Loom Studio").save(seed_accounts=False)
        second = Client(name="Moss Harbor Design").save(seed_accounts=False)
        assert Client.has_transactions(first) is False
        with closing(connect()) as connection:
            connection.execute("INSERT INTO journal_entries (client_id) VALUES (?)", (second,))
            connection.commit()
        assert Client.has_transactions(first) is False
        assert Client.has_transactions(second) is True


def test_get_first_returns_first_active_client_or_none():
    with client_sandbox() as (Client, _, _):
        assert Client.get_first() is None
        Client(name="Willow Dune Co", is_active=False).save(seed_accounts=False)
        Client(name="Pineglass Atelier").save(seed_accounts=False)
        Client(name="Aster Field Studio").save(seed_accounts=False)
        assert Client.get_first().name == "Aster Field Studio"
