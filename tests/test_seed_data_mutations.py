import importlib.util
import sqlite3
from pathlib import Path

import pytest

from constants import AccountSubtype


@pytest.fixture
def seed_module():
    path = Path(__file__).resolve().parents[1] / "database" / "seed_data.py"
    spec = importlib.util.spec_from_file_location("seed_data_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_get_accounts_for_client_selects_entity_and_fallback(seed_module):
    seed_module.CORE_ACCOUNTS = [("1100", "Larch Cash", "Asset", "Cash")]
    seed_module.EQUITY_ACCOUNTS = {
        "Larch LLC": [("3100", "Larch Capital", "Equity", "Owner Contribution")],
        "Sole Proprietorship": [
            ("3200", "Fallback Capital", "Equity", "Owner Contribution")
        ],
    }
    seed_module.ENTITY_SPECIFIC_ACCOUNTS = {
        "Larch LLC": [("2100", "Larch Loan", "Liability", "Loan")]
    }
    seed_module.BUSINESS_TYPE_ACCOUNTS = {"Other": []}

    chosen = seed_module.get_accounts_for_client("Larch LLC", "Other")
    fallback = seed_module.get_accounts_for_client("Unknown Larch", "Other")

    assert [account[0] for account in chosen] == ["1100", "2100", "3100"]
    assert [account[0] for account in fallback] == ["1100", "3200"]


def test_get_accounts_for_client_selects_business_and_fallback(seed_module):
    seed_module.CORE_ACCOUNTS = [("1100", "Orchid Cash", "Asset", "Cash")]
    seed_module.EQUITY_ACCOUNTS = {"Sole Proprietorship": []}
    seed_module.ENTITY_SPECIFIC_ACCOUNTS = {}
    seed_module.BUSINESS_TYPE_ACCOUNTS = {
        "Orchid Studio": [("4100", "Orchid Fees", "Revenue", "Other")],
        "Other": [("4200", "Fallback Fees", "Revenue", "Other")],
    }

    chosen = seed_module.get_accounts_for_client("Sole Proprietorship", "Orchid Studio")
    fallback = seed_module.get_accounts_for_client("Sole Proprietorship", "Unknown Studio")

    assert [account[0] for account in chosen] == ["1100", "4100"]
    assert [account[0] for account in fallback] == ["1100", "4200"]


def test_get_accounts_for_client_deduplicates_by_number_and_sorts(seed_module):
    seed_module.CORE_ACCOUNTS = [
        ("9000", "Cedar Original", "Expense", "Occupancy"),
        ("1000", "Cedar Cash", "Asset", "Cash"),
    ]
    seed_module.EQUITY_ACCOUNTS = {"Sole Proprietorship": []}
    seed_module.ENTITY_SPECIFIC_ACCOUNTS = {}
    seed_module.BUSINESS_TYPE_ACCOUNTS = {
        "Other": [
            ("9000", "Cedar Duplicate", "Expense", "Occupancy"),
            ("5000", "Cedar Expense", "Expense", "Occupancy"),
        ]
    }

    accounts = seed_module.get_accounts_for_client("Sole Proprietorship", "Other")

    assert [account[0] for account in accounts] == ["1000", "5000", "9000"]
    assert accounts[-1][1] == "Cedar Original"
    assert accounts[-1][3] == AccountSubtype.OPERATING_EXPENSE


def test_get_accounts_for_entity_type_uses_professional_services(seed_module):
    seed_module.CORE_ACCOUNTS = []
    seed_module.EQUITY_ACCOUNTS = {
        "Sole Proprietorship": [],
        "Pine Cooperative": [("3000", "Pine Capital", "Equity", "Owner Contribution")],
    }
    seed_module.ENTITY_SPECIFIC_ACCOUNTS = {}
    seed_module.BUSINESS_TYPE_ACCOUNTS = {
        "Professional Services": [
            ("4000", "Pine Services", "Revenue", "Other")
        ],
        "Other": [("4100", "Pine Goods", "Revenue", "Other")],
    }

    accounts = seed_module.get_accounts_for_entity_type("Pine Cooperative")

    assert [account[0] for account in accounts] == ["3000", "4000"]


def test_seed_chart_of_accounts_for_client_inserts_only_for_new_client(seed_module):
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            "CREATE TABLE accounts (client_id INTEGER, account_number TEXT, "
            "name TEXT, type TEXT, subtype TEXT)"
        )
        conn.execute(
            "INSERT INTO accounts VALUES (2, '9999', 'Birch Existing', 'Asset', 'Cash')"
        )
        seed_module.CORE_ACCOUNTS = [("1000", "Birch Cash", "Asset", "Cash")]
        seed_module.EQUITY_ACCOUNTS = {"Sole Proprietorship": []}
        seed_module.ENTITY_SPECIFIC_ACCOUNTS = {}
        seed_module.BUSINESS_TYPE_ACCOUNTS = {"Other": []}

        seed_module.seed_chart_of_accounts_for_client(conn, 1)
        seed_module.seed_chart_of_accounts_for_client(conn, 1)
        seed_module.seed_chart_of_accounts_for_client(conn, 2)

        rows = conn.execute(
            "SELECT client_id, account_number, name FROM accounts ORDER BY client_id"
        ).fetchall()
        assert rows == [
            (1, "1000", "Birch Cash"),
            (2, "9999", "Birch Existing"),
        ]
    finally:
        conn.close()


def test_seed_chart_of_accounts_for_client_leaves_transaction_to_caller(seed_module):
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            "CREATE TABLE accounts (client_id INTEGER, account_number TEXT, "
            "name TEXT, type TEXT, subtype TEXT)"
        )
        conn.commit()
        seed_module.CORE_ACCOUNTS = [("1000", "Maple Cash", "Asset", "Cash")]
        seed_module.EQUITY_ACCOUNTS = {"Sole Proprietorship": []}
        seed_module.ENTITY_SPECIFIC_ACCOUNTS = {}
        seed_module.BUSINESS_TYPE_ACCOUNTS = {"Other": []}

        seed_module.seed_chart_of_accounts_for_client(conn, 7)

        assert conn.in_transaction
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
    finally:
        conn.close()
