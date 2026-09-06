import calendar
import sqlite3
from contextlib import closing
from datetime import date

import pytest

from database import schema
from database.connection import _driver, get_cursor
from models.audit_log import AuditLog
from models.draft_entry import DraftEntry
from models.fiscal_period import FiscalPeriod
from models.fixed_asset import FixedAsset, FixedAssetType
from models.journal_entry import JournalEntry
from services import fixed_assets, mcp_tools
from conftest import post_entry
from test_fixed_assets import fixed_accounts


def _asset(client_id, accounts, method="straight_line", convention="full_month",
           cost=12000, salvage=0, life=3, rate=None, total_units=None,
           service=date(2026, 1, 15)):
    asset_type = FixedAssetType(
        client_id=client_id, name=f"{method} {convention}",
        asset_account_id=accounts["asset"],
        accumulated_depreciation_account_id=accounts["accum"],
        depreciation_expense_account_id=accounts["depreciation"],
        method=method, convention=convention,
        effective_life_months=life if method == "straight_line" else None,
        annual_rate=rate, total_units=total_units,
    )
    asset_type.save()
    asset = FixedAsset(
        client_id=client_id, fixed_asset_type_id=asset_type.id,
        description="Oracle machine", acquisition_date=service,
        in_service_date=service, cost_cents=cost, salvage_value_cents=salvage,
    )
    asset.save()
    return asset


def _month_ends(year, month, count):
    for offset in range(count):
        current_year, current_month = divmod(year * 12 + month - 1 + offset, 12)
        current_month += 1
        yield date(current_year, current_month,
                   calendar.monthrange(current_year, current_month)[1])


def _runs(asset):
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM depreciation_runs WHERE fixed_asset_id = ? "
            "ORDER BY period_end, run_seq", (asset.id,),
        )
        return [dict(row) for row in cursor.fetchall()]


@pytest.mark.parametrize("convention,life,cost,service,expected", [
    # 10000 / 3 = 3333.333; the final month takes 10000 - 6666.
    ("full_month", 3, 10000, date(2026, 1, 15), [3333, 3333, 3334]),
    # 12000 / 3 = 4000; half + full + full + half = 12000.
    ("mid_month", 3, 12000, date(2026, 1, 23), [2000, 4000, 4000, 2000]),
    # 24000 / 24 = 1000; 12*500 + 12*1000 + 12*500 = 24000.
    ("half_year", 24, 24000, date(2026, 1, 15),
     [500] * 12 + [1000] * 12 + [500] * 12),
    # First-year weight 6/3 = 2; 3*2000 + 12*500 = 12000.
    ("half_year", 12, 12000, date(2026, 10, 23), [2000] * 3 + [500] * 12),
])
def test_straight_line_convention_oracles(
    client_id, fixed_accounts, convention, life, cost, service, expected,
):
    asset = _asset(client_id, fixed_accounts, convention=convention,
                   life=life, cost=cost, service=service)
    for period in _month_ends(service.year, service.month, len(expected)):
        fixed_assets.run_depreciation(asset.id, period)
    assert [row["amount_cents"] for row in _runs(asset)] == expected
    assert asset.accumulated_depreciation_cents == cost
    assert asset.book_value_cents == 0


@pytest.mark.parametrize("convention,salvage,expected", [
    # 100000*.24/12 = 2000; 98000*.02 = 1960; 96040*.02 = 1920.8.
    ("full_month", 0, [2000, 1960, 1921]),
    # 100000*.02*.5 = 1000; 99000*.02 = 1980.
    ("mid_month", 0, [1000, 1980]),
    # January service: monthly weight 6/12; 99000*.02*.5 = 990.
    ("half_year", 0, [1000, 990]),
    # Only 100000 - 99950 = 50 remains above salvage.
    ("mid_month", 99950, [50]),
])
def test_declining_balance_convention_oracles(
    client_id, fixed_accounts, convention, salvage, expected,
):
    asset = _asset(client_id, fixed_accounts, method="declining_balance",
                   convention=convention, cost=100000, salvage=salvage, rate=0.24)
    for period in _month_ends(2026, 1, len(expected)):
        fixed_assets.run_depreciation(asset.id, period)
    assert [row["amount_cents"] for row in _runs(asset)] == expected


@pytest.mark.parametrize("convention", ["full_month", "mid_month", "half_year"])
def test_production_oracle_and_final_rounding(client_id, fixed_accounts, convention):
    asset = _asset(client_id, fixed_accounts, method="units_of_production",
                   convention=convention, cost=10000, total_units=3)
    # 10000 * 1/3 rounds to 3333 twice; the last unit takes 3334.
    for period in _month_ends(2026, 1, 3):
        fixed_assets.run_depreciation(asset.id, period, units_produced=1)
    assert [row["amount_cents"] for row in _runs(asset)] == [3333, 3333, 3334]


