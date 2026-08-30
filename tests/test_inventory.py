from datetime import date
from io import StringIO

import pytest

from database.connection import get_connection
from models.account import Account
from models.fiscal_period import FiscalPeriod
from models.journal_entry import JournalEntry
from services.inventory import (
    create_item, inventory_position, inventory_rollforward, record_movement,
    record_movements_from_csv,
)


def _inventory_setup(client_id, accounts):
    inventory = Account(
        client_id=client_id, account_number="1200", name="Inventory", type="Asset"
    )
    inventory.save()
    cogs = Account(
        client_id=client_id, account_number="5000", name="Cost of Goods Sold",
        type="Expense",
    )
    cogs.save()
    item_id = create_item(client_id, "WIDGET", "Widget", inventory.id, cogs.id)
    return item_id, inventory.id, cogs.id


def test_weighted_average_and_sale_use_derived_current_cost(client_id, accounts):
    item_id, _, _ = _inventory_setup(client_id, accounts)
    record_movement(item_id, date(2026, 1, 2), "purchase", 10, 1000)
    position = record_movement(item_id, date(2026, 1, 3), "purchase", 20, 1300)
    assert position["quantity"] == 30
    assert position["weighted_average_unit_cost_cents"] == 1200
    assert position["value_cents"] == 36000

    position = record_movement(item_id, date(2026, 1, 4), "sale", -5)
    assert position["quantity"] == 25
    assert position["weighted_average_unit_cost_cents"] == 1200
    assert position["value_cents"] == 30000
    conn = get_connection()
    sale = conn.execute(
        "SELECT unit_cost_cents FROM inventory_movements WHERE movement_type = 'sale'"
    ).fetchone()
    conn.close()
    assert sale["unit_cost_cents"] == 1200


def test_impossible_backdated_sale_rolls_back_movement_and_audit(client_id, accounts):
    item_id, _, _ = _inventory_setup(client_id, accounts)
    record_movement(item_id, date(2026, 1, 10), "purchase", 10, 1000)
    conn = get_connection()
    before_movements = conn.execute(
        "SELECT COUNT(*) FROM inventory_movements WHERE inventory_item_id = ?",
        (item_id,),
    ).fetchone()[0]
    before_audits = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE table_name = 'inventory_movements'"
    ).fetchone()[0]
    conn.close()

    with pytest.raises(ValueError, match="history cannot produce negative quantity"):
        record_movement(item_id, date(2026, 1, 5), "sale", -1)

    conn = get_connection()
    movements = conn.execute(
        "SELECT COUNT(*) FROM inventory_movements WHERE inventory_item_id = ?",
        (item_id,),
    ).fetchone()[0]
    audits = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE table_name = 'inventory_movements'"
    ).fetchone()[0]
    conn.close()
    assert movements - before_movements == 0
    assert audits - before_audits == 0


def test_valid_backdated_purchase_before_sale_is_accepted(client_id, accounts):
    item_id, _, _ = _inventory_setup(client_id, accounts)
    record_movement(item_id, date(2026, 1, 5), "purchase", 10, 1000)
    record_movement(item_id, date(2026, 1, 10), "sale", -5)

    result = record_movement(item_id, date(2026, 1, 3), "purchase", 2, 800)

    assert result["quantity"] == 7
    assert result["value_cents"] == 6600


def test_purchase_explicitly_supports_posting_and_subledger_only(client_id, accounts):
    item_id, inventory_id, _ = _inventory_setup(client_id, accounts)
    unposted = record_movement(
        item_id, date(2026, 2, 1), "purchase", 4, 2500,
        post_journal_entry=False,
    )
    assert unposted["journal_entry_id"] is None

    posted = record_movement(
        item_id, date(2026, 2, 2), "purchase", 2, 2500,
        post_journal_entry=True, offset_account_id=accounts["cash"],
    )
    entry = JournalEntry.get_by_id(posted["journal_entry_id"])
    assert [(line.account_id, line.debit, line.credit) for line in entry.lines] == [
        (inventory_id, 50.0, 0.0), (accounts["cash"], 0.0, 50.0),
    ]


def test_adjustment_posts_signed_balanced_entry_and_movement_atomically(client_id, accounts):
    item_id, inventory_id, cogs_id = _inventory_setup(client_id, accounts)
    record_movement(item_id, date(2026, 3, 1), "purchase", 10, 800)
    result = record_movement(item_id, date(2026, 3, 31), "adjustment", -3)

    entry = JournalEntry.get_by_id(result["journal_entry_id"])
    assert entry.is_balanced()
    assert [(line.account_id, line.debit, line.credit) for line in entry.lines] == [
        (inventory_id, 0.0, 24.0), (cogs_id, 24.0, 0.0),
    ]
    conn = get_connection()
    movement = conn.execute(
        "SELECT journal_entry_id FROM inventory_movements WHERE id = ?",
        (result["movement_id"],),
    ).fetchone()
    audit_count = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE table_name = 'inventory_movements' "
        "AND record_id = ?", (result["movement_id"],),
    ).fetchone()[0]
    conn.close()
    assert movement["journal_entry_id"] == entry.id
    assert audit_count == 1


def test_count_increase_posts_inventory_debit_and_cogs_credit(client_id, accounts):
    item_id, inventory_id, cogs_id = _inventory_setup(client_id, accounts)
    record_movement(item_id, date(2026, 3, 1), "purchase", 10, 800)
    result = record_movement(item_id, date(2026, 3, 31), "count", 2)

    entry = JournalEntry.get_by_id(result["journal_entry_id"])
    assert [(line.account_id, line.debit, line.credit) for line in entry.lines] == [
        (inventory_id, 16.0, 0.0), (cogs_id, 0.0, 16.0),
    ]


