"""Direct checks for the payable value objects."""

import importlib.util
from datetime import date
from pathlib import Path
import sys


MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "payables.py"


def _payables():
    spec = importlib.util.spec_from_file_location("payables_model_under_test", MODEL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_vendor_defaults():
    vendor = _payables().Vendor()
    assert (vendor.id, vendor.client_id, vendor.name, vendor.normalized_name,
            vendor.email, vendor.created_at) == (None, 0, "", "", None, None)


def test_bill_line_defaults():
    line = _payables().BillLine()
    assert (line.id, line.bill_id, line.description, line.quantity,
            line.unit_price_cents, line.expense_account_id, line.amount_cents) == (
                None, None, "", 1, 0, 0, 0,
            )


def test_bill_line_amount_uses_quantity_and_unit_price():
    line = _payables().BillLine(
        id=43, bill_id=31, description="Cedar paper", quantity=3,
        unit_price_cents=245, expense_account_id=6107,
    )
    assert line.amount_cents == 735
    line.quantity = 2
    assert line.amount_cents == 490


def test_bill_defaults():
    bill = _payables().Bill()
    assert (bill.id, bill.client_id, bill.vendor_id, bill.bill_date,
            bill.due_date, bill.status, bill.journal_entry_id,
            bill.voided_journal_entry_id, bill.control_account_id,
            bill.tax_rate, bill.tax_amount_cents, bill.tax_account_id) == (
                None, 0, 0, None, None, "draft", None, None, None, None, 0, None,
            )
    assert bill.lines == []
    assert bill.subtotal_cents == bill.total_cents == 0


def test_bill_lines_are_independent():
    payables = _payables()
    first = payables.Bill()
    second = payables.Bill()
    first.lines.append(payables.BillLine(quantity=2, unit_price_cents=175))
    assert first.subtotal_cents == 350
    assert second.lines == []
    assert second.subtotal_cents == 0


def test_bill_subtotal_sums_each_extended_line():
    payables = _payables()
    bill = payables.Bill(lines=[
        payables.BillLine(quantity=2, unit_price_cents=175),
        payables.BillLine(quantity=3, unit_price_cents=89),
    ])
    assert bill.subtotal_cents == 617
    bill.lines.append(payables.BillLine(quantity=1, unit_price_cents=41))
    assert bill.subtotal_cents == 658


def test_bill_total_adds_tax_once():
    payables = _payables()
    bill = payables.Bill(
        id=31, client_id=29, vendor_id=17, bill_date=date(2026, 4, 3),
        due_date=date(2026, 5, 3), status="posted", journal_entry_id=71,
        control_account_id=2107, tax_rate="0.10", tax_amount_cents=35,
        tax_account_id=2207,
        lines=[payables.BillLine(quantity=2, unit_price_cents=175)],
    )
    assert bill.subtotal_cents == 350
    assert bill.total_cents == 385
    bill.tax_amount_cents = 0
    assert bill.total_cents == 350
