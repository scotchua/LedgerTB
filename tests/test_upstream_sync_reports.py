"""Recorded statement expectations for journals produced by the fork engines."""

import json
from datetime import date
from pathlib import Path

import pytest

from database.connection import get_cursor
from models.account import Account
from models.fixed_asset import FixedAsset, FixedAssetType
from models.payroll import Employee
from models.reports import CASH_FLOW_STATEMENT_SECTIONS, ReportGenerator
from services.ar_ap import (
    create_bill, create_credit_memo, create_customer, create_invoice, create_vendor,
    post_bill, post_credit_memo, post_invoice, record_customer_payment,
    record_vendor_payment,
)
from services.fixed_assets import run_depreciation
from services.inventory import create_item, inventory_position, record_movement
from services.payroll_recording import add_pay_stub, create_pay_run, post_pay_run
from tests.conftest import post_entry


START = date(2026, 1, 1)
END = date(2026, 1, 31)
EXPECTED = json.loads(
    (Path(__file__).parent / "fixtures" / "upstream_sync_reports.json").read_text()
)


@pytest.fixture
def engine_book(client_id):
    definitions = [
        ("cash", "1000", "Workshop Checking", "Asset", "Bank", "Operating balances"),
        ("ar", "1100", "Accounts Receivable", "Asset", "Accounts Receivable", "Operating balances"),
        ("inventory", "1200", "Materials", "Asset", "WIP", "Operating balances"),
        ("equipment", "1500", "Shop Equipment", "Asset", "Equipment", "Operating balances"),
        ("office", "1510", "Office Equipment", "Asset", "Equipment", "Operating balances"),
        ("accum", "1590", "Accumulated Depreciation", "Asset", "Contra Asset", "Operating balances"),
        ("ap", "2000", "Accounts Payable", "Liability", "Payable", "Amounts payable"),
        ("tax", "2100", "Sales Tax Payable", "Liability", "Tax", "Amounts payable"),
        ("withholding", "2200", "Recorded Withholding", "Liability", "Accrual", "Amounts payable"),
        ("benefit_payable", "2210", "Recorded Benefits", "Liability", "Accrual", "Amounts payable"),
        ("capital", "3000", "Common Stock", "Equity", "Capital", "Workshop funding"),
        ("sales", "4000", "Product Sales", "Revenue", "Product Revenue", "Workshop sales"),
        ("cogs", "5000", "Materials Used", "Expense", "COGS", "Workshop costs"),
        ("wages", "6000", "Wages", "Expense", "Operating Expense", "Workshop costs"),
        ("benefits", "6010", "Benefits", "Expense", "Operating Expense", "Workshop costs"),
        ("supplies", "6100", "Shop Supplies", "Expense", "Operating Expense", "Workshop costs"),
        ("prior_wages", "6500", "Legacy Wages", "Expense", "Payroll", "Workshop costs"),
        ("depreciation", "7000", "Depreciation", "Expense", "Non-Cash", "Workshop costs"),
    ]
    chart = {}
    for key, number, name, account_type, subtype, caption in definitions:
        account = Account(
            client_id=client_id, account_number=number, name=name,
            type=account_type, subtype=subtype, account_grouping=caption,
        )
        chart[key] = account.save()
    # Reproduce stored legacy aliases; Account.save normalizes new input.
    with get_cursor(commit=True) as cursor:
        for key, _number, _name, _type, subtype, _caption in definitions:
            cursor.execute("UPDATE accounts SET subtype = ? WHERE id = ?",
                           (subtype, chart[key]))

    post_entry(client_id, date(2025, 1, 1), [
        (chart["cash"], 10000, 0), (chart["capital"], 0, 10000),
    ], entry_type="Beginning Balance")
    employee = Employee(client_id=client_id, name="Fixture Worker",
                        start_date=date(2025, 1, 1))
    employee.save()
    prior_run = create_pay_run(client_id, date(2025, 1, 1), date(2025, 1, 15),
                               date(2025, 1, 20))
    add_pay_stub(prior_run.id, employee.id, 10000, [], 10000)
    post_pay_run(prior_run.id, {}, chart["prior_wages"], chart["cash"], {})

    item = create_item(client_id, "FIXTURE", "Fixture material",
                       chart["inventory"], chart["cogs"])
    record_movement(item, START, "purchase", 20, 1000,
                    post_journal_entry=True, offset_account_id=chart["cash"])
    customer = create_customer(client_id, "Fixture Customer")
    invoice = create_invoice(client_id, customer.id, [{
        "description": "Materials", "quantity": 5, "unit_price_cents": 3000,
        "revenue_account_id": chart["sales"], "inventory_item_id": item,
    }], date(2026, 1, 5), END, "0.10")
    post_invoice(invoice.id, chart["ar"], chart["tax"])
    record_customer_payment(client_id, customer.id, date(2026, 1, 10),
                            10000, chart["cash"],
                            [{"invoice_id": invoice.id, "amount_cents": 10000}])
    credit = create_credit_memo(client_id, customer.id, [{
        "description": "Price allowance", "quantity": 1, "unit_price_cents": 2000,
        "revenue_account_id": chart["sales"],
    }], date(2026, 1, 12), "0.10", invoice.id)
    post_credit_memo(credit.id, chart["ar"], chart["tax"])

    vendor = create_vendor(client_id, "Fixture Supplier")
    bill = create_bill(client_id, vendor.id, [{
        "description": "Shop supplies", "quantity": 1, "unit_price_cents": 50000,
        "expense_account_id": chart["supplies"],
    }], START, END)
    post_bill(bill.id, chart["ap"])
    record_vendor_payment(client_id, vendor.id, date(2026, 1, 15),
                          40000, chart["cash"],
                          [{"bill_id": bill.id, "amount_cents": 40000}])
    post_entry(client_id, START, [
        (chart["equipment"], 1200, 0), (chart["office"], 600, 0),
        (chart["cash"], 0, 1800),
    ])
    for key, cost in (("equipment", 120000), ("office", 60000)):
        asset_type = FixedAssetType(
            client_id=client_id, name=key, asset_account_id=chart[key],
            accumulated_depreciation_account_id=chart["accum"],
            depreciation_expense_account_id=chart["depreciation"],
            effective_life_months=12,
        )
        asset_type.save()
        asset = FixedAsset(
            client_id=client_id, fixed_asset_type_id=asset_type.id,
            description=key, acquisition_date=START, cost_cents=cost,
            in_service_date=START,
        )
        asset.save()
        run_depreciation(asset.id, END)

    run = create_pay_run(client_id, START, date(2026, 1, 15), date(2026, 1, 20))
    add_pay_stub(run.id, employee.id, 30000,
                 [{"label": "Recorded withholding", "amount_cents": 3000}], 27000,
                 employer_costs=[{"label": "Recorded benefit", "amount_cents": 5000}])
    post_pay_run(run.id, {}, chart["wages"], chart["cash"],
                 {"Recorded withholding": chart["withholding"]},
                 {"Recorded benefit": (chart["benefits"], chart["benefit_payable"])})
    assert inventory_position(item)["value_cents"] == 15000
    return chart


