from datetime import date
import json

import pytest

from database import connection as dbconn
from models.account import Account
from models.import_coding import record_decision
from models.transaction import ImportedTransaction
from services import mcp_tools


def _pending(client_id, bank_id, status="Pending"):
    row = ImportedTransaction(client_id=client_id, import_batch="tool", transaction_date=date(2026, 2, 1),
                              description="Invented row", amount=-8, bank_account_id=bank_id, status=status)
    row.save()
    return row


def test_suggest_categories_batch_replay_and_projection(client_id, accounts, monkeypatch):
    bank = Account.get_by_id(accounts["cash"])
    expense = Account.get_by_id(accounts["expense"])
    pending = [_pending(client_id, bank.id) for _ in range(3)]
    posted = _pending(client_id, bank.id, "Posted")
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    items = [{"transaction_id": row.id, "account_number": expense.account_number,
              "confidence": "high", "reason": "Invented reason"}
             for row in [*pending, posted]]
    result = mcp_tools.suggest_categories(client_id, items, "request-one")
    assert len(result["accepted"]) == 3 and len(result["rejected"]) == 1
    replay = mcp_tools.suggest_categories(client_id, items, "request-one")
    assert len(replay["skipped"]) == 3 and len(replay["rejected"]) == 1
    listed = mcp_tools.list_staged_imports(client_id)
    assert {row["coding"]["state"] for row in listed} == {"assistant"}
    conn = dbconn.get_connection()
    assert conn.execute("SELECT COUNT(*) FROM import_suggestions").fetchone()[0] == 3
    audit = conn.execute("SELECT new_values FROM audit_log WHERE table_name='import_suggestions' ORDER BY id LIMIT 1").fetchone()
    assert json.loads(audit[0])["accepted_ids"] == result["accepted"]
    conn.close()


def test_list_staged_imports_keeps_human_coding_for_inactive_account(
        client_id, accounts, monkeypatch):
    bank = Account.get_by_id(accounts["cash"])
    expense = Account.get_by_id(accounts["expense"])
    txn = _pending(client_id, bank.id)
    with dbconn.get_cursor(commit=True) as cursor:
        record_decision(txn.id, client_id, expense.id, None, cursor)
    expense.deactivate()
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "read")

    listed = mcp_tools.list_staged_imports(client_id)

    row = next(row for row in listed if row["id"] == txn.id)
    assert row["coding"]["state"] == "human_coded"
    assert row["coding"]["account_number"] == expense.account_number


def test_duplicate_input_writes_nothing(client_id, accounts, monkeypatch):
    bank = Account.get_by_id(accounts["cash"])
    expense = Account.get_by_id(accounts["expense"])
    txn = _pending(client_id, bank.id)
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    item = {"transaction_id": txn.id, "account_number": expense.account_number,
            "confidence": "low", "reason": "Invented"}
    with pytest.raises(ValueError, match="Duplicate"):
        mcp_tools.suggest_categories(client_id, [item, item])
    conn = dbconn.get_connection()
    assert conn.execute("SELECT COUNT(*) FROM import_suggestions").fetchone()[0] == 0
    conn.close()


def test_authorizer_levels(client_id, accounts, monkeypatch):
    bank = Account.get_by_id(accounts["cash"])
    expense = Account.get_by_id(accounts["expense"])
    txn = _pending(client_id, bank.id)
    item = {"transaction_id": txn.id, "account_number": expense.account_number,
            "confidence": "high", "reason": "Invented"}
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "read")
    with pytest.raises(Exception):
        mcp_tools.suggest_categories(client_id, [item])
    monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", "propose")
    suggestion_id = mcp_tools.suggest_categories(client_id, [item])["accepted"][0]
    for level in dbconn.ASSISTANT_ACCESS_LEVELS:
        monkeypatch.setattr(dbconn, "ASSISTANT_ACCESS_LEVEL", level)
        with pytest.raises(Exception):
            with dbconn.get_cursor(commit=True) as cursor:
                cursor.execute("UPDATE import_suggestions SET reason='changed' WHERE id=?", (suggestion_id,))
        with pytest.raises(Exception):
            with dbconn.get_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM import_suggestions WHERE id=?", (suggestion_id,))