@pytest.mark.parametrize("via_draft", [False, True])
def test_correction_reverses_then_posts_and_duplicate_seq_is_refused(
    client_id, fixed_accounts, via_draft,
):
    asset = _asset(client_id, fixed_accounts, method="units_of_production",
                   cost=10000, salvage=1000, total_units=100)
    period = date(2026, 1, 31)
    first_id = fixed_assets.run_depreciation(asset.id, period, units_produced=25)
    first = _runs(asset)[0]
    # (10000 - 1000) * 25/100 = 2250; corrected 40/100 = 3600.
    proposal = mcp_tools.propose_depreciation_run(
        client_id, asset.id, period.isoformat(), "Correct output",
        run_seq=1, units_produced=40,
    )
    assert proposal["amount_cents"] == 3600
    assert proposal["run_seq"] == 1
    assert JournalEntry.count(client_id) == 1
    assert _runs(asset)[0]["superseded_by"] is None
    draft = DraftEntry.get_by_id(proposal["draft_id"], client_id)
    if via_draft:
        draft.approve()
    else:
        fixed_assets.run_depreciation(asset.id, period, run_seq=1, units_produced=40)
        with pytest.raises(ValueError, match="already been run.*nothing was posted"):
            draft.approve()
        assert DraftEntry.get_by_id(draft.id, client_id).status == "pending"

    old, replacement = _runs(asset)
    assert (old["id"], old["run_seq"], old["superseded_by"]) == (
        first_id, 0, replacement["id"])
    assert (replacement["run_seq"], replacement["units_produced"],
            replacement["amount_cents"]) == (1, 40, 3600)
    original = JournalEntry.get_by_id(first["journal_entry_id"], client_id)
    reversal = JournalEntry.get_by_id(original.reversed_by_journal_entry_id, client_id)
    assert reversal.reverses_journal_entry_id == original.id
    assert original.id < reversal.id < replacement["journal_entry_id"]
    assert reversal.entry_date == period
    assert [(line.account_id, line.debit, line.credit) for line in reversal.lines] == [
        (line.account_id, line.credit, line.debit) for line in original.lines]
    assert asset.accumulated_depreciation_cents == 3600
    for sequence in (0, 1):
        with pytest.raises(ValueError, match="already been run"):
            fixed_assets.run_depreciation(asset.id, period, run_seq=sequence,
                                          units_produced=40)
        with pytest.raises(ValueError, match="already been run"):
            fixed_assets.propose_depreciation_run(asset.id, period,
                                                  run_seq=sequence, units_produced=40)
    assert JournalEntry.count(client_id) == 3
    # A second correction consumes the next sequence, even if the amount is unchanged.
    fixed_assets.run_depreciation(asset.id, period, run_seq=2, units_produced=40)
    fixed_assets.run_depreciation(asset.id, date(2026, 2, 28), units_produced=60)
    assert asset.accumulated_depreciation_cents == 9000


@pytest.mark.parametrize("via_draft", [False, True])
def test_correction_failure_rolls_back_reversal_and_supersession(
    client_id, fixed_accounts, monkeypatch, via_draft,
):
    asset = _asset(client_id, fixed_accounts)
    period = date(2026, 1, 31)
    fixed_assets.run_depreciation(asset.id, period)
    proposal = fixed_assets.propose_depreciation_run(asset.id, period, run_seq=1)
    original_write = AuditLog.write

    def fail_run_audit(cursor, client_id, table_name, record_id, action, **kwargs):
        if table_name == "depreciation_runs" and action == "UPDATE":
            raise RuntimeError("forced supersession audit failure")
        return original_write(cursor, client_id, table_name, record_id, action, **kwargs)

    monkeypatch.setattr(AuditLog, "write", fail_run_audit)
    with pytest.raises(RuntimeError, match="forced supersession"):
        if via_draft:
            DraftEntry.get_by_id(proposal["draft_id"], client_id).approve()
        else:
            fixed_assets.run_depreciation(asset.id, period, run_seq=1)
    assert JournalEntry.count(client_id) == 1
    assert len(_runs(asset)) == 1
    assert _runs(asset)[0]["superseded_by"] is None
    assert JournalEntry.get_by_id(_runs(asset)[0]["journal_entry_id"]).reversed_by_journal_entry_id is None
    assert DraftEntry.get_by_id(proposal["draft_id"], client_id).status == "pending"


