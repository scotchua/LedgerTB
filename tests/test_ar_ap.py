from datetime import date
from pathlib import Path
import threading
import time

import pytest
import pypdfium2 as pdfium

from database.connection import get_connection
from models.account import Account
from models.client import Client
from models.journal_entry import JournalEntry
import services.ar_ap as ar_ap
from services.ar_ap import (apply_credit_memo, apply_customer_credit, create_bill,
                            build_invoice_pdf, create_credit_memo, create_customer,
                            create_invoice, create_vendor, get_1099_summary,
                            get_ar_aging, get_income_by_customer,
                            get_sales_tax_report,
                            list_customer_credits, list_invoices, post_bill,
                            post_credit_memo, post_invoice, record_customer_payment,
                            record_sales_tax_remittance,
                            record_vendor_payment, refund_customer_credit,
                            send_invoice_email,
                            void_credit_memo, void_invoice, void_payment)
from services.inventory import create_item, inventory_position, record_movement


@pytest.fixture
def ar_ap_accounts(client_id, accounts):
    ar = Account(client_id=client_id, account_number="1100", name="Accounts Receivable", type="Asset")
    ar2 = Account(client_id=client_id, account_number="1110", name="Other Receivable", type="Asset")
    ap = Account(client_id=client_id, account_number="2100", name="Accounts Payable", type="Liability")
    revenue_2 = Account(client_id=client_id, account_number="4100", name="Project Revenue", type="Revenue")
    expense_2 = Account(client_id=client_id, account_number="6100", name="Supplies Expense", type="Expense")
    tax = Account(client_id=client_id, account_number="2200", name="Sales Tax Payable", type="Liability")
    for account in (ar, ar2, ap, revenue_2, expense_2, tax):
        account.save()
    return {**accounts, "ar": ar.id, "ar2": ar2.id, "ap": ap.id,
            "revenue_2": revenue_2.id, "expense_2": expense_2.id, "tax": tax.id}


def _invoice(client_id, customer_id, accounts, amount=10000, due=date(2026, 8, 31), post=True,
             control=None, invoice_date=date(2026, 8, 1)):
    invoice = create_invoice(client_id, customer_id, [{"description": "Work", "quantity": 1,
        "unit_price_cents": amount, "revenue_account_id": accounts["revenue"]}],
        invoice_date, due)
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


def _pdf_text(buffer):
    document = pdfium.PdfDocument(buffer.read())
    try:
        return "\n".join(
            document[index].get_textpage().get_text_range()
            for index in range(len(document))
        )
    finally:
        document.close()


