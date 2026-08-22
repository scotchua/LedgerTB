"""Account groupings: several accounts presenting as one line.

Grouping is opt-in. Detail is what the numbers are; a grouping is a presentation
choice, so nothing collapses unless it is asked for. The detail has to stay
reachable and the totals must not move, or the grouping is just a way to lose
information.

Accumulated depreciation is left out of the property grouping on purpose. It is
normally stated separately, and "net" belongs to intangibles. The netting test
below sets that grouping explicitly, because the mechanism still has to work for
anyone who does want it.
"""

from datetime import date

import pytest

from constants import AccountSubtype, AccountType
from models.account import Account
from models.reports import ReportGenerator
from tests.conftest import post_entry

PERIOD = (date(2026, 1, 1), date(2026, 12, 31))
AS_OF = date(2026, 12, 31)
PPE = "Property and equipment"
PAYROLL = "Payroll costs"


@pytest.fixture
def groupinged_chart(client_id):
    """Three equipment accounts under one grouping; depreciation on its own."""

    def make(number, name, account_type, grouping=None, subtype=None):
        account = Account(client_id=client_id, account_number=number, name=name,
                          type=account_type, subtype=subtype)
        account.account_grouping = grouping
        account.save()
        return account.id

    return {
        "cash": make("1000", "Operating Checking", AccountType.ASSET, subtype="Cash"),
        "trucks": make("1500", "Vehicles", AccountType.ASSET, PPE, "Fixed Asset"),
        "shop": make("1510", "Shop Equipment", AccountType.ASSET, PPE, "Fixed Asset"),
        "office": make("1520", "Office Equipment", AccountType.ASSET, PPE, "Fixed Asset"),
        "accum": make("1590", "Accumulated Depreciation", AccountType.ASSET,
                      None, "Contra Asset"),
        "capital": make("3000", "Owner's Capital", AccountType.EQUITY, subtype="Capital"),
        "sales": make("4000", "Cabinet Sales", AccountType.REVENUE),
        "wages": make("6000", "Wages", AccountType.EXPENSE, PAYROLL),
        "taxes": make("6010", "Payroll Taxes", AccountType.EXPENSE, PAYROLL),
        "rent": make("6500", "Rent", AccountType.EXPENSE),
    }


@pytest.fixture
def booked(client_id, groupinged_chart):
    chart = groupinged_chart
    post_entry(client_id, date(2026, 1, 2), [
        (chart["trucks"], 40000, 0),
        (chart["shop"], 15000, 0),
        (chart["office"], 5000, 0),
        (chart["capital"], 0, 60000),
    ])
    post_entry(client_id, date(2026, 12, 31), [
        (chart["cash"], 12000, 0),
        (chart["sales"], 0, 12000),
    ])
    post_entry(client_id, date(2026, 12, 31), [
        (chart["wages"], 7000, 0),
        (chart["taxes"], 800, 0),
        (chart["rent"], 1200, 0),
        (chart["cash"], 0, 9000),
    ])
    return chart


def grouped_bs(client_id):
    return ReportGenerator.balance_sheet(client_id, AS_OF, group_accounts=True)


def detail_bs(client_id):
    return ReportGenerator.balance_sheet(client_id, AS_OF)


# --- grouping is opt-in -----------------------------------------------------

def test_nothing_groups_unless_it_is_asked_for(client_id, booked):
    """The default is what the numbers are, not how someone presents them."""
    names = [item["name"] for item in detail_bs(client_id)["assets"]]

    for account in ("Vehicles", "Shop Equipment", "Office Equipment"):
        assert account in names
    assert PPE not in names


def test_asking_for_it_collapses_the_group(client_id, booked):
    report = grouped_bs(client_id)
    names = [item["name"] for item in report["assets"]]

    assert PPE in names
    for hidden in ("Vehicles", "Shop Equipment", "Office Equipment"):
        assert hidden not in names

    line = next(i for i in report["assets"] if i["name"] == PPE)
    assert line["balance"] == 60000
    # A grouping is not an account, so it carries no account number.
    assert line["account_number"] == ""