def test_invalid_sequences_and_duplicate_pending_proposals(client_id, fixed_accounts):
    asset = _asset(client_id, fixed_accounts)
    period = date(2026, 1, 31)
    for sequence in (-1, 1, True, 0.5):
        with pytest.raises(ValueError, match="sequence"):
            fixed_assets.run_depreciation(asset.id, period, run_seq=sequence)
    fixed_assets.propose_depreciation_run(asset.id, period)
    with pytest.raises(ValueError, match="pending"):
        fixed_assets.propose_depreciation_run(asset.id, period)
    fixed_assets.run_depreciation(asset.id, period)
    with pytest.raises(ValueError, match="sequence"):
        fixed_assets.run_depreciation(asset.id, period, run_seq=2)
    fixed_assets.run_depreciation(asset.id, date(2026, 2, 28))
    with pytest.raises(ValueError, match="chronological"):
        fixed_assets.run_depreciation(asset.id, period, run_seq=1)


@pytest.mark.parametrize("period_type", ["Year", "Month"])
def test_closed_period_refuses_post_proposal_approval_correction_and_disposal(
    client_id, fixed_accounts, period_type,
):
    asset = _asset(client_id, fixed_accounts)
    first = date(2026, 1, 31)
    fixed_assets.run_depreciation(asset.id, first)
    proposal = fixed_assets.propose_depreciation_run(asset.id, first, run_seq=1)
    FiscalPeriod(
        client_id=client_id, period_name="Closed oracle period", period_type=period_type,
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), is_closed=True,
    ).save()
    actions = [
        lambda: fixed_assets.run_depreciation(asset.id, date(2026, 2, 28)),
        lambda: fixed_assets.propose_depreciation_run(asset.id, date(2026, 2, 28)),
        lambda: fixed_assets.run_depreciation(asset.id, first, run_seq=1),
        lambda: DraftEntry.get_by_id(proposal["draft_id"], client_id).approve(),
        lambda: fixed_assets.dispose_asset(asset.id, date(2026, 2, 15), 1000,
                                           fixed_accounts["cash"], fixed_accounts["gain_loss"]),
    ]
    for action in actions:
        with pytest.raises(ValueError, match="closed"):
            action()
    assert JournalEntry.count(client_id) == 1
    assert _runs(asset)[0]["superseded_by"] is None


@pytest.mark.parametrize("proceeds,expected_gain,expected_loss", [
    # 10000 - 3000 = 7000 book value; 8000 - 7000 = 1000 gain.
    (8000, 1000, 0),
    # 5000 - 7000 = -2000: debit the disposal loss.
    (5000, 0, 2000),
])
def test_disposal_and_corrected_register_roll_forward_gl_oracle(
    client_id, fixed_accounts, proceeds, expected_gain, expected_loss,
):
    asset = _asset(client_id, fixed_accounts, cost=10000, salvage=1000)
    fixed_assets.run_depreciation(asset.id, date(2026, 1, 31))
    fixed_assets.run_depreciation(asset.id, date(2026, 1, 31), run_seq=1)
    register = fixed_assets.fixed_asset_register(client_id, date(2026, 1, 31))
    assert [(row["cost_cents"], row["accumulated_depreciation_cents"],
             row["book_value_cents"]) for row in register] == [(10000, 3000, 7000)]
    roll = fixed_assets.depreciation_roll_forward(
        client_id, date(2026, 1, 1), date(2026, 1, 31))[0]
    assert (roll["opening_cents"], roll["depreciation_cents"],
            roll["disposals_cents"], roll["closing_cents"]) == (0, 3000, 0, 3000)
    tie = fixed_assets.depreciation_gl_tie_out(client_id, date(2026, 1, 31))[0]
    assert (tie["subledger_cents"], tie["gl_cents"], tie["difference_cents"]) == (3000, 3000, 0)
    entry_id = fixed_assets.dispose_asset(asset.id, date(2026, 2, 15), proceeds,
                                          fixed_accounts["cash"], fixed_accounts["gain_loss"])
    entry = JournalEntry.get_by_id(entry_id, client_id)
    amounts = {line.account_id: (round(line.debit * 100), round(line.credit * 100))
               for line in entry.lines}
    assert amounts[fixed_accounts["asset"]] == (0, 10000)
    assert amounts[fixed_accounts["accum"]] == (3000, 0)
    assert amounts[fixed_accounts["cash"]] == (proceeds, 0)
    assert amounts[fixed_accounts["gain_loss"]] == (expected_loss, expected_gain)
    roll = fixed_assets.depreciation_roll_forward(
        client_id, date(2026, 2, 1), date(2026, 2, 28))[0]
    assert (roll["opening_cents"], roll["depreciation_cents"],
            roll["disposals_cents"], roll["closing_cents"]) == (3000, 0, 3000, 0)
    tie = fixed_assets.depreciation_gl_tie_out(client_id, date(2026, 2, 28))[0]
    assert (tie["subledger_cents"], tie["gl_cents"], tie["difference_cents"]) == (0, 0, 0)
    register = fixed_assets.fixed_asset_register(client_id, date(2026, 2, 28))[0]
    assert (register["cost_cents"], register["accumulated_depreciation_cents"],
            register["book_value_cents"]) == (0, 0, 0)
    post_entry(client_id, date(2026, 2, 28), [
        (fixed_accounts["depreciation"], 0.01, 0),
        (fixed_accounts["accum"], 0, 0.01),
    ])
    assert fixed_assets.depreciation_gl_tie_out(
        client_id, date(2026, 2, 28))[0]["difference_cents"] == -1


