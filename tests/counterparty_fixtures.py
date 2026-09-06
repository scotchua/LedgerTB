"""Seeded service-built books and labelled duplicate faults; synthetic data only."""

from dataclasses import dataclass
from datetime import date, timedelta
import random

from database.connection import get_connection
from models.account import Account
from models.client import Client
from models.journal_entry import JournalEntry, JournalEntryLine
from money import to_dollars
from services import ar_ap


@dataclass
class CounterpartyBook:
    client_id: int
    accounts: dict
    source_entries: dict
    manual_entries: list
    coverage: dict


def attribution_coverage(client_id: int) -> dict:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS total, COUNT(l.counterparty_id) AS attributed "
            "FROM journal_entry_lines l JOIN journal_entries j ON j.id = l.journal_entry_id "
            "WHERE j.client_id = ?", (client_id,),
        ).fetchone()
        return {"line_count": row["total"], "attributed_lines": row["attributed"],
                "coverage": row["attributed"] / row["total"] if row["total"] else 0.0}
    finally:
        conn.close()


def seed_counterparty_book(seed: int = 1729, party_count: int = 10,
                           manual_count: int = 10) -> CounterpartyBook:
    """Create five sourced entries per customer/vendor pair and a manual slice.

    Expected line coverage is 10 * party_count / (10 * party_count + 2 * manual_count).
    The default is 100 / 120 = 83.333%; every sourced line must be attributed.
    The caller supplies a temporary active database, as with other service tests.
    """
    if party_count < 1 or manual_count < 0:
        raise ValueError("party_count must be positive and manual_count non-negative.")
    rng = random.Random(seed)
    client_id = Client(name=f"Synthetic counterparties {seed}").save(seed_accounts=False)
    accounts = {}
    for key, number, name, kind in (
        ("cash", "1000", "Cash", "Asset"),
        ("ar", "1100", "Accounts Receivable", "Asset"),
        ("ap", "2100", "Accounts Payable", "Liability"),
        ("revenue", "4000", "Service Revenue", "Revenue"),
        ("expense", "6000", "Office Expense", "Expense"),
    ):
        accounts[key] = Account(client_id=client_id, account_number=number,
                                name=name, type=kind).save()
    source_entries = {}
    for index in range(party_count):
        customer = ar_ap.create_customer(client_id, f"Synthetic customer {index:04d}")
        vendor = ar_ap.create_vendor(client_id, f"Synthetic vendor {index:04d}")
        day = date(2025, 1, 1) + timedelta(days=rng.randrange(300))
        invoice_amount, bill_amount = rng.randrange(10000, 50000), rng.randrange(10000, 50000)
        invoice = ar_ap.create_invoice(client_id, customer.id, [{
            "description": f"Services {index}", "quantity": 1,
            "unit_price_cents": invoice_amount, "revenue_account_id": accounts["revenue"],
        }], day, day + timedelta(days=30))
        invoice = ar_ap.post_invoice(invoice.id, accounts["ar"])
        bill = ar_ap.create_bill(client_id, vendor.id, [{
            "description": f"Supplies {index}", "quantity": 1,
            "unit_price_cents": bill_amount, "expense_account_id": accounts["expense"],
        }], day, day + timedelta(days=30))
        bill = ar_ap.post_bill(bill.id, accounts["ap"])
        customer_payment = ar_ap.record_customer_payment(
            client_id, customer.id, day + timedelta(days=1), invoice_amount // 2 + 200,
            accounts["cash"], [],
        )
        vendor_payment = ar_ap.record_vendor_payment(
            client_id, vendor.id, day + timedelta(days=1), bill_amount // 2 + 200,
            accounts["cash"], [],
        )
        ar_ap.apply_customer_credit(customer_payment, invoice.id, invoice_amount // 2,
                                    day + timedelta(days=2))
        ar_ap.apply_vendor_credit(vendor_payment, bill.id, bill_amount // 2,
                                  day + timedelta(days=2))
        memo = ar_ap.create_credit_memo(client_id, customer.id, [{
            "description": f"Service credit {index}", "quantity": 1,
            "unit_price_cents": 500, "revenue_account_id": accounts["revenue"],
        }], day + timedelta(days=2), original_invoice_id=invoice.id)
        memo = ar_ap.post_credit_memo(memo.id, accounts["ar"])
        ar_ap.apply_credit_memo(memo.id, invoice.id, 500, day + timedelta(days=3))
        source_entries[invoice.journal_entry_id] = ("customer", customer.id)
        source_entries[bill.journal_entry_id] = ("vendor", vendor.id)
        source_entries[memo.journal_entry_id] = ("customer", customer.id)
        conn = get_connection()
        try:
            for table, payment_id, kind, source_id in (
                ("payments", customer_payment, "customer", customer.id),
                ("bill_payments_v2", vendor_payment, "vendor", vendor.id),
            ):
                entry_id = conn.execute(
                    f"SELECT journal_entry_id FROM {table} WHERE id = ?", (payment_id,),
                ).fetchone()[0]
                source_entries[entry_id] = (kind, source_id)
        finally:
            conn.close()
    manual_entries = []
    for index in range(manual_count):
        amount = to_dollars(rng.randrange(100, 10000))
        entry = JournalEntry(
            client_id=client_id, entry_date=date(2025, 1, 1) + timedelta(days=rng.randrange(300)),
            description=f"Manual journal {index}", source_reference=f"MANUAL-{index}",
            lines=[JournalEntryLine(account_id=accounts["expense"], debit=amount),
                   JournalEntryLine(account_id=accounts["cash"], credit=amount)],
        )
        manual_entries.append(entry.save())
    return CounterpartyBook(client_id, accounts, source_entries, manual_entries,
                            attribution_coverage(client_id))


