from datetime import date
import json

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from database.connection import get_connection
from models.account import Account
from models.import_coding import effective_coding, record_decision, record_decisions
from models.import_suggestion import ImportSuggestion
from models.transaction import ImportedTransaction
from tests.conftest import page_path


def _transaction(client_id, account_id, status="Pending"):
    row = ImportedTransaction(
        client_id=client_id, import_batch="suggestions", transaction_date=date(2026, 1, 2),
        description="Invented purchase", amount=-12.34, bank_account_id=account_id,
        status=status,
    )
    row.save()
    return row


def test_projection_precedence_and_stale_newest(client_id, accounts):
    bank = Account.get_by_id(accounts["cash"])
    expense = Account.get_by_id(accounts["expense"])
    other = Account(client_id=client_id, account_number="6998", name="Second Expense", type="Expense")
    other.save()
    txn = _transaction(client_id, bank.id)
    assert effective_coding(client_id)[txn.id].state == "unreviewed"
    conn = get_connection()
    cur = conn.cursor()
    first = ImportSuggestion.insert(cur, txn.id, expense.id, "medium", "older", "assistant", "one")
    second = ImportSuggestion.insert(cur, txn.id, other.id, "high", "newer", "assistant", "two")
    cur.execute("UPDATE import_suggestions SET created_at = '2026-01-01 00:00:00'")
    conn.commit()
    assert effective_coding(client_id)[txn.id].suggestion_id == second
    other.is_active = False
    other.save()
    coding = effective_coding(client_id)[txn.id]
    assert coding.state == "stale" and coding.suggestion_id == second
    with get_connection() as decision_conn:
        record_decision(txn.id, client_id, expense.id, first, decision_conn.cursor())
        decision_conn.commit()
    assert effective_coding(client_id)[txn.id].state == "human_coded"


def test_human_clear_and_batch_audit(client_id, accounts):
    bank = Account.get_by_id(accounts["cash"])
    expense = Account.get_by_id(accounts["expense"])
    rows = [_transaction(client_id, bank.id) for _ in range(2)]
    operation_id = record_decisions([
        {"transaction_id": rows[0].id, "account_id": expense.id},
        {"transaction_id": rows[1].id, "account_id": None},
    ], client_id)
    coding = effective_coding(client_id)
    assert coding[rows[0].id].state == "human_coded"
    assert coding[rows[1].id].state == "human_cleared"
    conn = get_connection()
    audits = conn.execute(
        "SELECT new_values FROM audit_log WHERE table_name='imported_transactions' "
        "AND action='UPDATE' ORDER BY id DESC LIMIT 2"
    ).fetchall()
    assert all(operation_id in row[0] for row in audits)
    conn.close()


def test_triggers_reject_cross_client_and_decided(client_id, accounts):
    bank = Account.get_by_id(accounts["cash"])
    txn = _transaction(client_id, bank.id)
    conn = get_connection()
    other_client = conn.execute("INSERT INTO clients (name, entity_type) VALUES ('Other Co', 'Other')").lastrowid
    other_account = conn.execute(
        "INSERT INTO accounts (client_id, account_number, name, type, is_active) "
        "VALUES (?, '6100', 'Other Expense', 'Expense', 1)", (other_client,)
    ).lastrowid
    with pytest.raises(Exception, match="another client"):
        ImportSuggestion.insert(conn.cursor(), txn.id, other_account, "high", "bad", "in_app", "cross")
    conn.rollback()
    conn.execute(
        "UPDATE imported_transactions SET decided_at=datetime('now') WHERE id=?", (txn.id,)
    )
    conn.commit()
    with pytest.raises(Exception, match="already decided"):
        ImportSuggestion.insert(conn.cursor(), txn.id, other_account, "high", "bad", "in_app", "decided")
    conn.close()


def test_record_decision_rejects_suggestion_from_another_transaction(client_id, accounts):
    bank = Account.get_by_id(accounts["cash"])
    expense = Account.get_by_id(accounts["expense"])
    first = _transaction(client_id, bank.id)
    second = _transaction(client_id, bank.id)
    conn = get_connection()
    suggestion_id = ImportSuggestion.insert(
        conn.cursor(), first.id, expense.id, "high", "match", "assistant", "owned"
    )
    conn.commit()

    with pytest.raises(ValueError, match="does not belong"):
        record_decision(second.id, client_id, expense.id, suggestion_id, conn.cursor())
    conn.commit()

    row = conn.execute(
        "SELECT decided_account_id, decided_at, decided_suggestion_id "
        "FROM imported_transactions WHERE id = ?", (second.id,)
    ).fetchone()
    assert tuple(row) == (None, None, None)
    conn.close()


def test_delete_decided_suggestion_preserves_audit_evidence(client_id, accounts):
    bank = Account.get_by_id(accounts["cash"])
    expense = Account.get_by_id(accounts["expense"])
    txn = _transaction(client_id, bank.id)
    conn = get_connection()
    suggestion_id = ImportSuggestion.insert(
        conn.cursor(), txn.id, expense.id, "high", "match", "assistant", "delete-one"
    )
    record_decision(txn.id, client_id, expense.id, suggestion_id, conn.cursor())
    conn.commit()
    conn.close()

    ImportedTransaction.delete(txn.id)

    conn = get_connection()
    old_values = json.loads(conn.execute(
        "SELECT old_values FROM audit_log WHERE table_name = 'imported_transactions' "
        "AND record_id = ? AND action = 'DELETE'", (txn.id,)
    ).fetchone()[0])
    suggestion_audits = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE table_name = 'import_suggestions' "
        "AND record_id = ? AND action = 'DELETE'", (suggestion_id,)
    ).fetchone()[0]
    assert old_values["decided_account_id"] == expense.id
    assert old_values["decided_suggestion_id"] == suggestion_id
    assert suggestion_audits == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM imported_transactions WHERE id = ?", (txn.id,)
    ).fetchone()[0] == 0
    conn.close()