def test_ar_ap_reports_hand_computed_void_credit_and_on_account_cases(
    client_id, ar_ap_accounts,
):
    customer = create_customer(client_id, "Report Customer")
    vendor = create_vendor(client_id, "Report Vendor")
    taxed = create_invoice(client_id, customer.id, [{"description": "Taxed", "quantity": 1,
        "unit_price_cents": 10000, "revenue_account_id": ar_ap_accounts["revenue"]}],
        date(2026, 1, 10), date(2026, 2, 10), "0.10")
    post_invoice(taxed.id, ar_ap_accounts["ar"], ar_ap_accounts["tax"])
    untaxed = _invoice(client_id, customer.id, ar_ap_accounts, 5000)
    voided = _invoice(client_id, customer.id, ar_ap_accounts, 9000)
    void_invoice(voided.id, date(2026, 8, 20))
    payment = record_customer_payment(client_id, customer.id, date(2026, 1, 15),
        7000, ar_ap_accounts["cash"], [{"invoice_id": taxed.id, "amount_cents": 4000}])
    apply_customer_credit(payment, untaxed.id, 1000)
    credit = create_credit_memo(client_id, customer.id, [{"description": "Allowance", "quantity": 1,
        "unit_price_cents": 2000, "revenue_account_id": ar_ap_accounts["revenue"]}],
        date(2026, 1, 18), "0.10", taxed.id)
    post_credit_memo(credit.id, ar_ap_accounts["ar"], ar_ap_accounts["tax"])
    apply_credit_memo(credit.id, taxed.id, 2200)

    bill = create_bill(client_id, vendor.id, [{"description": "Fees", "quantity": 1,
        "unit_price_cents": 80000, "expense_account_id": ar_ap_accounts["expense"]}],
        date(2026, 1, 5), date(2026, 2, 5))
    post_bill(bill.id, ar_ap_accounts["ap"])
    record_vendor_payment(client_id, vendor.id, date(2026, 2, 1), 65000,
        ar_ap_accounts["cash"], [{"bill_id": bill.id, "amount_cents": 65000}])
    void_bill = create_bill(client_id, vendor.id, [{"description": "Void", "quantity": 1,
        "unit_price_cents": 10000, "expense_account_id": ar_ap_accounts["expense"]}],
        date(2026, 1, 6), date(2026, 2, 6))
    post_bill(void_bill.id, ar_ap_accounts["ap"])
    void_vendor = record_vendor_payment(client_id, vendor.id, date(2026, 2, 2), 10000,
        ar_ap_accounts["cash"], [{"bill_id": void_bill.id, "amount_cents": 10000}])
    ar_ap.void_vendor_payment(void_vendor, date(2026, 2, 3))

    tax = get_sales_tax_report(client_id, date(2026, 1, 1), date(2026, 12, 31))
    assert (tax["total_sales_cents"], tax["total_taxable_cents"],
            tax["total_non_taxable_cents"], tax["total_tax_cents"]) == (
                13000, 8000, 5000, 800,
            )
    summary = get_1099_summary(client_id, 2026)["vendors"]
    assert summary == [{"vendor_id": vendor.id, "vendor_name": "Report Vendor",
                        "total_paid_cents": 65000, "review_threshold": True}]
    income = get_income_by_customer(client_id, date(2026, 1, 1), date(2026, 12, 31))
    assert income == [{"customer_id": customer.id, "customer_name": "Report Customer",
                       "invoice_count": 2, "subtotal_cents": 15000,
                       "total_cents": 16000, "total_paid_cents": 7200,
                       "open_balance_cents": 8800, "open_credit_cents": 2000}]
    assert (sum(row["open_balance_cents"] for row in income)
            - sum(row["open_credit_cents"] for row in income)) == sum(
        row["amount_cents"] for row in get_ar_aging(client_id, date(2026, 12, 31))
    )


@pytest.mark.parametrize("tax_rate,partial,voided", [
    (None, False, False), ("0.10", False, False), (None, True, False),
    (None, False, True),
])
def test_invoice_pdf_tax_payment_and_void_variants(
    client_id, ar_ap_accounts, tax_rate, partial, voided,
):
    customer = create_customer(client_id, f"PDF Customer {tax_rate} {partial} {voided}")
    invoice = create_invoice(client_id, customer.id, [{"description": "Advisory work",
        "quantity": 2, "unit_price_cents": 5000,
        "revenue_account_id": ar_ap_accounts["revenue"]}], date(2026, 3, 1),
        date(2026, 3, 31), tax_rate)
    post_invoice(invoice.id, ar_ap_accounts["ar"], ar_ap_accounts["tax"] if tax_rate else None)
    if partial:
        record_customer_payment(client_id, customer.id, date(2026, 3, 5), 2500,
            ar_ap_accounts["cash"], [{"invoice_id": invoice.id, "amount_cents": 2500}])
    if voided:
        void_invoice(invoice.id, date(2026, 3, 10))
    pdf = build_invoice_pdf(invoice.id)
    assert pdf.getvalue().startswith(b"%PDF")
    text = _pdf_text(pdf)
    assert "INVOICE" in text and "Advisory work" in text and "Balance due" in text
    assert ("VOID" in text) is voided
    assert ("Tax (0.10)" in text) is bool(tax_rate)
    if partial:
        assert "$25.00" in text


