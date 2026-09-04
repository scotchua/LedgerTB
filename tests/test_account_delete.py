"""Account deletion guard tests (M4).

Previously the Chart-of-Accounts page ran a raw DELETE guarded only by
has_transactions (journal entry lines). An account referenced solely by a
categorization rule or an imported transaction passed that guard, so the DELETE
hit a RESTRICT foreign key and raised an uncaught IntegrityError. Account.delete
now checks every referencing table and raises a clean ValueError instead.
"""

from datetime import date

import pytest

from conftest import post_entry
from database.connection import get_connection
from models.client import Client
from models.account import Account
from models.import_suggestion import ImportSuggestion
from models.transaction import ImportedTransaction
from services.pattern_learning import PatternLearner


def test_delete_unreferenced_account_succeeds(client_id):
    a = Account(client_id=client_id, account_number="9999", name="Temp", type="Expense")
    a.save()
    assert Account.deletion_blockers(a.id) == {}
    Account.delete(a.id, client_id=client_id)
    assert Account.get_by_id(a.id) is None


def test_delete_blocked_by_journal_entry(client_id, accounts):
    post_entry(client_id, date(2025, 1, 1),
               [(accounts["cash"], 100, 0), (accounts["revenue"], 0, 100)])
    assert "journal entry lines" in Account.deletion_blockers(accounts["cash"])
    with pytest.raises(ValueError):
        Account.delete(accounts["cash"], client_id=client_id)
    assert Account.get_by_id(accounts["cash"]) is not None  # survives


def test_delete_blocked_by_categorization_rule(client_id, accounts):
    """The M4 gap: an account with a learned rule but no journal entries used to
    pass has_transactions and then crash on the FK. Now it is cleanly blocked."""
    PatternLearner.learn_pattern(client_id, "STARBUCKS STORE 123", accounts["expense"])
    assert not Account.has_transactions(accounts["expense"])  # the old (insufficient) guard
    assert "categorization rules" in Account.deletion_blockers(accounts["expense"])
    with pytest.raises(ValueError):
        Account.delete(accounts["expense"], client_id=client_id)
    assert Account.get_by_id(accounts["expense"]) is not None


def test_delete_blocked_by_imported_transaction(client_id, accounts):
    ImportedTransaction(
        client_id=client_id, transaction_date=date(2025, 1, 1), description="X",
        amount=-10.0, bank_account_id=accounts["cash"],
        suggested_account_id=accounts["expense"], status="Pending",
    ).save()
    # Referenced as suggested_account_id...
    assert "imported transactions" in Account.deletion_blockers(accounts["expense"])
    # ...and as bank_account_id.
    assert "imported transactions" in Account.deletion_blockers(accounts["cash"])
    with pytest.raises(ValueError):
        Account.delete(accounts["expense"], client_id=client_id)


def test_suggestion_and_decided_accounts_each_block_delete(client_id, accounts):
    bank = Account.get_by_id(accounts["cash"])
    suggested = Account(client_id=client_id, account_number="6997", name="Suggested", type="Expense")
    suggested.save()
    decided = Account(client_id=client_id, account_number="6998", name="Decided", type="Expense")
    decided.save()
    transaction = ImportedTransaction(
        client_id=client_id, import_batch="blockers", transaction_date=date(2026, 1, 2),
        description="Invented purchase", amount=-12.34, bank_account_id=bank.id,
        status="Pending",
    )
    transaction.save()
    with get_connection() as conn:
        ImportSuggestion.insert(
            conn.cursor(), transaction.id, suggested.id, "medium", "match",
            "assistant", "blockers",
        )
        conn.execute(
            "UPDATE imported_transactions SET decided_account_id = ?, decided_at = datetime('now') "
            "WHERE id = ?", (decided.id, transaction.id)
        )
        conn.commit()

    assert Account.deletion_blockers(suggested.id) == {"import suggestions": 1}
    assert Account.deletion_blockers(decided.id) == {"imported transactions": 1}


def test_delete_cross_client_raises_and_preserves(client_id, accounts):
    other = Client(name="Other Co", entity_type="S-Corp", fiscal_year_end_month=12).save(seed_accounts=False)
    with pytest.raises(ValueError):
        Account.delete(accounts["cash"], client_id=other)
    assert Account.get_by_id(accounts["cash"]) is not None