def test_delete_batch_decided_suggestion_preserves_audit_evidence(client_id, accounts):
    bank = Account.get_by_id(accounts["cash"])
    expense = Account.get_by_id(accounts["expense"])
    rows = [_transaction(client_id, bank.id) for _ in range(2)]
    conn = get_connection()
    suggestion_ids = [
        ImportSuggestion.insert(
            conn.cursor(), row.id, expense.id, "medium", "match", "assistant",
            f"delete-batch-{index}",
        )
        for index, row in enumerate(rows)
    ]
    record_decision(rows[0].id, client_id, expense.id, suggestion_ids[0], conn.cursor())
    conn.commit()
    conn.close()

    ImportedTransaction.delete_batch("suggestions")

    conn = get_connection()
    transaction_audits = conn.execute(
        "SELECT record_id, old_values FROM audit_log "
        "WHERE table_name = 'imported_transactions' AND action = 'DELETE' "
        "AND record_id IN (?, ?)", (rows[0].id, rows[1].id)
    ).fetchall()
    suggestion_audits = conn.execute(
        "SELECT record_id FROM audit_log WHERE table_name = 'import_suggestions' "
        "AND action = 'DELETE' AND record_id IN (?, ?)", suggestion_ids
    ).fetchall()
    decided = json.loads(next(
        audit["old_values"] for audit in transaction_audits
        if audit["record_id"] == rows[0].id
    ))
    assert len(transaction_audits) == 2
    assert decided["decided_account_id"] == expense.id
    assert decided["decided_suggestion_id"] == suggestion_ids[0]
    assert {audit["record_id"] for audit in suggestion_audits} == set(suggestion_ids)
    conn.close()


def _review_page(monkeypatch, client_id):
    import utils.client_selector as selector
    from services.categorization import CategorizationService

    monkeypatch.setattr(selector, "render_client_selector", lambda: client_id)
    monkeypatch.setattr(selector, "apply_sidebar_style", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "page_link", lambda *args, **kwargs: None)
    monkeypatch.setattr(CategorizationService, "is_available", lambda self: True)
    page = AppTest.from_file(
        page_path("pages/4_Import_Transactions.py"), default_timeout=60
    )
    page.session_state["import_active_tab"] = "Review & Categorize"
    return page


def _three_coding_states(client_id, accounts):
    bank = Account.get_by_id(accounts["cash"])
    expense = Account.get_by_id(accounts["expense"])
    rows = [_transaction(client_id, bank.id) for _ in range(3)]
    conn = get_connection()
    suggestion_id = ImportSuggestion.insert(
        conn.cursor(), rows[0].id, expense.id, "high", "assistant match",
        "assistant", "page-suggestion",
    )
    record_decision(rows[1].id, client_id, None, None, conn.cursor())
    record_decision(rows[2].id, client_id, expense.id, None, conn.cursor())
    conn.commit()
    conn.close()
    return rows, expense, suggestion_id


def test_review_preserves_decisions_and_categorizes_only_unreviewed(
    client_id, accounts, monkeypatch,
):
    from services.categorization import CategorizationService
    from utils.import_review import row_key

    rows, expense, _ = _three_coding_states(client_id, accounts)
    received = []

    def categorize(self, transactions, available_accounts, business_context=None):
        received.extend(transaction["staged_id"] for transaction in transactions)
        for transaction in transactions:
            transaction["suggested_account_id"] = expense.id
            transaction["confidence"] = "85%"
            transaction["reason"] = "model match"
        self.last_matched = len(transactions)
        self.last_total = len(transactions)

    monkeypatch.setattr(CategorizationService, "categorize_transactions", categorize)
    page = _review_page(monkeypatch, client_id).run()
    page.button(key="load_staged_imports").click().run()

    review_rows = page.session_state["transactions_to_review"]
    keys = {row["staged_id"]: row_key("cat", row) for row in review_rows}
    assert not page.exception
    assert page.selectbox(key=keys[rows[0].id]).value is None
    assert page.selectbox(key=keys[rows[1].id]).value is None
    assert page.selectbox(key=keys[rows[2].id]).value == expense.id
    assert any("AI suggests" in str(caption.value) for caption in page.caption)

    next(button for button in page.button if button.label.startswith("Categorize ")).click().run()
    assert not page.exception
    assert received == [rows[0].id]
    conn = get_connection()
    new_suggestions = conn.execute(
        "SELECT imported_transaction_id, confidence FROM import_suggestions "
        "WHERE source = 'in_app' ORDER BY imported_transaction_id"
    ).fetchall()
    conn.close()
    assert [(row["imported_transaction_id"], row["confidence"])
            for row in new_suggestions] == [(rows[0].id, "medium")]


def test_transfer_hides_suggestion_actions_without_deciding(
    client_id, accounts, monkeypatch,
):
    from utils.import_review import row_key

    rows, _, _ = _three_coding_states(client_id, accounts)
    page = _review_page(monkeypatch, client_id).run()
    page.button(key="load_staged_imports").click().run()
    suggested_row = next(
        row for row in page.session_state["transactions_to_review"]
        if row["staged_id"] == rows[0].id
    )
    page.checkbox(key=row_key("xfer", suggested_row)).check().run()

    assert not page.exception
    assert not any(button.label == "Use suggestion" for button in page.button)
    assert not any("AI suggests" in str(caption.value) for caption in page.caption)
    conn = get_connection()
    decided_at = conn.execute(
        "SELECT decided_at FROM imported_transactions WHERE id = ?", (rows[0].id,)
    ).fetchone()[0]
    conn.close()
    assert decided_at is None