def test_invoice_email_success_and_redacted_failure(
    client_id, ar_ap_accounts, fake_credential_vault, monkeypatch,
):
    customer = create_customer(client_id, "Email Customer", "customer@example.com")
    invoice = _invoice(client_id, customer.id, ar_ap_accounts)
    fake_credential_vault.update({"smtp.host": "smtp.example.com", "smtp.port": "587",
        "smtp.username": "mailer", "smtp.password": "top-secret-password",
        "smtp.from_address": "billing@example.com"})
    sent = []

    class FakeSMTP:
        def __init__(self, host, port):
            assert (host, port) == ("smtp.example.com", 587)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self): pass
        def login(self, username, password):
            assert (username, password) == ("mailer", "top-secret-password")
        def send_message(self, message): sent.append(message)

    monkeypatch.setattr(ar_ap.smtplib, "SMTP", FakeSMTP)
    send_invoice_email(invoice.id, "customer@example.com", "Your invoice", "Attached.")
    message = sent[0]
    assert message["To"] == "customer@example.com" and message["Subject"] == "Your invoice"
    assert any(part.get_content_type() == "application/pdf" for part in message.iter_attachments())

    class FailingSMTP(FakeSMTP):
        def send_message(self, message):
            raise RuntimeError("server echoed top-secret-password")

    monkeypatch.setattr(ar_ap.smtplib, "SMTP", FailingSMTP)
    with pytest.raises(RuntimeError, match="could not be sent"):
        send_invoice_email(invoice.id, "customer@example.com")
    conn = get_connection()
    logs = conn.execute("SELECT status, error FROM email_log ORDER BY id").fetchall()
    audits = conn.execute("SELECT COUNT(*) FROM audit_log WHERE table_name = 'email_log'").fetchone()[0]
    conn.close()
    assert [row["status"] for row in logs] == ["sent", "failed"]
    assert "top-secret-password" not in (logs[-1]["error"] or "")
    assert audits == 2


def test_smtp_credentials_are_vault_only():
    schema = (Path(__file__).parent.parent / "database" / "migrations" /
              "040_email_log.sql").read_text()
    assert "password" not in schema.lower()


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


def test_ar_ap_chronology_rejects_impossible_dates_without_partial_writes(
    client_id, ar_ap_accounts,
):
    customer = create_customer(client_id, "Chronology Customer")
    vendor = create_vendor(client_id, "Chronology Vendor")
    invoice_line = [{"description": "Work", "quantity": 1,
                     "unit_price_cents": 1000,
                     "revenue_account_id": ar_ap_accounts["revenue"]}]
    bill_line = [{"description": "Supplies", "quantity": 1,
                  "unit_price_cents": 1000,
                  "expense_account_id": ar_ap_accounts["expense"]}]

    with pytest.raises(ValueError, match="Due date cannot precede"):
        create_invoice(client_id, customer.id, invoice_line,
                       date(2026, 8, 10), date(2026, 8, 9))
    with pytest.raises(ValueError, match="Due date cannot precede"):
        create_bill(client_id, vendor.id, bill_line,
                    date(2026, 8, 10), date(2026, 8, 9))
    assert _scalar("SELECT COUNT(*) FROM invoices") == 0
    assert _scalar("SELECT COUNT(*) FROM bills") == 0

    invoice = create_invoice(client_id, customer.id, invoice_line,
                             date(2026, 8, 10), date(2026, 9, 10))
    invoice = post_invoice(invoice.id, ar_ap_accounts["ar"])
    payment_id = record_customer_payment(
        client_id, customer.id, date(2026, 8, 15), 1000,
        ar_ap_accounts["cash"], [],
    )
    entries_before = _scalar("SELECT COUNT(*) FROM journal_entries")
    audit_before = _scalar("SELECT COUNT(*) FROM audit_log")
    with pytest.raises(ValueError, match="Refund date cannot precede"):
        refund_customer_credit(payment_id, 100, ar_ap_accounts["cash"],
                               date(2026, 8, 14))
    with pytest.raises(ValueError, match="Void date cannot precede"):
        void_payment(payment_id, date(2026, 8, 14))
    with pytest.raises(ValueError, match="Void date cannot precede"):
        void_invoice(invoice.id, date(2026, 8, 9))
    assert _scalar("SELECT COUNT(*) FROM journal_entries") == entries_before
    assert _scalar("SELECT COUNT(*) FROM payment_refunds") == 0
    assert _scalar("SELECT COUNT(*) FROM audit_log") == audit_before
    assert _scalar("SELECT status FROM payments WHERE id = ?", (payment_id,)) == "recorded"
    assert _scalar("SELECT status FROM invoices WHERE id = ?", (invoice.id,)) == "posted"

    with pytest.raises(ValueError, match="Credit memo date cannot precede"):
        create_credit_memo(
            client_id, customer.id, invoice_line, date(2026, 8, 9),
            original_invoice_id=invoice.id,
        )
    assert _scalar("SELECT COUNT(*) FROM credit_memos") == 0