def test_switching_back_and_forth_is_stable(client_id, booked):
    """Flipping the toggle repeatedly must keep giving the same two answers."""
    first_detail = [(i["name"], i["balance"]) for i in detail_bs(client_id)["assets"]]
    first_grouped = [(i["name"], i["balance"]) for i in grouped_bs(client_id)["assets"]]

    assert [(i["name"], i["balance"]) for i in detail_bs(client_id)["assets"]] == first_detail
    assert [(i["name"], i["balance"]) for i in grouped_bs(client_id)["assets"]] == first_grouped
    assert first_detail != first_grouped


def test_grouping_never_moves_a_total(client_id, booked):
    grouped = grouped_bs(client_id)
    detailed = detail_bs(client_id)

    assert grouped["total_assets"] == detailed["total_assets"]
    assert grouped["total_liabilities"] == detailed["total_liabilities"]
    assert grouped["total_equity"] == detailed["total_equity"]
    assert grouped["total_assets"] == grouped["total_liabilities_equity"]

    grouped_subtotals = {
        group["key"]: group["subtotal"] for group in grouped["asset_groups"]
    }
    detailed_subtotals = {
        group["key"]: group["subtotal"] for group in detailed["asset_groups"]
    }
    assert grouped_subtotals == detailed_subtotals


def test_caption_stays_split_across_statement_groups(
    client_id, booked, groupinged_chart
):
    cash = Account.get_by_id(groupinged_chart["cash"], client_id)
    cash.account_grouping = PPE
    cash.save()

    report = grouped_bs(client_id)
    caption_groups = [
        group["key"] for group in report["asset_groups"]
        if any(item["name"] == PPE for item in group["accounts"])
    ]

    assert caption_groups == ["current_assets", "property_equipment_net"]


def test_ungroupinged_accounts_are_untouched(client_id, booked):
    names = [item["name"] for item in grouped_bs(client_id)["assets"]]

    assert "Operating Checking" in names


def test_the_grouping_sits_where_its_first_account_sat(client_id, booked):
    names = [item["name"] for item in grouped_bs(client_id)["assets"]]

    assert names.index("Operating Checking") < names.index(PPE)


# --- accumulated depreciation ----------------------------------------------

def test_depreciation_stays_on_its_own_line_by_default(client_id, booked, groupinged_chart):
    """It is normally stated separately, so it must not be swept into the
    property grouping just because it is a fixed-asset account."""
    post_entry(client_id, date(2026, 12, 31), [
        (groupinged_chart["rent"], 9000, 0),
        (groupinged_chart["accum"], 0, 9000),
    ])

    report = grouped_bs(client_id)
    names = [item["name"] for item in report["assets"]]

    assert "Accumulated Depreciation" in names
    assert next(i for i in report["assets"] if i["name"] == PPE)["balance"] == 60000
    assert next(i for i in report["assets"]
                if i["name"] == "Accumulated Depreciation")["balance"] == -9000


def test_a_contra_account_nets_when_it_is_given_the_grouping(client_id, booked, groupinged_chart):
    """Not the default presentation, but the mechanism has to work for whoever
    does want a single net line."""
    accum = Account.get_by_id(groupinged_chart["accum"], client_id)
    accum.account_grouping = PPE
    accum.save()

    post_entry(client_id, date(2026, 12, 31), [
        (groupinged_chart["rent"], 9000, 0),
        (groupinged_chart["accum"], 0, 9000),
    ])

    report = grouped_bs(client_id)
    assert next(i for i in report["assets"] if i["name"] == PPE)["balance"] == 51000
    assert all(i["name"] != "Accumulated Depreciation" for i in report["assets"])


# --- editing a grouping -----------------------------------------------------

