"""Direct tests for the receivables value objects."""

from datetime import date
import importlib.util
import os
from pathlib import Path
import sys


def _models():
    source = Path(os.environ.get(
        "RECEIVABLES_MUTATION_SOURCE",
        Path(__file__).resolve().parents[1] / "models" / "receivables.py",
    ))
    spec = importlib.util.spec_from_file_location("_receivables_model_test", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_customer_defaults():
    customer = _models().Customer(name="Juniper Studio")
    assert customer.client_id == 0
    assert customer.email is None


def test_invoice_line_amount_cents():
    InvoiceLine = _models().InvoiceLine
    assert InvoiceLine(unit_price_cents=175).amount_cents == 175
    assert InvoiceLine(quantity=3, unit_price_cents=175).amount_cents == 525


def test_invoice_subtotal_cents():
    models = _models()
    invoice = models.Invoice(lines=[
        models.InvoiceLine(quantity=2, unit_price_cents=125),
        models.InvoiceLine(quantity=1, unit_price_cents=80),
    ])
    assert invoice.subtotal_cents == 330


def test_invoice_total_cents():
    models = _models()
    invoice = models.Invoice(
        invoice_date=date(2026, 4, 2), due_date=date(2026, 4, 30),
        lines=[models.InvoiceLine(quantity=2, unit_price_cents=125)],
        tax_amount_cents=25,
    )
    assert invoice.total_cents == 275


def test_invoice_defaults():
    invoice = _models().Invoice(customer_id=17)
    assert invoice.tax_amount_cents == 0
    assert invoice.lines == []


def test_credit_memo_line_amount_cents():
    CreditMemoLine = _models().CreditMemoLine
    assert CreditMemoLine(unit_price_cents=90).amount_cents == 90
    assert CreditMemoLine(quantity=3, unit_price_cents=90).amount_cents == 270


def test_credit_memo_subtotal_cents():
    models = _models()
    memo = models.CreditMemo(lines=[
        models.CreditMemoLine(quantity=2, unit_price_cents=115),
        models.CreditMemoLine(quantity=1, unit_price_cents=45),
    ])
    assert memo.subtotal_cents == 275


def test_credit_memo_total_cents():
    models = _models()
    memo = models.CreditMemo(
        memo_date=date(2026, 5, 9),
        lines=[models.CreditMemoLine(quantity=2, unit_price_cents=115)],
        tax_amount_cents=23,
    )
    assert memo.total_cents == 253


def test_credit_memo_defaults():
    memo = _models().CreditMemo(customer_id=19)
    assert memo.tax_amount_cents == 0
    assert memo.lines == []