def test_historical_aging_uses_allocation_effective_date(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Effective Date Customer")
    invoice = create_invoice(
        client_id, customer.id,
        [{"description": "January work", "quantity": 1,
          "unit_price_cents": 1000,
          "revenue_account_id": ar_ap_accounts["revenue"]}],
        date(2026, 1, 15), date(2026, 2, 15),
    )
    invoice = post_invoice(invoice.id, ar_ap_accounts["ar"])
    payment_id = record_customer_payment(
        client_id, customer.id, date(2026, 1, 10), 1000,
        ar_ap_accounts["cash"], [],
    )
    with pytest.raises(ValueError, match="cannot precede the payment or document"):
        apply_customer_credit(payment_id, invoice.id, 1000, date(2026, 1, 14))
    application_id = apply_customer_credit(
        payment_id, invoice.id, 1000, date(2026, 1, 20)
    )
    assert _scalar(
        "SELECT application_date FROM payment_allocations WHERE id = ?",
        (application_id,),
    ) == "2026-01-20"

    before_application = get_ar_aging(client_id, date(2026, 1, 16))
    assert {(row["kind"], row["amount_cents"]) for row in before_application} == {
        ("invoice", 1000), ("credit", -1000),
    }
    assert get_ar_aging(client_id, date(2026, 1, 21)) == []

    future_customer = create_customer(client_id, "Initial Allocation Customer")
    future_invoice = create_invoice(
        client_id, future_customer.id,
        [{"description": "Future invoice", "quantity": 1,
          "unit_price_cents": 500,
          "revenue_account_id": ar_ap_accounts["revenue"]}],
        date(2026, 3, 15), date(2026, 4, 15),
    )
    future_invoice = post_invoice(future_invoice.id, ar_ap_accounts["ar"])
    future_payment = record_customer_payment(
        client_id, future_customer.id, date(2026, 3, 10), 500,
        ar_ap_accounts["cash"],
        [{"invoice_id": future_invoice.id, "amount_cents": 500}],
    )
    assert _scalar(
        "SELECT application_date FROM payment_allocations WHERE payment_id = ?",
        (future_payment,),
    ) == "2026-03-15"
    assert get_ar_aging(client_id, date(2026, 3, 12))[-1]["amount_cents"] == -500
    assert not [row for row in get_ar_aging(client_id, date(2026, 3, 16))
                if row["party_id"] == future_customer.id]


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
    partial = _invoice(client_id, customer.id, ar_ap_accounts, 10000,
                       date(2026, 7, 1), invoice_date=date(2026, 6, 1))
    credit_doc = _invoice(client_id, customer.id, ar_ap_accounts, 1000, date(2026, 8, 15))
    voided = _invoice(client_id, customer.id, ar_ap_accounts, 2000,
                      date(2026, 5, 1), invoice_date=date(2026, 4, 1))
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


def test_taxed_and_untaxed_invoice_entries_and_tax_inclusive_allocations(
    client_id, ar_ap_accounts,
):
    customer = create_customer(client_id, "Tax Customer")
    taxed = create_invoice(client_id, customer.id, [{"description": "Taxed work", "quantity": 1,
        "unit_price_cents": 10000, "revenue_account_id": ar_ap_accounts["revenue"]}],
        tax_rate="0.0650")
    posted = post_invoice(taxed.id, ar_ap_accounts["ar"], ar_ap_accounts["tax"])
    assert _entry_lines(posted.journal_entry_id) == [
        (ar_ap_accounts["ar"], 10650, 0),
        (ar_ap_accounts["revenue"], 0, 10000),
        (ar_ap_accounts["tax"], 0, 650),
    ]
    assert _scalar("SELECT tax_rate FROM invoices WHERE id = ?", (taxed.id,)) == "0.0650"
    record_customer_payment(client_id, customer.id, date.today(), 10000,
                            ar_ap_accounts["cash"],
                            [{"invoice_id": taxed.id, "amount_cents": 10000}])
    assert _scalar("SELECT status FROM invoices WHERE id = ?", (taxed.id,)) == "partially_paid"
    assert next(row for row in list_invoices(client_id) if row["id"] == taxed.id)[
        "open_balance_cents"] == 650

    paid = create_invoice(client_id, customer.id, [{"description": "Paid taxed work", "quantity": 1,
        "unit_price_cents": 10000, "revenue_account_id": ar_ap_accounts["revenue"]}],
        tax_rate="0.0650")
    post_invoice(paid.id, ar_ap_accounts["ar"], ar_ap_accounts["tax"])
    record_customer_payment(client_id, customer.id, date.today(), 10650,
                            ar_ap_accounts["cash"],
                            [{"invoice_id": paid.id, "amount_cents": 10650}])
    assert _scalar("SELECT status FROM invoices WHERE id = ?", (paid.id,)) == "paid"

    untaxed = create_invoice(client_id, customer.id, [{"description": "Untaxed", "quantity": 1,
        "unit_price_cents": 10000, "revenue_account_id": ar_ap_accounts["revenue"]}])
    untaxed = post_invoice(untaxed.id, ar_ap_accounts["ar"])
    assert _entry_lines(untaxed.journal_entry_id) == [
        (ar_ap_accounts["ar"], 10000, 0),
        (ar_ap_accounts["revenue"], 0, 10000),
    ]


def test_taxed_bill_and_sales_tax_remittance_entries_and_audit(client_id, ar_ap_accounts):
    vendor = create_vendor(client_id, "Taxed Vendor")
    bill = create_bill(client_id, vendor.id, [{"description": "Supplies", "quantity": 1,
        "unit_price_cents": 10000, "expense_account_id": ar_ap_accounts["expense"]}],
        tax_rate="0.0650")
    posted = post_bill(bill.id, ar_ap_accounts["ap"], ar_ap_accounts["tax"])
    assert _entry_lines(posted.journal_entry_id) == [
        (ar_ap_accounts["expense"], 10000, 0),
        (ar_ap_accounts["tax"], 650, 0),
        (ar_ap_accounts["ap"], 0, 10650),
    ]
    before = _scalar("SELECT COALESCE(MAX(id), 0) FROM audit_log")
    entry_id = record_sales_tax_remittance(client_id, ar_ap_accounts["tax"],
                                           ar_ap_accounts["cash"], 650, date.today(), "Q3")
    assert _entry_lines(entry_id) == [
        (ar_ap_accounts["tax"], 650, 0), (ar_ap_accounts["cash"], 0, 650),
    ]
    assert _audit_actions(before) == [
        ("journal_entries", "INSERT"), ("sales_tax_remittances", "INSERT"),
    ]


def test_credit_memo_posts_applies_without_entry_and_void_guards(client_id, ar_ap_accounts):
    customer = create_customer(client_id, "Memo Customer")
    invoices = [_invoice(client_id, customer.id, ar_ap_accounts, amount)
                for amount in (6000, 4650)]
    memo = create_credit_memo(client_id, customer.id, [{"description": "Allowance", "quantity": 1,
        "unit_price_cents": 10000, "revenue_account_id": ar_ap_accounts["revenue"]}],
        tax_rate="0.0650", original_invoice_id=invoices[0].id)
    posted = post_credit_memo(memo.id, ar_ap_accounts["ar"], ar_ap_accounts["tax"])
    assert _entry_lines(posted.journal_entry_id) == [
        (ar_ap_accounts["revenue"], 10000, 0),
        (ar_ap_accounts["tax"], 650, 0),
        (ar_ap_accounts["ar"], 0, 10650),
    ]
    entries = _scalar("SELECT COUNT(*) FROM journal_entries")
    apply_credit_memo(memo.id, invoices[0].id, 6000)
    apply_credit_memo(memo.id, invoices[1].id, 4650)
    assert _scalar("SELECT COUNT(*) FROM journal_entries") == entries
    assert [_scalar("SELECT status FROM invoices WHERE id = ?", (invoice.id,))
            for invoice in invoices] == ["paid", "paid"]
    assert _scalar("SELECT status FROM credit_memos WHERE id = ?", (memo.id,)) == "applied"
    with pytest.raises(ValueError, match="void blocked"):
        void_credit_memo(memo.id)
    with pytest.raises(ValueError, match="void blocked"):
        void_invoice(invoices[0].id)

    clean = create_credit_memo(client_id, customer.id, [{"description": "Clean", "quantity": 1,
        "unit_price_cents": 1000, "revenue_account_id": ar_ap_accounts["revenue"]}])
    clean = post_credit_memo(clean.id, ar_ap_accounts["ar"])
    reversal = void_credit_memo(clean.id)
    assert _entry_lines(reversal) == [(account, credit, debit)
                                      for account, debit, credit in _entry_lines(clean.journal_entry_id)]


def test_taxed_invoice_void_reverses_tax_line_and_credit_memo_aging_ties_out(
    client_id, ar_ap_accounts,
):
    customer = create_customer(client_id, "Tax Void Customer")
    taxed = create_invoice(client_id, customer.id, [{"description": "Taxed", "quantity": 1,
        "unit_price_cents": 10000, "revenue_account_id": ar_ap_accounts["revenue"]}],
        date(2026, 8, 1), date(2026, 8, 31), tax_rate="0.0650")
    taxed = post_invoice(taxed.id, ar_ap_accounts["ar"], ar_ap_accounts["tax"])
    reversal = void_invoice(taxed.id, date(2026, 8, 20))
    assert _entry_lines(reversal) == [(account, credit, debit)
                                      for account, debit, credit in _entry_lines(taxed.journal_entry_id)]

    invoice = _invoice(client_id, customer.id, ar_ap_accounts, 10000, date(2026, 8, 31))
    memo = create_credit_memo(client_id, customer.id, [{"description": "Unapplied", "quantity": 1,
        "unit_price_cents": 2500, "revenue_account_id": ar_ap_accounts["revenue"]}],
        memo_date=date(2026, 8, 15))
    post_credit_memo(memo.id, ar_ap_accounts["ar"])
    aging = get_ar_aging(client_id, date(2026, 8, 31))
    gl = _scalar(
        "SELECT COALESCE(SUM(jel.debit - jel.credit), 0) FROM journal_entry_lines jel "
        "JOIN journal_entries je ON je.id = jel.journal_entry_id "
        "WHERE je.client_id = ? AND jel.account_id = ? AND je.entry_date <= ?",
        (client_id, ar_ap_accounts["ar"], "2026-08-31"),
    )
    assert sum(row["amount_cents"] for row in aging) == gl == 7500
    assert {row["kind"] for row in aging} == {"invoice", "credit_memo"}