@dataclass(frozen=True)
class LabelledPair:
    first_entry_id: int
    second_entry_id: int
    duplicate: bool
    scenario: str


def seed_duplicate_evaluation(book: CounterpartyBook, seed: int = 2718) -> list:
    """80 independent labelled pairs: 24 positives and 56 hard negatives.

    Each pair has its own vendor to make all unlabelled cross-pair matches false.
    Faults are injected as new journal postings, never by editing posted history.
    """
    rng = random.Random(seed)
    scenarios = (["exact", "tolerance", "date_boundary"] * 8
                 + ["reversal", "recurring", "different_party", "outside_amount",
                    "outside_date", "opposite_sign", "unattributed"] * 8)
    rng.shuffle(scenarios)
    labels = []
    for index, scenario in enumerate(scenarios):
        vendor = ar_ap.create_vendor(book.client_id, f"Evaluation vendor {index:04d}")
        day = date(2026, 1, 1) + timedelta(days=rng.randrange(200))
        amount_cents = rng.randrange(1000, 100000)
        bill = ar_ap.create_bill(book.client_id, vendor.id, [{
            "description": "Monthly service", "quantity": 1, "unit_price_cents": amount_cents,
            "expense_account_id": book.accounts["expense"],
        }], day, day)
        bill = ar_ap.post_bill(bill.id, book.accounts["ap"])
        first = JournalEntry.get_by_id(bill.journal_entry_id, client_id=book.client_id)
        if scenario == "reversal":
            second_id = ar_ap.void_bill(bill.id, day + timedelta(days=1))
        elif scenario in ("recurring", "different_party"):
            second_vendor = vendor
            if scenario == "different_party":
                second_vendor = ar_ap.create_vendor(book.client_id, f"Other vendor {index:04d}")
            second_bill = ar_ap.create_bill(book.client_id, second_vendor.id, [{
                "description": "Monthly service", "quantity": 1, "unit_price_cents": amount_cents,
                "expense_account_id": book.accounts["expense"],
            }], day + timedelta(days=1), day + timedelta(days=1))
            second_id = ar_ap.post_bill(second_bill.id, book.accounts["ap"]).journal_entry_id
        else:
            delta = 1 if scenario == "tolerance" else 2 if scenario == "outside_amount" else 0
            offset = 3 if scenario == "date_boundary" else 4 if scenario == "outside_date" else 1
            lines = []
            for line in first.lines:
                amount = to_dollars(amount_cents + delta)
                debit = bool(line.debit) != (scenario == "opposite_sign")
                lines.append(JournalEntryLine(
                    account_id=line.account_id, debit=amount if debit else 0,
                    credit=0 if debit else amount,
                    counterparty_id=None if scenario == "unattributed" else line.counterparty_id,
                ))
            second_id = JournalEntry(
                client_id=book.client_id, entry_date=day + timedelta(days=offset),
                description="Synthetic repeated posting", source_reference=first.source_reference,
                lines=lines,
            ).save()
        labels.append(LabelledPair(first.id, second_id,
                                  scenario in ("exact", "tolerance", "date_boundary"), scenario))
    return labels


def duplicate_metrics(labels: list, proposals: list) -> dict:
    expected = {(p.first_entry_id, p.second_entry_id) for p in labels if p.duplicate}
    predicted = {(p["first_entry_id"], p["second_entry_id"]) for p in proposals}
    true_positives = len(predicted & expected)
    return {"labelled_pairs": len(labels), "true_positives": true_positives,
            "false_positives": len(predicted - expected),
            "false_negatives": len(expected - predicted),
            "precision": true_positives / len(predicted) if predicted else 0.0,
            "recall": true_positives / len(expected) if expected else 0.0}