def test_adjustment_je_uses_frozen_cost_for_fractional_average(client_id, accounts):
    item_id, inventory_id, cogs_id = _inventory_setup(client_id, accounts)
    record_movement(item_id, date(2026, 3, 1), "purchase", 10, 1000)
    record_movement(item_id, date(2026, 3, 2), "purchase", 5, 1200)

    result = record_movement(item_id, date(2026, 3, 31), "adjustment", -4)

    conn = get_connection()
    movement = conn.execute(
        "SELECT quantity, unit_cost_cents FROM inventory_movements WHERE id = ?",
        (result["movement_id"],),
    ).fetchone()
    conn.close()
    expected_cents = abs(round(movement["quantity"] * movement["unit_cost_cents"]))
    entry = JournalEntry.get_by_id(result["journal_entry_id"])
    assert movement["unit_cost_cents"] == 1067
    assert [(line.account_id, line.debit, line.credit) for line in entry.lines] == [
        (inventory_id, 0.0, expected_cents / 100),
        (cogs_id, expected_cents / 100, 0.0),
    ]


def test_csv_import_documents_and_imports_purchase_and_reduction(client_id, accounts):
    item_id, _, _ = _inventory_setup(client_id, accounts)
    imported = record_movements_from_csv(
        item_id,
        StringIO("date,quantity,unit_cost\n2026-04-01,10,12.50\n2026-04-02,-2,\n"),
    )
    assert len(imported) == 2
    assert inventory_position(item_id) == {
        "quantity": 8.0,
        "weighted_average_unit_cost_cents": 1250,
        "value_cents": 10000,
    }


def test_csv_replay_failure_is_atomic_and_corrected_retry_does_not_duplicate(
    client_id, accounts,
):
    item_id, _, _ = _inventory_setup(client_id, accounts)
    invalid = StringIO(
        "date,quantity,unit_cost\n"
        "2026-04-02,10,12.50\n"
        "2026-04-01,-1,\n"
    )

    with pytest.raises(ValueError, match="history cannot produce negative quantity"):
        record_movements_from_csv(item_id, invalid)

    conn = get_connection()
    assert conn.execute(
        "SELECT COUNT(*) FROM inventory_movements WHERE inventory_item_id = ?",
        (item_id,),
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE table_name = 'inventory_movements'"
    ).fetchone()[0] == 0
    conn.close()

    imported = record_movements_from_csv(
        item_id,
        StringIO(
            "date,quantity,unit_cost\n"
            "2026-04-01,10,12.50\n"
            "2026-04-02,-2,\n"
        ),
    )
    assert len(imported) == 2
    assert inventory_position(item_id)["quantity"] == 8


def test_backdated_purchase_does_not_reprice_posted_sale(client_id, accounts):
    item_id, _, _ = _inventory_setup(client_id, accounts)
    record_movement(item_id, date(2026, 1, 1), "purchase", 10, 1000)
    sale = record_movement(item_id, date(2026, 1, 10), "sale", -5)

    record_movement(item_id, date(2026, 1, 5), "purchase", 10, 2000)

    conn = get_connection()
    stored_cost = conn.execute(
        "SELECT unit_cost_cents FROM inventory_movements WHERE id = ?",
        (sale["movement_id"],),
    ).fetchone()[0]
    conn.close()
    assert stored_cost == 1000
    report = inventory_rollforward(item_id, date(2026, 1, 1), date(2026, 1, 31))
    assert report["additions_value_cents"] == 30000
    assert report["reductions_value_cents"] == 5000
    assert report["closing_value_cents"] == 25000
    assert report["opening_value_cents"] + report["additions_value_cents"] - (
        report["reductions_value_cents"]
    ) == report["closing_value_cents"]


def test_closed_year_rejects_direct_and_csv_movements(client_id, accounts):
    item_id, _, _ = _inventory_setup(client_id, accounts)
    FiscalPeriod(
        client_id=client_id, period_name="FY 2025", period_type="Year",
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), is_closed=True,
    ).save()

    with pytest.raises(ValueError, match="FY 2025 is closed"):
        record_movement(item_id, date(2025, 12, 1), "purchase", 1, 1000)
    with pytest.raises(ValueError, match="FY 2025 is closed"):
        record_movements_from_csv(
            item_id, StringIO("date,quantity,unit_cost\n2025-12-01,1,10.00\n")
        )

    conn = get_connection()
    assert conn.execute(
        "SELECT COUNT(*) FROM inventory_movements WHERE inventory_item_id = ?",
        (item_id,),
    ).fetchone()[0] == 0
    conn.close()


def test_rollforward_quantity_arithmetic(client_id, accounts):
    item_id, _, _ = _inventory_setup(client_id, accounts)
    record_movement(item_id, date(2025, 12, 15), "purchase", 10, 1000)
    record_movement(item_id, date(2026, 1, 10), "purchase", 5, 1200)
    record_movement(item_id, date(2026, 2, 1), "sale", -4)
    record_movement(item_id, date(2026, 3, 31), "count", -1)

    report = inventory_rollforward(item_id, date(2026, 1, 1), date(2026, 3, 31))
    assert report["opening_quantity"] == 10
    assert report["additions_quantity"] == 5
    assert report["reductions_quantity"] == 4
    assert report["adjustments_quantity"] == -1
    assert report["additions_value_cents"] == 6000
    # Frozen stored-cost policy rounds the unit cost before extending quantity.
    assert report["reductions_value_cents"] == 4268
    assert report["adjustments_value_cents"] == -1067
    assert report["closing_quantity"] == 10
    assert (
        report["opening_quantity"] + report["additions_quantity"]
        - report["reductions_quantity"] + report["adjustments_quantity"]
        == report["closing_quantity"]
    )
    assert report["quantity_check"] == 0
