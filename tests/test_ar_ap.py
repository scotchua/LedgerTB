from datetime import date

import pytest

from database.connection import get_connection
from models.account import Account
from services.ar_ap import (create_bill, create_customer, create_invoice,
                            create_vendor, post_bill, post_invoice,
                            record_bill_payment, record_invoice_payment)


@pytest.fixture
def ar_ap_accounts(client_id, accounts):
    ar = Account(client_id=client_id, account_number="1100", name="Accounts Receivable", type="Asset")
    ap = Account(client_id=client_id, account_number="2100", name="Accounts Payable", type="Liability")
    second_revenue = Account(client_id=client_id, account_number="4100", name="Project Revenue", type="Revenue")
    second_expense = Account(client_id=client_id, account_number="6100", name="Supplies Expense", type="Expense")
    ar.save(); ap.save(); second_revenue.save(); second_expense.save()
    return {**accounts, "ar": ar.id, "ap": ap.id,
            "revenue_2": second_revenue.id, "expense_2": second_expense.id}


def _entry_lines(entry_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT account_id, debit, credit FROM journal_entry_lines WHERE journal_entry_id = ? ORDER BY id",
        (entry_id,),
    ).fetchall()
    conn.close()
    return [(row["account_id"], row["debit"], row["credit"]) for row in rows]


def _audit_rows(table, record_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT action, performed_by FROM audit_log WHERE table_name = ? AND record_id = ? ORDER BY id",
        (table, record_id),
    ).fetchall()
    conn.close()
    return [(row["action"], row["performed_by"]) for row in rows]