@pytest.mark.parametrize("driver", [sqlite3, _driver], ids=["sqlite", "book_driver"])
def test_910_migration_upgrades_populated_book(tmp_path, monkeypatch, driver):
    migration_dir = schema.MIGRATIONS_DIR
    legacy_dir = tmp_path / "legacy_migrations"
    legacy_dir.mkdir()
    for path in migration_dir.glob("*.sql"):
        if path.name < "910":
            (legacy_dir / path.name).write_bytes(path.read_bytes())
    with closing(driver.connect(tmp_path / "legacy.db")) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with monkeypatch.context() as legacy:
            legacy.setattr(schema, "MIGRATIONS_DIR", legacy_dir)
            schema.create_tables(conn)
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone() == (52,)
        assert conn.execute("SELECT version FROM schema_migrations "
                            "WHERE version = '909_counterparties'").fetchone() == ("909_counterparties",)
        conn.executescript("""
            INSERT INTO clients (id, name) VALUES (1, 'Legacy oracle');
            INSERT INTO accounts (id, client_id, account_number, name, type)
            VALUES (1, 1, '1500', 'Equipment', 'Asset');
            INSERT INTO fixed_asset_types
                (id, client_id, name, asset_account_id,
                 accumulated_depreciation_account_id, depreciation_expense_account_id,
                 method, effective_life_months)
            VALUES (1, 1, 'Equipment', 1, 1, 1, 'straight_line', 3);
            INSERT INTO fixed_assets
                (id, client_id, fixed_asset_type_id, description, acquisition_date,
                 cost_cents, in_service_date)
            VALUES (1, 1, 1, 'Machine', '2026-01-15', 10000, '2026-01-15');
            INSERT INTO journal_entries (id, client_id, entry_date)
            VALUES (1, 1, '2026-01-31');
            INSERT INTO depreciation_runs
                (id, fixed_asset_id, period_start, period_end, amount_cents, journal_entry_id)
            VALUES (1, 1, '2026-01-01', '2026-01-31', 3333, 1);
            INSERT INTO draft_entries
                (id, client_id, proposed_by, entry_date, description, lines_json)
            VALUES (1, 1, 'Assistant', '2026-02-28', 'Depreciation', '[]');
            INSERT INTO depreciation_draft_links VALUES
                (1, 1, '2026-02-28', 'straight_line', 3333);
            UPDATE sqlite_sequence SET seq = 40
            WHERE name IN ('fixed_asset_types', 'fixed_assets', 'depreciation_runs');
        """)
        original = conn.execute("SELECT * FROM depreciation_runs").fetchone()
        schema.create_tables(conn)
        schema.create_tables(conn)
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone() == (53,)
        assert conn.execute("SELECT version FROM schema_migrations "
                            "WHERE version = '910_fixed_asset_depreciation_corrections'").fetchone() == (
                                "910_fixed_asset_depreciation_corrections",)
        assert conn.execute("SELECT id, fixed_asset_id, period_start, period_end, "
                            "amount_cents, journal_entry_id, created_at "
                            "FROM depreciation_runs").fetchone() == original
        assert conn.execute("SELECT run_seq, superseded_by FROM depreciation_runs").fetchone() == (0, None)
        assert conn.execute("SELECT run_seq, units_produced FROM depreciation_draft_links").fetchone() == (0, None)
        assert conn.execute("SELECT convention FROM fixed_asset_types").fetchone() == ("full_month",)
        assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name IN "
                            "('fixed_asset_types', 'fixed_assets', 'depreciation_runs')").fetchall() == [(40,)] * 3
        assert conn.execute("SELECT name FROM pragma_index_info('uq_depreciation_runs_asset_period')").fetchall() == [
            ("fixed_asset_id",), ("period_end",), ("run_seq",)]
        conn.execute("INSERT INTO depreciation_runs "
                     "(fixed_asset_id, period_start, period_end, amount_cents, journal_entry_id, run_seq) "
                     "VALUES (1, '2026-01-01', '2026-01-31', 3333, 1, 1)")
        with pytest.raises(driver.IntegrityError):
            conn.execute("INSERT INTO depreciation_runs "
                         "(fixed_asset_id, period_start, period_end, amount_cents, journal_entry_id, run_seq) "
                         "VALUES (1, '2026-01-01', '2026-01-31', 3333, 1, 1)")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