def test_an_account_can_be_taken_out_of_a_grouping(client_id, booked, groupinged_chart):
    """Clearing the grouping returns the account to its own line, and the
    remaining group carries on without it."""
    office = Account.get_by_id(groupinged_chart["office"], client_id)
    office.account_grouping = None
    office.save()

    report = grouped_bs(client_id)
    names = [item["name"] for item in report["assets"]]

    assert "Office Equipment" in names
    assert next(i for i in report["assets"] if i["name"] == PPE)["balance"] == 55000
    assert next(i for i in report["assets"]
                if i["name"] == "Office Equipment")["balance"] == 5000
    assert report["total_assets"] == detail_bs(client_id)["total_assets"]


def test_an_account_can_be_moved_to_a_different_grouping(client_id, booked, groupinged_chart):
    office = Account.get_by_id(groupinged_chart["office"], client_id)
    office.account_grouping = "Office and computer equipment"
    office.save()

    report = grouped_bs(client_id)
    by_name = {i["name"]: i["balance"] for i in report["assets"]}

    assert by_name[PPE] == 55000
    assert by_name["Office and computer equipment"] == 5000
    assert "Office Equipment" not in by_name


def test_emptying_a_group_removes_the_grouping_entirely(client_id, booked, groupinged_chart):
    for key in ("trucks", "shop", "office"):
        account = Account.get_by_id(groupinged_chart[key], client_id)
        account.account_grouping = None
        account.save()

    names = [item["name"] for item in grouped_bs(client_id)["assets"]]

    assert PPE not in names
    assert "Vehicles" in names


def test_renaming_a_grouping_on_every_member_renames_the_line(client_id, booked, groupinged_chart):
    for key in ("trucks", "shop", "office"):
        account = Account.get_by_id(groupinged_chart[key], client_id)
        account.account_grouping = "Plant and equipment"
        account.save()

    by_name = {i["name"]: i["balance"] for i in grouped_bs(client_id)["assets"]}

    assert by_name["Plant and equipment"] == 60000
    assert PPE not in by_name


def test_the_grouping_round_trips_and_is_audited(client_id, groupinged_chart):
    from models.audit_log import AuditLog

    account = Account.get_by_id(groupinged_chart["rent"], client_id)
    assert account.account_grouping is None

    account.account_grouping = "Occupancy"
    account.save()

    assert Account.get_by_id(account.id, client_id).account_grouping == "Occupancy"
    latest = AuditLog.get_history("accounts", account.id)[0]
    assert latest.old_values["account_grouping"] is None
    assert latest.new_values["account_grouping"] == "Occupancy"


def test_clearing_a_grouping_is_audited_too(client_id, groupinged_chart):
    from models.audit_log import AuditLog

    account = Account.get_by_id(groupinged_chart["trucks"], client_id)
    account.account_grouping = None
    account.save()

    latest = AuditLog.get_history("accounts", account.id)[0]
    assert latest.old_values["account_grouping"] == PPE
    assert latest.new_values["account_grouping"] is None


# --- the income statement ---------------------------------------------------

def test_expense_groupings_group_too(client_id, booked):
    report = ReportGenerator.income_statement(client_id, *PERIOD, group_accounts=True)
    names = [item["name"] for item in report["expenses"]]

    assert PAYROLL in names
    assert "Wages" not in names
    assert "Rent" in names  # no grouping, presents on its own

    assert next(i for i in report["expenses"]
                if i["name"] == PAYROLL)["balance"] == 7800


def test_net_income_is_unchanged_by_grouping(client_id, booked):
    grouped = ReportGenerator.income_statement(client_id, *PERIOD, group_accounts=True)
    detailed = ReportGenerator.income_statement(client_id, *PERIOD)

    assert grouped["net_income"] == detailed["net_income"] == 3000
    assert grouped["total_expenses"] == detailed["total_expenses"] == 9000


# --- comparative statements -------------------------------------------------

def test_both_periods_group_the_same_way(client_id, booked):
    """A grouping in one year facing its own accounts in the other would produce
    a comparison of unrelated things."""
    report = ReportGenerator.comparative_balance_sheet(
        client_id, AS_OF, group_accounts=True)
    names = [item["name"] for item in report["assets"]]

    assert PPE in names
    assert "Vehicles" not in names