def test_invoice_posts_exact_balanced_entry_and_audits(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Northwind Labs")
    invoice = create_invoice(client_id, customer.id, [
        {"description": "Consulting", "quantity": 2, "unit_price_cents": 12550,
         "revenue_account_id": ar_ap_accounts["revenue"]},
        {"description": "Setup", "quantity": 1, "unit_price_cents": 4995,
         "revenue_account_id": ar_ap_accounts["revenue_2"]},
    ], date(2026, 8, 1), date(2026, 8, 31))
    posted = post_invoice(invoice.id, ar_ap_accounts["ar"])
    assert _entry_lines(posted.journal_entry_id) == [
        (ar_ap_accounts["ar"], 30095, 0),
        (ar_ap_accounts["revenue"], 0, 25100),
        (ar_ap_accounts["revenue_2"], 0, 4995),
    ]
    assert [row[0] for row in _audit_rows("invoices", invoice.id)] == ["INSERT", "UPDATE"]
    assert all(row[1] for row in _audit_rows("invoices", invoice.id))


def test_invoice_full_and_partial_payments_update_status(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Acme Services")
    full = create_invoice(client_id, customer.id, [{"description": "Work", "quantity": 1,
        "unit_price_cents": 10000, "revenue_account_id": ar_ap_accounts["revenue"]}])
    post_invoice(full.id, ar_ap_accounts["ar"])
    assert record_invoice_payment(full.id, 10000, ar_ap_accounts["cash"],
                                  date(2026, 8, 10), ar_ap_accounts["ar"]).status == "paid"

    partial = create_invoice(client_id, customer.id, [{"description": "Work", "quantity": 1,
        "unit_price_cents": 10000, "revenue_account_id": ar_ap_accounts["revenue"]}])
    post_invoice(partial.id, ar_ap_accounts["ar"])
    assert record_invoice_payment(partial.id, 4000, ar_ap_accounts["cash"],
                                  date(2026, 8, 10), ar_ap_accounts["ar"]).status == "partially_paid"
    assert record_invoice_payment(partial.id, 6000, ar_ap_accounts["cash"],
                                  date(2026, 8, 11), ar_ap_accounts["ar"]).status == "paid"


def test_bill_posts_exact_balanced_entry_and_payment_states(client_id, ar_ap_accounts):
    vendor = create_vendor(client_id, "Office Market")
    bill = create_bill(client_id, vendor.id, [
        {"description": "Paper", "quantity": 3, "unit_price_cents": 1234,
         "expense_account_id": ar_ap_accounts["expense"]},
        {"description": "Ink", "quantity": 2, "unit_price_cents": 2499,
         "expense_account_id": ar_ap_accounts["expense_2"]},
    ], date(2026, 8, 2), date(2026, 9, 1))
    posted = post_bill(bill.id, ar_ap_accounts["ap"])
    assert _entry_lines(posted.journal_entry_id) == [
        (ar_ap_accounts["expense"], 3702, 0),
        (ar_ap_accounts["expense_2"], 4998, 0),
        (ar_ap_accounts["ap"], 0, 8700),
    ]
    assert record_bill_payment(bill.id, 3000, ar_ap_accounts["cash"],
                               date(2026, 8, 12), ar_ap_accounts["ap"]).status == "partially_paid"
    assert record_bill_payment(bill.id, 5700, ar_ap_accounts["cash"],
                               date(2026, 8, 13), ar_ap_accounts["ap"]).status == "paid"
    full = create_bill(client_id, vendor.id, [{"description": "Fee", "quantity": 1,
        "unit_price_cents": 2500, "expense_account_id": ar_ap_accounts["expense"]}])
    post_bill(full.id, ar_ap_accounts["ap"])
    assert record_bill_payment(full.id, 2500, ar_ap_accounts["cash"],
                               date(2026, 8, 14), ar_ap_accounts["ap"]).status == "paid"


def test_repost_and_draft_payment_are_refused(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Example Customer")
    invoice = create_invoice(client_id, customer.id, [{"description": "Work", "quantity": 1,
        "unit_price_cents": 5000, "revenue_account_id": ar_ap_accounts["revenue"]}])
    with pytest.raises(ValueError, match="before recording"):
        record_invoice_payment(invoice.id, 5000, ar_ap_accounts["cash"], date.today(), ar_ap_accounts["ar"])
    post_invoice(invoice.id, ar_ap_accounts["ar"])
    with pytest.raises(ValueError, match="already been posted"):
        post_invoice(invoice.id, ar_ap_accounts["ar"])

    vendor = create_vendor(client_id, "Example Vendor")
    bill = create_bill(client_id, vendor.id, [{"description": "Fee", "quantity": 1,
        "unit_price_cents": 5000, "expense_account_id": ar_ap_accounts["expense"]}])
    with pytest.raises(ValueError, match="before recording"):
        record_bill_payment(bill.id, 5000, ar_ap_accounts["cash"], date.today(), ar_ap_accounts["ap"])
    post_bill(bill.id, ar_ap_accounts["ap"])
    with pytest.raises(ValueError, match="already been posted"):
        post_bill(bill.id, ar_ap_accounts["ap"])


def test_vendor_normalization_and_existing_foreign_key_remains_valid(client_id, ar_ap_accounts):
    vendor = create_vendor(client_id, "  BLUE   Sky  Supply ")
    assert vendor.normalized_name == "blue sky supply"
    conn = get_connection()
    stored = conn.execute("SELECT normalized_name FROM vendors WHERE id = ?", (vendor.id,)).fetchone()
    assert stored["normalized_name"] == "blue sky supply"
    conn.execute(
        "INSERT INTO categorization_rules (client_id, vendor_id, pattern, default_account_id) VALUES (?, ?, ?, ?)",
        (client_id, vendor.id, "BLUE SKY", ar_ap_accounts["expense"]),
    )
    foreign_tables = {row["table"] for row in conn.execute("PRAGMA foreign_key_list(categorization_rules)")}
    assert "vendors" in foreign_tables
    conn.rollback()
    conn.close()


def test_payment_mutations_are_audited(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Audit Customer")
    invoice = create_invoice(client_id, customer.id, [{"description": "Work", "quantity": 1,
        "unit_price_cents": 1000, "revenue_account_id": ar_ap_accounts["revenue"]}])
    post_invoice(invoice.id, ar_ap_accounts["ar"])
    record_invoice_payment(invoice.id, 1000, ar_ap_accounts["cash"], date.today(), ar_ap_accounts["ar"])
    conn = get_connection()
    payment_id = conn.execute("SELECT id FROM invoice_payments WHERE invoice_id = ?", (invoice.id,)).fetchone()["id"]
    conn.close()
    assert _audit_rows("invoice_payments", payment_id)[0][0] == "INSERT"
    assert len(_audit_rows("invoices", invoice.id)) == 3


def test_overpayment_is_refused(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Balance Customer")
    invoice = create_invoice(client_id, customer.id, [{"description": "Work", "quantity": 1,
        "unit_price_cents": 1000, "revenue_account_id": ar_ap_accounts["revenue"]}])
    post_invoice(invoice.id, ar_ap_accounts["ar"])
    with pytest.raises(ValueError, match="remaining balance"):
        record_invoice_payment(invoice.id, 1001, ar_ap_accounts["cash"], date.today(), ar_ap_accounts["ar"])
