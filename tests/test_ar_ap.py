from datetime import date
import threading
import time

import pytest

from database.connection import get_connection
from models.account import Account
from models.client import Client
from models.journal_entry import JournalEntry
import services.ar_ap as ar_ap
from services.ar_ap import (apply_customer_credit, create_bill, create_customer,
                            create_invoice, create_vendor, get_ar_aging,
                            list_customer_credits, list_invoices, post_bill,
                            post_invoice, record_customer_payment,
                            record_vendor_payment, refund_customer_credit,
                            void_invoice, void_payment)
from services.inventory import create_item, inventory_position, record_movement


@pytest.fixture
def ar_ap_accounts(client_id, accounts):
    ar = Account(client_id=client_id, account_number="1100", name="Accounts Receivable", type="Asset")
    ar2 = Account(client_id=client_id, account_number="1110", name="Other Receivable", type="Asset")
    ap = Account(client_id=client_id, account_number="2100", name="Accounts Payable", type="Liability")
    revenue_2 = Account(client_id=client_id, account_number="4100", name="Project Revenue", type="Revenue")
    expense_2 = Account(client_id=client_id, account_number="6100", name="Supplies Expense", type="Expense")
    for account in (ar, ar2, ap, revenue_2, expense_2):
        account.save()
    return {**accounts, "ar": ar.id, "ar2": ar2.id, "ap": ap.id,
            "revenue_2": revenue_2.id, "expense_2": expense_2.id}


def _invoice(client_id, customer_id, accounts, amount=10000, due=date(2026, 8, 31), post=True,
             control=None):
    invoice = create_invoice(client_id, customer_id, [{"description": "Work", "quantity": 1,
        "unit_price_cents": amount, "revenue_account_id": accounts["revenue"]}],
        date(2026, 8, 1), due)
    if post:
        post_invoice(invoice.id, control or accounts["ar"])
    return invoice


def _entry_lines(entry_id, include_memo=False):
    conn = get_connection()
    rows = conn.execute(
        "SELECT account_id, debit, credit, memo FROM journal_entry_lines WHERE journal_entry_id = ? ORDER BY id",
        (entry_id,),
    ).fetchall()
    conn.close()
    if include_memo:
        return [(row["account_id"], row["debit"], row["credit"], row["memo"]) for row in rows]
    return [(row["account_id"], row["debit"], row["credit"]) for row in rows]


def _scalar(sql, params=()):
    conn = get_connection()
    value = conn.execute(sql, params).fetchone()[0]
    conn.close()
    return value


def _audit_actions(since_id=0):
    conn = get_connection()
    rows = conn.execute(
        "SELECT table_name, action FROM audit_log WHERE id > ? ORDER BY id", (since_id,),
    ).fetchall()
    conn.close()
    return [(row["table_name"], row["action"]) for row in rows]


def _inventory_item(client_id, accounts):
    inventory = Account(client_id=client_id, account_number="1200", name="Inventory", type="Asset")
    cogs = Account(client_id=client_id, account_number="5000", name="COGS", type="Expense")
    inventory.save()
    cogs.save()
    return create_item(client_id, "WIDGET", "Widget", inventory.id, cogs.id), inventory.id, cogs.id


