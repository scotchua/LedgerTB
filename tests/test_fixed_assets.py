from datetime import date

import pytest

from database.connection import get_cursor
from models.account import Account
from models.fixed_asset import FixedAsset, FixedAssetType
from models.journal_entry import JournalEntry
from services import mcp_tools
from services.fixed_assets import dispose_asset, run_depreciation


@pytest.fixture
def fixed_accounts(client_id, accounts):
    def make(number, name, account_type, subtype=None):
        account = Account(client_id=client_id, account_number=number, name=name,
                          type=account_type, subtype=subtype)
        account.save()
        return account.id

    return {
        **accounts,
        "asset": make("1500", "Equipment", "Asset", "Fixed Asset"),
        "accum": make("1590", "Accumulated Depreciation", "Asset",
                      "Accumulated Depreciation"),
        "depreciation": make("7000", "Depreciation Expense", "Expense",
                             "Depreciation & Amortization"),
        "gain_loss": make("7100", "Gain or Loss on Disposal", "Expense",
                          "Loss on Asset Disposal"),
    }


def _make_type(client_id, accounts, method="straight_line", life=3, rate=None):
    asset_type = FixedAssetType(
        client_id=client_id, name=f"Equipment {method} {life} {rate}",
        asset_account_id=accounts["asset"],
        accumulated_depreciation_account_id=accounts["accum"],
        depreciation_expense_account_id=accounts["depreciation"],
        method=method,
        effective_life_months=life if method == "straight_line" else None,
        annual_rate=rate if method == "declining_balance" else None,
    )
    asset_type.save()
    return asset_type


def _make_asset(client_id, asset_type, cost=10000, salvage=1000):
    asset = FixedAsset(
        client_id=client_id, fixed_asset_type_id=asset_type.id,
        description="Test machine", acquisition_date=date(2026, 1, 1),
        cost_cents=cost, salvage_value_cents=salvage,
        in_service_date=date(2026, 1, 15),
    )
    asset.save()
    return asset


def _run_amounts(asset_id):
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT amount_cents FROM depreciation_runs "
            "WHERE fixed_asset_id = ? ORDER BY period_end", (asset_id,))
        return [row["amount_cents"] for row in cursor.fetchall()]


def _entry_cents(entry_id, client_id):
    entry = JournalEntry.get_by_id(entry_id, client_id)
    return sorted((round(line.debit * 100), round(line.credit * 100))
                  for line in entry.lines)


def test_straight_line_full_life_caps_final_month(client_id, fixed_accounts):
    asset = _make_asset(client_id, _make_type(client_id, fixed_accounts),
                        cost=10000, salvage=0)
    for period_end in (date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)):
        run_depreciation(asset.id, period_end)

    assert _run_amounts(asset.id) == [3333, 3333, 3334]
    assert FixedAsset.get_by_id(asset.id).book_value_cents == 0


def test_declining_balance_concrete_months(client_id, fixed_accounts):
    asset_type = _make_type(client_id, fixed_accounts,
                            method="declining_balance", life=None, rate=0.24)
    asset = _make_asset(client_id, asset_type, cost=100000, salvage=0)
    for period_end in (date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)):
        run_depreciation(asset.id, period_end)

    assert _run_amounts(asset.id) == [2000, 1960, 1921]
    assert FixedAsset.get_by_id(asset.id).book_value_cents == 94119


def test_duplicate_period_is_refused_before_insert(client_id, fixed_accounts):
    asset = _make_asset(client_id, _make_type(client_id, fixed_accounts))
    run_depreciation(asset.id, date(2026, 1, 31))

    with pytest.raises(ValueError, match="already been run"):
        run_depreciation(asset.id, date(2026, 1, 31))
    assert JournalEntry.count(client_id) == 1


@pytest.mark.parametrize(
    "proceeds",
    [
        pytest.param(8000, id="gain"),
        pytest.param(5000, id="loss"),
        pytest.param(0, id="zero_proceeds"),
    ],
)
def test_disposal_gain_loss_and_zero(client_id, fixed_accounts, proceeds):
    asset = _make_asset(client_id, _make_type(client_id, fixed_accounts),
                        cost=10000, salvage=1000)
    run_depreciation(asset.id, date(2026, 1, 31))
    accumulated = sum(_run_amounts(asset.id))
    book_value = asset.cost_cents - accumulated
    gain_loss = proceeds - book_value
    expected_lines = [(0, asset.cost_cents), (accumulated, 0)]
    if proceeds:
        expected_lines.append((proceeds, 0))
    if gain_loss > 0:
        expected_lines.append((0, gain_loss))
    elif gain_loss < 0:
        expected_lines.append((-gain_loss, 0))
    entry_id = dispose_asset(
        asset.id, date(2026, 2, 15), proceeds,
        fixed_accounts["cash"], fixed_accounts["gain_loss"])

    assert _entry_cents(entry_id, client_id) == sorted(expected_lines)
    disposed = FixedAsset.get_by_id(asset.id)
    assert disposed.status == "disposed"
    assert disposed.disposal_proceeds_cents == proceeds


def test_disposing_already_disposed_asset_is_refused(client_id, fixed_accounts):
    asset = _make_asset(client_id, _make_type(client_id, fixed_accounts))
    dispose_asset(asset.id, date(2026, 2, 15), 0,
                  fixed_accounts["cash"], fixed_accounts["gain_loss"])

    with pytest.raises(ValueError, match="already been disposed"):
        dispose_asset(asset.id, date(2026, 2, 16), 0,
                      fixed_accounts["cash"], fixed_accounts["gain_loss"])


def test_propose_depreciation_creates_draft_only(client_id, fixed_accounts):
    asset = _make_asset(client_id, _make_type(client_id, fixed_accounts))
    result = mcp_tools.propose_depreciation_run(
        client_id, asset.id, "2026-01-31", "Monthly close")

    assert result["status"] == "pending"
    assert result["amount_cents"] == 3000
    assert JournalEntry.count(client_id) == 0
    assert _run_amounts(asset.id) == []


def test_fixed_asset_mutations_are_audited(client_id, fixed_accounts):
    asset_type = _make_type(client_id, fixed_accounts)
    asset = _make_asset(client_id, asset_type)
    run_depreciation(asset.id, date(2026, 1, 31))
    dispose_asset(asset.id, date(2026, 2, 15), 0,
                  fixed_accounts["cash"], fixed_accounts["gain_loss"])

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT table_name, action, performed_by FROM audit_log "
            "WHERE client_id = ? AND table_name IN "
            "('fixed_asset_types', 'fixed_assets', 'depreciation_runs') "
            "ORDER BY id", (client_id,))
        rows = cursor.fetchall()
    assert [(row["table_name"], row["action"]) for row in rows] == [
        ("fixed_asset_types", "INSERT"), ("fixed_assets", "INSERT"),
        ("depreciation_runs", "INSERT"), ("fixed_assets", "UPDATE"),
    ]
    assert all(row["performed_by"] for row in rows)


def test_mcp_depreciation_tool_is_propose_gated_and_not_post_gated():
    import inspect
    import mcp_server

    source = inspect.getsource(mcp_server.propose_depreciation_run)
    assert '_require_level("propose")' in source
    assert '_require_level("post")' not in source
    assert "run_depreciation(" not in source