def test_the_comparative_default_is_detail_as_well(client_id, booked):
    report = ReportGenerator.comparative_balance_sheet(client_id, AS_OF)
    names = [item["name"] for item in report["assets"]]

    assert "Vehicles" in names
    assert PPE not in names


# --- a grouping that nets to nothing ----------------------------------------

def test_a_grouping_that_nets_to_zero_is_omitted(client_id, groupinged_chart):
    """Same treatment a single account with no balance already gets."""
    chart = groupinged_chart
    accum = Account.get_by_id(chart["accum"], client_id)
    accum.account_grouping = PPE
    accum.save()

    post_entry(client_id, date(2026, 6, 1), [
        (chart["trucks"], 5000, 0),
        (chart["accum"], 0, 5000),
    ])

    names = [item["name"] for item in grouped_bs(client_id)["assets"]]

    assert PPE not in names


# --- the deliverable --------------------------------------------------------

def test_the_close_package_presents_groupings(client_id, booked):
    """The package is the statement that leaves the building, so it groups even
    though the in-app view does not by default."""
    import openpyxl
    from io import BytesIO
    from services.close_package import build_close_package

    tb_rows, _ = ReportGenerator.trial_balance_worksheet(client_id, *PERIOD)
    package = build_close_package(client_id, "Kettle Ridge Cabinetry",
                                  *PERIOD, tb_rows)
    wb = openpyxl.load_workbook(BytesIO(package.read()))
    balance_sheet = wb["Balance Sheet"]
    labels = [balance_sheet.cell(row=i, column=1).value
              for i in range(1, balance_sheet.max_row + 1)]

    assert any(label and label.strip() == PPE for label in labels)
    assert not any(label and label.strip() == "Vehicles" for label in labels)
    # The detail is still in the package, on the trial balance.
    tb_labels = [wb["Trial Balance"].cell(row=i, column=2).value
                 for i in range(1, wb["Trial Balance"].max_row + 1)]
    assert "Vehicles" in tb_labels


def test_cross_group_caption_stays_split_in_comparative_grouped_view(
    client_id, accounts
):
    """The collapse boundary is the statement group in every path.

    This exact case shipped broken in review: the flat lists collapsed at the
    section boundary, and the comparative path then re-bucketed the merged
    caption line whole into the first member's group. Current Assets absorbed
    an Other Asset's balance, but only while the prior-year comparison was on,
    so the same book answered differently depending on a display toggle.
    """
    short = Account(
        client_id=client_id, account_number="1300",
        name="Affiliate Advance ST", type="Asset",
        subtype=AccountSubtype.OTHER_CURRENT_ASSET,
        account_grouping="Due from affiliates",
    )
    short.save()
    long_term = Account(
        client_id=client_id, account_number="1900",
        name="Affiliate Advance LT", type="Asset",
        subtype=AccountSubtype.OTHER_ASSET,
        account_grouping="Due from affiliates",
    )
    long_term.save()
    equity = Account(
        client_id=client_id, account_number="3000B", name="Owner Equity",
        type="Equity", subtype=AccountSubtype.OWNER_CONTRIBUTION,
    )
    equity.save()
    post_entry(client_id, date(2026, 2, 1),
               [(short.id, 4000, 0), (equity.id, 0, 4000)])
    post_entry(client_id, date(2026, 2, 1),
               [(long_term.id, 6000, 0), (equity.id, 0, 6000)])

    report = ReportGenerator.comparative_balance_sheet(
        client_id, date(2026, 12, 31), group_accounts=True
    )
    subtotals = {
        group['group']: group['subtotal']['current']
        for group in report['asset_groups']
    }
    assert subtotals['Current Assets'] == 4000.0
    assert subtotals['Other Assets'] == 6000.0
    # Both groups carry a caption line of the same name, never one merged line.
    captions = [
        (group['group'], account['name'], account['current'])
        for group in report['asset_groups']
        for account in group['accounts']
        if account['name'] == "Due from affiliates"
    ]
    assert captions == [
        ('Current Assets', 'Due from affiliates', 4000.0),
        ('Other Assets', 'Due from affiliates', 6000.0),
    ]