def test_invoice_inventory_post_and_void_use_frozen_cost(client_id, ar_ap_accounts):
    item_id, inventory_id, cogs_id = _inventory_item(client_id, ar_ap_accounts)
    record_movement(item_id, date(2026, 7, 1), "purchase", 10, 1001)
    customer = create_customer(client_id, "Inventory Customer")
    invoice = create_invoice(client_id, customer.id, [
        {"description": "Widgets A", "quantity": 2, "unit_price_cents": 3000,
         "revenue_account_id": ar_ap_accounts["revenue"], "inventory_item_id": item_id},
        {"description": "Widgets B", "quantity": 3, "unit_price_cents": 3000,
         "revenue_account_id": ar_ap_accounts["revenue"], "inventory_item_id": item_id},
        {"description": "Service", "quantity": 1, "unit_price_cents": 500,
         "revenue_account_id": ar_ap_accounts["revenue"]},
    ], date(2026, 8, 1), date(2026, 8, 31))

    posted = post_invoice(invoice.id, ar_ap_accounts["ar"])
    conn = get_connection()
    movements = conn.execute(
        "SELECT * FROM inventory_movements WHERE source_type = 'invoice' ORDER BY source_line_id"
    ).fetchall()
    cogs_entry_id = movements[0]["journal_entry_id"]
    conn.close()
    assert len(movements) == 2
    assert [(row["source_id"], row["quantity"], row["unit_cost_cents"])
            for row in movements] == [(invoice.id, -2, 1001), (invoice.id, -3, 1001)]
    assert len({row["source_line_id"] for row in movements}) == 2
    assert _entry_lines(posted.journal_entry_id) == [
        (ar_ap_accounts["ar"], 15500, 0),
        (ar_ap_accounts["revenue"], 0, 6000),
        (ar_ap_accounts["revenue"], 0, 9000),
        (ar_ap_accounts["revenue"], 0, 500),
    ]
    assert _entry_lines(cogs_entry_id) == [
        (cogs_id, 2002, 0), (inventory_id, 0, 2002),
        (cogs_id, 3003, 0), (inventory_id, 0, 3003),
    ]
    assert inventory_position(item_id)["quantity"] == 5

    record_movement(item_id, date(2026, 8, 10), "purchase", 10, 2000)
    void_invoice(invoice.id, date(2026, 8, 20))
    conn = get_connection()
    reversals = conn.execute(
        "SELECT * FROM inventory_movements WHERE source_type = 'invoice_void' ORDER BY source_line_id"
    ).fetchall()
    reversal_entry_id = reversals[0]["journal_entry_id"]
    conn.close()
    assert [(row["quantity"], row["unit_cost_cents"]) for row in reversals] == [
        (2, 1001), (3, 1001),
    ]
    assert _entry_lines(reversal_entry_id) == [
        (inventory_id, 2002, 0), (cogs_id, 0, 2002),
        (inventory_id, 3003, 0), (cogs_id, 0, 3003),
    ]
    assert inventory_position(item_id)["quantity"] == 20


def test_invoice_inventory_negative_stock_rolls_back_everything(client_id, ar_ap_accounts):
    item_id, _, _ = _inventory_item(client_id, ar_ap_accounts)
    record_movement(item_id, date(2026, 8, 1), "purchase", 1, 1000)
    customer = create_customer(client_id, "No Stock Customer")
    invoice = create_invoice(client_id, customer.id, [{
        "description": "Widgets", "quantity": 2, "unit_price_cents": 3000,
        "revenue_account_id": ar_ap_accounts["revenue"], "inventory_item_id": item_id,
    }], date(2026, 8, 2), date(2026, 8, 31))
    before_entries = _scalar("SELECT COUNT(*) FROM journal_entries")
    before_movements = _scalar("SELECT COUNT(*) FROM inventory_movements")
    before_audits = _scalar("SELECT COUNT(*) FROM audit_log")

    with pytest.raises(ValueError, match="Movement cannot reduce inventory below zero"):
        post_invoice(invoice.id, ar_ap_accounts["ar"])

    assert _scalar("SELECT COUNT(*) FROM journal_entries") == before_entries
    assert _scalar("SELECT COUNT(*) FROM inventory_movements") == before_movements
    assert _scalar("SELECT COUNT(*) FROM audit_log") == before_audits
    assert _scalar("SELECT status FROM invoices WHERE id = ?", (invoice.id,)) == "draft"


def test_invoice_inventory_duplicate_post_refuses_without_duplicate_movements(
    client_id, ar_ap_accounts,
):
    item_id, _, _ = _inventory_item(client_id, ar_ap_accounts)
    record_movement(item_id, date(2026, 8, 1), "purchase", 2, 1000)
    customer = create_customer(client_id, "Replay Customer")
    invoice = create_invoice(client_id, customer.id, [{
        "description": "Widget", "quantity": 1, "unit_price_cents": 3000,
        "revenue_account_id": ar_ap_accounts["revenue"], "inventory_item_id": item_id,
    }], date(2026, 8, 2), date(2026, 8, 31))
    post_invoice(invoice.id, ar_ap_accounts["ar"])

    with pytest.raises(ValueError, match="already been posted"):
        post_invoice(invoice.id, ar_ap_accounts["ar"])

    assert _scalar(
        "SELECT COUNT(*) FROM inventory_movements WHERE source_type = 'invoice' AND source_id = ?",
        (invoice.id,),
    ) == 1