def _group_lines(report, key, *amount_fields):
    return [
        [group["key"], line["name"], *(line[field] for field in amount_fields)]
        for group in report[key] for line in group["accounts"]
    ]


def test_engine_statements_keep_captions_inside_upstream_sections(client_id, engine_book):
    income = ReportGenerator.income_statement(client_id, START, END, group_accounts=True)
    balance = ReportGenerator.balance_sheet(client_id, END, group_accounts=True)
    for report, expected, group_keys in (
        (income, EXPECTED["income_statement"], ("revenue_groups", "expense_groups")),
        (balance, EXPECTED["balance_sheet"], ("asset_groups", "liability_groups", "equity_groups")),
    ):
        for key, value in expected.items():
            if not isinstance(value, list):
                assert report[key] == value, key
        for key in group_keys:
            assert _group_lines(report, key, "balance") == expected[key]
            for group in report[key]:
                assert group["subtotal"] == sum(line["balance"] for line in group["accounts"])

    comparison = ReportGenerator.comparative_income_statement(
        client_id, START, END, group_accounts=True,
    )
    assert _group_lines(comparison, "expense_groups", "current", "prior") == (
        EXPECTED["income_statement"]["comparative_expense_groups"]
    )
    comparative_balance = ReportGenerator.comparative_balance_sheet(
        client_id, END, group_accounts=True,
    )
    for key in ("asset_groups", "liability_groups", "equity_groups"):
        assert _group_lines(comparative_balance, key, "current") == EXPECTED["balance_sheet"][key]
    assert comparative_balance["current_balanced"] is True
    assert comparative_balance["prior_balanced"] is True
    assert income["multistep_ready"] is True


@pytest.mark.parametrize("override", [None, "financing"])
def test_engine_cash_flow_override_wins_over_upstream_subtype(client_id, engine_book, override):
    if override:
        payable = Account.get_by_id(engine_book["ap"], client_id)
        payable.cash_flow_section = override
        payable.save()
    report = ReportGenerator.cash_flow_statement(client_id, START, END)
    expected = EXPECTED["cash_flow"]
    for section, amount in expected[override or "default"].items():
        assert report[section]["total"] == amount, section
    for key in ("cash_beginning", "cash_ending", "actual_cash_change", "computed_cash_change"):
        assert report[key] == expected[key], key
    assert [line["amount"] for line in report["noncash_items"]] == (
        expected["noncash_amounts"][override or "default"]
    )
    assert report["unclassified"]["entries"] == []
    assert report["ready"] is True
    assert report["reconciliation_difference"] == 0
    if override:
        assert [[line["name"], line["amount"]] for line in report["financing"]["lines"]] == (
            expected["financing_lines"]
        )
        assert [[line["key"], line["amount"]] for line in report["operating"]["lines"]] == (
            expected["override_operating_lines"]
        )
    comparison = ReportGenerator.comparative_cash_flow_statement(client_id, START, END)
    for section, amount in expected[override or "default"].items():
        assert comparison[section]["total"]["current"] == amount
    assert comparison["current_ready"] is True
    labels = ReportGenerator.cash_flow_statement_to_dataframe(report)["Item"].tolist()
    for _heading, _section, label in CASH_FLOW_STATEMENT_SECTIONS:
        assert label in labels
