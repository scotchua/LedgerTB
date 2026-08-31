"""Executable oracle for MONEY-01 inventory rounding residuals."""

from datetime import date, timedelta

from database.connection import get_connection
from models.account import Account
from services.ar_ap import (
    create_customer, create_invoice, post_invoice, void_invoice,
)
from services.inventory import create_item, inventory_position, record_movement


def _inventory_setup(client_id, accounts):
    inventory = Account(
        client_id=client_id, account_number="1200", name="Inventory", type="Asset",
    )
    cogs = Account(
        client_id=client_id, account_number="5000", name="Cost of Goods Sold",
        type="Expense",
    )
    receivable = Account(
        client_id=client_id, account_number="1100", name="Accounts Receivable",
        type="Asset",
    )
    for account in (inventory, cogs, receivable):
        account.save()
    item_id = create_item(
        client_id, "WIDGET", "Widget", inventory.id, cogs.id,
    )
    customer = create_customer(client_id, "Inventory Customer")
    return item_id, customer.id, receivable.id, cogs.id


def _post_sale(client_id, customer_id, receivable_id, accounts, item_id, quantity,
               invoice_date):
    invoice = create_invoice(
        client_id,
        customer_id,
        [{
            "description": "Widgets",
            "quantity": quantity,
            "unit_price_cents": 500,
            "revenue_account_id": accounts["revenue"],
            "inventory_item_id": item_id,
        }],
        invoice_date,
        invoice_date + timedelta(days=30),
    )
    post_invoice(invoice.id, receivable_id)
    return invoice


def _control_balance(account_id):
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(jel.debit - jel.credit), 0)
            FROM journal_entry_lines jel
            JOIN journal_entries je ON je.id = jel.journal_entry_id
            WHERE jel.account_id = ?
            """,
            (account_id,),
        ).fetchone()
        return row[0]
    finally:
        conn.close()


def _cogs_line_amounts(account_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT jel.debit - jel.credit
            FROM journal_entry_lines jel
            JOIN journal_entries je ON je.id = jel.journal_entry_id
            WHERE jel.account_id = ?
            ORDER BY jel.id
            """,
            (account_id,),
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def test_single_cycle_clears_final_depletion_residual_to_cogs(client_id, accounts):
    item_id, customer_id, receivable_id, cogs_id = _inventory_setup(
        client_id, accounts,
    )
    record_movement(item_id, date(2026, 1, 1), "purchase", 3, 101)
    record_movement(item_id, date(2026, 1, 2), "purchase", 3, 100)

    _post_sale(
        client_id, customer_id, receivable_id, accounts, item_id, 6,
        date(2026, 1, 3),
    )

    # (3 units * 101 cents) + (3 units * 100 cents) = 603 cents of COGS.
    assert _control_balance(cogs_id) == 603


def test_three_cycles_conserve_acquired_cost(client_id, accounts):
    item_id, customer_id, receivable_id, cogs_id = _inventory_setup(
        client_id, accounts,
    )
    for cycle in range(3):
        purchase_date = date(2026, 2, 1) + timedelta(days=cycle * 3)
        record_movement(item_id, purchase_date, "purchase", 3, 101)
        record_movement(
            item_id, purchase_date + timedelta(days=1), "purchase", 3, 100,
        )
        _post_sale(
            client_id, customer_id, receivable_id, accounts, item_id, 6,
            purchase_date + timedelta(days=2),
        )

    ending_position = inventory_position(item_id)
    assert ending_position["quantity"] == 0
    # 3 cycles * ((3 * 101 cents) + (3 * 100 cents)) = 1,809 cents acquired.
    assert _control_balance(cogs_id) == 1809


def test_deplete_then_repurchase_starts_a_new_cost_pool(client_id, accounts):
    item_id, customer_id, receivable_id, cogs_id = _inventory_setup(
        client_id, accounts,
    )
    record_movement(item_id, date(2026, 3, 1), "purchase", 3, 101)
    record_movement(item_id, date(2026, 3, 2), "purchase", 3, 100)
    _post_sale(
        client_id, customer_id, receivable_id, accounts, item_id, 6,
        date(2026, 3, 3),
    )
    record_movement(item_id, date(2026, 3, 4), "purchase", 3, 202)
    _post_sale(
        client_id, customer_id, receivable_id, accounts, item_id, 3,
        date(2026, 3, 5),
    )

    # 603 cents in the first pool + (3 units * 202 cents) = 1,209 cents.
    assert _control_balance(cogs_id) == 1209


def test_void_final_depletion_restores_quantity_value_and_residual(client_id, accounts):
    item_id, customer_id, receivable_id, cogs_id = _inventory_setup(
        client_id, accounts,
    )
    record_movement(item_id, date(2026, 4, 1), "purchase", 3, 101)
    record_movement(item_id, date(2026, 4, 2), "purchase", 3, 100)
    invoice = _post_sale(
        client_id, customer_id, receivable_id, accounts, item_id, 6,
        date(2026, 4, 3),
    )
    void_invoice(invoice.id, date(2026, 4, 4))

    position = inventory_position(item_id)
    assert position["quantity"] == 6
    # Voiding the final depletion restores the original 603-cent pool.
    assert position["value_cents"] == 603
    # The sale and its void leave no net COGS.
    assert _control_balance(cogs_id) == 0


def test_whole_cent_average_has_no_residual(client_id, accounts):
    item_id, customer_id, receivable_id, cogs_id = _inventory_setup(
        client_id, accounts,
    )
    record_movement(item_id, date(2026, 5, 1), "purchase", 1, 100)
    record_movement(item_id, date(2026, 5, 2), "purchase", 1, 102)
    _post_sale(
        client_id, customer_id, receivable_id, accounts, item_id, 2,
        date(2026, 5, 3),
    )

    # (1 * 100 cents) + (1 * 102 cents) = 202 cents, with no residual.
    assert _control_balance(cogs_id) == 202
    # Exact extension needs one 202-cent COGS line and no residual line.
    assert _cogs_line_amounts(cogs_id) == [202]
    # A whole-cent depletion reports neither quantity nor residual value.
    assert inventory_position(item_id) == {
        "quantity": 0.0,
        "weighted_average_unit_cost_cents": 0,
        "value_cents": 0,
    }


def test_zero_quantity_position_reports_signed_residual(client_id, accounts):
    item_id, customer_id, receivable_id, _ = _inventory_setup(client_id, accounts)
    record_movement(item_id, date(2026, 6, 1), "purchase", 3, 101)
    record_movement(item_id, date(2026, 6, 2), "purchase", 3, 100)
    _post_sale(
        client_id, customer_id, receivable_id, accounts, item_id, 6,
        date(2026, 6, 3),
    )

    position = inventory_position(item_id)
    assert position["quantity"] == 0
    # 603 cents acquired - 606 cents of frozen-cost COGS = -3 cents.
    assert position["value_cents"] == -3