def test_service_invoice_has_no_inventory_entries(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Service Customer")
    invoice = _invoice(client_id, customer.id, ar_ap_accounts, post=False)
    before_entries = _scalar("SELECT COUNT(*) FROM journal_entries")
    post_invoice(invoice.id, ar_ap_accounts["ar"])
    assert _scalar("SELECT COUNT(*) FROM journal_entries") == before_entries + 1
    assert _scalar("SELECT COUNT(*) FROM inventory_movements") == 0
    void_invoice(invoice.id, date(2026, 8, 20))
    assert _scalar("SELECT COUNT(*) FROM journal_entries") == before_entries + 2
    assert _scalar("SELECT COUNT(*) FROM inventory_movements") == 0


def test_invoice_and_bill_post_exact_balanced_entries_and_audits(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Northwind Labs")
    invoice = create_invoice(client_id, customer.id, [
        {"description": "Consulting", "quantity": 2, "unit_price_cents": 12550,
         "revenue_account_id": ar_ap_accounts["revenue"]},
        {"description": "Setup", "quantity": 1, "unit_price_cents": 4995,
         "revenue_account_id": ar_ap_accounts["revenue_2"]},
    ], date(2026, 8, 1), date(2026, 8, 31))
    posted_invoice = post_invoice(invoice.id, ar_ap_accounts["ar"])
    assert _entry_lines(posted_invoice.journal_entry_id, include_memo=True) == [
        (ar_ap_accounts["ar"], 30095, 0, None),
        (ar_ap_accounts["revenue"], 0, 25100, "Consulting"),
        (ar_ap_accounts["revenue_2"], 0, 4995, "Setup"),
    ]
    assert _audit_actions()[-3:] == [
        ("invoices", "INSERT"),
        ("journal_entries", "INSERT"),
        ("invoices", "UPDATE"),
    ]

    vendor = create_vendor(client_id, "Office Market")
    bill = create_bill(client_id, vendor.id, [
        {"description": "Paper", "quantity": 3, "unit_price_cents": 1234,
         "expense_account_id": ar_ap_accounts["expense"]},
        {"description": "Ink", "quantity": 2, "unit_price_cents": 2499,
         "expense_account_id": ar_ap_accounts["expense_2"]},
    ], date(2026, 8, 2), date(2026, 9, 1))
    posted_bill = post_bill(bill.id, ar_ap_accounts["ap"])
    assert _entry_lines(posted_bill.journal_entry_id, include_memo=True) == [
        (ar_ap_accounts["expense"], 3702, 0, "Paper"),
        (ar_ap_accounts["expense_2"], 4998, 0, "Ink"),
        (ar_ap_accounts["ap"], 0, 8700, None),
    ]
    assert _audit_actions()[-3:] == [
        ("bills", "INSERT"),
        ("journal_entries", "INSERT"),
        ("bills", "UPDATE"),
    ]


def test_reposting_invoice_and_bill_is_refused(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Posted Customer")
    invoice = _invoice(client_id, customer.id, ar_ap_accounts)
    with pytest.raises(ValueError, match="already been posted"):
        post_invoice(invoice.id, ar_ap_accounts["ar"])

    vendor = create_vendor(client_id, "Posted Vendor")
    bill = create_bill(client_id, vendor.id, [{"description": "Fee", "quantity": 1,
        "unit_price_cents": 5000, "expense_account_id": ar_ap_accounts["expense"]}])
    post_bill(bill.id, ar_ap_accounts["ap"])
    with pytest.raises(ValueError, match="already been posted"):
        post_bill(bill.id, ar_ap_accounts["ap"])


def test_vendor_normalization_and_foreign_keys_remain_valid(client_id, ar_ap_accounts):
    vendor = create_vendor(client_id, "  BLUE   Sky  Supply ")
    assert vendor.normalized_name == "blue sky supply"
    conn = get_connection()
    stored = conn.execute(
        "SELECT normalized_name FROM vendors WHERE id = ?", (vendor.id,),
    ).fetchone()
    assert stored["normalized_name"] == "blue sky supply"
    conn.execute(
        "INSERT INTO categorization_rules (client_id, vendor_id, pattern, default_account_id) "
        "VALUES (?, ?, ?, ?)",
        (client_id, vendor.id, "BLUE SKY", ar_ap_accounts["expense"]),
    )
    conn.commit()
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_customer_payment_audit_attribution_sequence(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Audit Customer")
    invoices = [_invoice(client_id, customer.id, ar_ap_accounts, amount)
                for amount in (1000, 2000)]
    before = _scalar("SELECT COALESCE(MAX(id), 0) FROM audit_log")
    record_customer_payment(
        client_id, customer.id, date(2026, 8, 15), 3000, ar_ap_accounts["cash"],
        [{"invoice_id": invoices[0].id, "amount_cents": 1000},
         {"invoice_id": invoices[1].id, "amount_cents": 2000}],
    )
    assert _audit_actions(before) == [
        ("journal_entries", "INSERT"),
        ("payment_allocations", "INSERT"),
        ("payment_allocations", "INSERT"),
        ("payments", "INSERT"),
        ("invoices", "UPDATE"),
        ("invoices", "UPDATE"),
    ]


def test_stored_control_account_prevents_cash_on_both_sides(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "P0 Customer")
    invoice = _invoice(client_id, customer.id, ar_ap_accounts)
    stored = _scalar("SELECT control_account_id FROM invoices WHERE id = ?", (invoice.id,))
    assert stored == ar_ap_accounts["ar"]
    with pytest.raises(ValueError, match="money account must differ"):
        record_customer_payment(client_id, customer.id, date.today(), 10000,
                                ar_ap_accounts["ar"], [{"invoice_id": invoice.id,
                                                       "amount_cents": 10000}])
    assert _scalar("SELECT COUNT(*) FROM payments") == 0


def test_posting_rejects_control_account_used_by_a_line(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Posting Guard")
    invoice = create_invoice(client_id, customer.id, [{"description": "Bad line", "quantity": 1,
        "unit_price_cents": 1000, "revenue_account_id": ar_ap_accounts["revenue"]}])
    conn = get_connection()
    conn.execute("UPDATE accounts SET type = 'Asset' WHERE id = ?", (ar_ap_accounts["revenue"],))
    conn.commit(); conn.close()
    with pytest.raises(ValueError, match="differ from every document line"):
        post_invoice(invoice.id, ar_ap_accounts["revenue"])


def test_one_payment_allocates_three_invoices_with_one_entry(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Three Docs")
    invoices = [_invoice(client_id, customer.id, ar_ap_accounts, amount)
                for amount in (1000, 2000, 3000)]
    payment_id = record_customer_payment(
        client_id, customer.id, date(2026, 8, 15), 5000, ar_ap_accounts["cash"],
        [{"invoice_id": invoices[0].id, "amount_cents": 1000},
         {"invoice_id": invoices[1].id, "amount_cents": 1000},
         {"invoice_id": invoices[2].id, "amount_cents": 3000}],
    )
    conn = get_connection()
    payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    allocations = conn.execute(
        "SELECT invoice_id, amount_cents FROM payment_allocations WHERE payment_id = ? ORDER BY id",
        (payment_id,),).fetchall()
    statuses = [conn.execute("SELECT status FROM invoices WHERE id = ?", (item.id,)).fetchone()[0]
                for item in invoices]
    conn.close()
    assert _entry_lines(payment["journal_entry_id"]) == [
        (ar_ap_accounts["cash"], 5000, 0), (ar_ap_accounts["ar"], 0, 5000)]
    assert [(row[0], row[1]) for row in allocations] == [
        (invoices[0].id, 1000), (invoices[1].id, 1000), (invoices[2].id, 3000)]
    assert statuses == ["paid", "partially_paid", "paid"]
    assert [row["open_balance_cents"] for row in reversed(list_invoices(client_id))] == [0, 1000, 0]


def test_credit_apply_and_refund_are_exact(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Credit Customer")
    first = _invoice(client_id, customer.id, ar_ap_accounts, 1000)
    payment_id = record_customer_payment(
        client_id, customer.id, date(2026, 8, 15), 4000, ar_ap_accounts["cash"],
        [{"invoice_id": first.id, "amount_cents": 1000}],
    )
    assert list_customer_credits(client_id)[0]["open_credit_cents"] == 3000
    second = _invoice(client_id, customer.id, ar_ap_accounts, 2000)
    entries_before = _scalar("SELECT COUNT(*) FROM journal_entries")
    apply_customer_credit(payment_id, second.id, 2000)
    assert _scalar("SELECT COUNT(*) FROM journal_entries") == entries_before
    assert _scalar("SELECT status FROM invoices WHERE id = ?", (second.id,)) == "paid"
    refund_id = refund_customer_credit(payment_id, 500, ar_ap_accounts["cash"], date(2026, 8, 20))
    assert list_customer_credits(client_id)[0]["open_credit_cents"] == 500
    refund_entry = _scalar("SELECT journal_entry_id FROM payment_refunds WHERE id = ?", (refund_id,))
    assert _entry_lines(refund_entry) == [
        (ar_ap_accounts["ar"], 500, 0), (ar_ap_accounts["cash"], 0, 500)]


def test_fully_unallocated_payment_is_open_credit(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Unallocated Customer")
    invoice = _invoice(client_id, customer.id, ar_ap_accounts, 1000)
    payment_id = record_customer_payment(client_id, customer.id, date.today(), 750,
                                         ar_ap_accounts["cash"], [])
    assert list_customer_credits(client_id)[0]["open_credit_cents"] == 750
    apply_customer_credit(payment_id, invoice.id, 750)
    assert _scalar("SELECT status FROM invoices WHERE id = ?", (invoice.id,)) == "partially_paid"


def test_payment_validation_rolls_everything_back(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Guard Customer")
    other_customer = create_customer(client_id, "Other Customer")
    invoice = _invoice(client_id, customer.id, ar_ap_accounts, 1000)
    draft = _invoice(client_id, customer.id, ar_ap_accounts, 1000, post=False)
    other_party = _invoice(client_id, other_customer.id, ar_ap_accounts, 1000)
    mixed = _invoice(client_id, customer.id, ar_ap_accounts, 1000, control=ar_ap_accounts["ar2"])
    other_client = Client(name="Other Co", entity_type="S-Corp",
                          fiscal_year_end_month=12).save(seed_accounts=False)
    other_client_customer = create_customer(other_client, "Other Client Customer")
    other_client_revenue = Account(client_id=other_client, account_number="4999",
                                   name="Other Client Revenue", type="Revenue")
    other_client_ar = Account(client_id=other_client, account_number="1199",
                              name="Other Client Receivable", type="Asset")
    other_client_revenue.save(); other_client_ar.save()
    cross_client = create_invoice(other_client, other_client_customer.id,
        [{"description": "Other", "quantity": 1, "unit_price_cents": 1000,
          "revenue_account_id": other_client_revenue.id}])
    post_invoice(cross_client.id, other_client_ar.id)
    cases = [
        (2000, [{"invoice_id": invoice.id, "amount_cents": 2001}], "Allocated amounts"),
        (2000, [{"invoice_id": invoice.id, "amount_cents": 1001}], "open balance"),
        (1000, [{"invoice_id": other_party.id, "amount_cents": 1000}], "payment's party"),
        (1000, [{"invoice_id": cross_client.id, "amount_cents": 1000}], "belong to this client"),
        (1000, [{"invoice_id": draft.id, "amount_cents": 1000}], "must be posted"),
        (2000, [{"invoice_id": invoice.id, "amount_cents": 1000},
                {"invoice_id": mixed.id, "amount_cents": 1000}], "same control account"),
    ]
    for amount, allocations, message in cases:
        with pytest.raises(ValueError, match=message):
            record_customer_payment(client_id, customer.id, date.today(), amount,
                                    ar_ap_accounts["cash"], allocations)
    assert _scalar("SELECT COUNT(*) FROM payments") == 0
    assert _scalar("SELECT COUNT(*) FROM payment_allocations") == 0


def test_payment_fault_rolls_back_allocations_journal_and_audit(client_id, ar_ap_accounts,
                                                                monkeypatch):
    customer = create_customer(client_id, "Fault Customer")
    invoice = _invoice(client_id, customer.id, ar_ap_accounts, 1000)
    before = _scalar("SELECT COUNT(*) FROM audit_log")
    monkeypatch.setattr(ar_ap, "_after_allocation_insert",
                        lambda: (_ for _ in ()).throw(RuntimeError("fault")))
    with pytest.raises(RuntimeError, match="fault"):
        record_customer_payment(client_id, customer.id, date.today(), 1000,
                                ar_ap_accounts["cash"], [{"invoice_id": invoice.id,
                                                         "amount_cents": 1000}])
    assert _scalar("SELECT COUNT(*) FROM payments") == 0
    assert _scalar("SELECT COUNT(*) FROM payment_allocations") == 0
    assert _scalar("SELECT COUNT(*) FROM audit_log") == before


def test_two_connection_payment_race_rechecks_balance(client_id, ar_ap_accounts, monkeypatch):
    customer = create_customer(client_id, "Race Customer")
    invoice = _invoice(client_id, customer.id, ar_ap_accounts, 1000)
    original_save = JournalEntry.save
    first_inside = threading.Event()
    release_first = threading.Event()
    results = []

    def delayed_save(self, conn=None):
        if not first_inside.is_set():
            first_inside.set()
            release_first.wait(2)
        return original_save(self, conn=conn)

    monkeypatch.setattr(JournalEntry, "save", delayed_save)

    def pay():
        try:
            results.append(record_customer_payment(
                client_id, customer.id, date.today(), 1000, ar_ap_accounts["cash"],
                [{"invoice_id": invoice.id, "amount_cents": 1000}]))
        except Exception as exc:
            results.append(exc)

    first = threading.Thread(target=pay)
    second = threading.Thread(target=pay)
    first.start()
    assert first_inside.wait(2)
    second.start()
    time.sleep(0.1)
    assert second.is_alive()
    release_first.set()
    first.join(3); second.join(3)
    assert len([result for result in results if isinstance(result, int)]) == 1
    error = next(result for result in results if isinstance(result, Exception))
    assert "open balance" in str(error)
    assert _scalar("SELECT COUNT(*) FROM payments") == 1


def test_void_payment_and_invoice_restore_and_reverse(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Void Customer")
    invoice = _invoice(client_id, customer.id, ar_ap_accounts, 1000)
    payment_id = record_customer_payment(
        client_id, customer.id, date(2026, 8, 15), 1000, ar_ap_accounts["cash"],
        [{"invoice_id": invoice.id, "amount_cents": 1000}],
    )
    with pytest.raises(ValueError, match="Void the payment first"):
        void_invoice(invoice.id, date(2026, 8, 20))
    void_payment(payment_id, date(2026, 8, 20))
    restored = next(row for row in list_invoices(client_id) if row["id"] == invoice.id)
    assert restored["status"] == "posted" and restored["open_balance_cents"] == 1000
    original = _scalar("SELECT journal_entry_id FROM invoices WHERE id = ?", (invoice.id,))
    reversal = void_invoice(invoice.id, date(2026, 8, 20))
    assert _entry_lines(reversal) == [(account, credit, debit)
                                      for account, debit, credit in _entry_lines(original)]
    assert _scalar("SELECT status FROM invoices WHERE id = ?", (invoice.id,)) == "voided"


def test_ar_aging_ties_to_control_account_with_partial_credit_and_void(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Aging Customer")
    partial = _invoice(client_id, customer.id, ar_ap_accounts, 10000, date(2026, 7, 1))
    credit_doc = _invoice(client_id, customer.id, ar_ap_accounts, 1000, date(2026, 8, 15))
    voided = _invoice(client_id, customer.id, ar_ap_accounts, 2000, date(2026, 5, 1))
    record_customer_payment(client_id, customer.id, date(2026, 8, 20), 7000,
                            ar_ap_accounts["cash"],
                            [{"invoice_id": partial.id, "amount_cents": 4000},
                             {"invoice_id": credit_doc.id, "amount_cents": 1000}])
    void_invoice(voided.id, date(2026, 8, 20))
    aging = get_ar_aging(client_id, date(2026, 8, 31))
    gl = _scalar(
        "SELECT COALESCE(SUM(jel.debit - jel.credit), 0) FROM journal_entry_lines jel "
        "JOIN journal_entries je ON je.id = jel.journal_entry_id "
        "WHERE je.client_id = ? AND jel.account_id = ? AND je.entry_date <= ?",
        (client_id, ar_ap_accounts["ar"], "2026-08-31"),
    )
    assert sum(row["amount_cents"] for row in aging) == gl == 4000
    assert {row["kind"] for row in aging} == {"invoice", "credit"}


def test_bill_flow_uses_v2_tables(client_id, ar_ap_accounts):
    vendor = create_vendor(client_id, "Office Market")
    bill = create_bill(client_id, vendor.id, [{"description": "Paper", "quantity": 1,
        "unit_price_cents": 2500, "expense_account_id": ar_ap_accounts["expense"]}])
    post_bill(bill.id, ar_ap_accounts["ap"])
    payment_id = record_vendor_payment(client_id, vendor.id, date.today(), 2500,
                                       ar_ap_accounts["cash"],
                                       [{"bill_id": bill.id, "amount_cents": 2500}])
    assert _scalar("SELECT COUNT(*) FROM bill_payments_v2 WHERE id = ?", (payment_id,)) == 1
    assert _scalar("SELECT COUNT(*) FROM bill_payments") == 0
    assert _scalar("SELECT status FROM bills WHERE id = ?", (bill.id,)) == "paid"
