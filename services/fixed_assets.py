import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from database.connection import get_connection, get_cursor
from models.fixed_asset import FixedAsset, FixedAssetType
from money import to_dollars


def _month_end(value: date) -> date:
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def depreciation_amount_cents(asset: FixedAsset, period_end: date) -> int:
    """Return one month's depreciation using a full-month convention.

    An asset receives a full month in its in-service month, with its first
    eligible date being that calendar month-end. Day-level proration is not
    used; callers must supply a calendar month-end.
    """
    if period_end != _month_end(period_end):
        raise ValueError("Depreciation period_end must be a calendar month-end.")
    if asset.status != "registered":
        raise ValueError("Disposed assets cannot be depreciated.")
    if period_end < _month_end(asset.in_service_date):
        raise ValueError("Depreciation cannot precede the in-service month.")
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT MAX(period_end) latest, COUNT(*) run_count "
            "FROM depreciation_runs "
            "WHERE fixed_asset_id = ?", (asset.id,))
        run_summary = cursor.fetchone()
        latest = run_summary["latest"]
    if latest and period_end <= date.fromisoformat(latest):
        raise ValueError("Depreciation periods must be run in chronological order.")
    remaining = asset.book_value_cents - asset.salvage_value_cents
    if remaining <= 0:
        raise ValueError("Asset is already at its salvage value.")
    asset_type = FixedAssetType.get_by_id(asset.fixed_asset_type_id, asset.client_id)
    if asset_type.method == "straight_line":
        if run_summary["run_count"] + 1 >= asset_type.effective_life_months:
            return remaining
        monthly = (Decimal(asset.cost_cents - asset.salvage_value_cents)
                   / Decimal(asset_type.effective_life_months))
    else:
        monthly = (Decimal(asset.book_value_cents) * Decimal(str(asset_type.annual_rate))
                   / Decimal(12))
    amount = int(monthly.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return min(max(amount, 1), remaining)


def run_depreciation(fixed_asset_id: int, period_end: date) -> int:
    from models.audit_log import AuditLog
    from models.journal_entry import JournalEntry, JournalEntryLine

    asset = FixedAsset.get_by_id(fixed_asset_id)
    if asset is None:
        raise ValueError("Fixed asset not found.")
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM depreciation_runs WHERE fixed_asset_id = ? AND period_end = ?",
            (fixed_asset_id, period_end.isoformat()),
        )
        if cursor.fetchone():
            raise ValueError("Depreciation has already been run for this asset and period.")
    amount_cents = depreciation_amount_cents(asset, period_end)
    asset_type = FixedAssetType.get_by_id(asset.fixed_asset_type_id, asset.client_id)
    entry = JournalEntry(
        client_id=asset.client_id,
        entry_date=period_end,
        description=f"Depreciation — {asset.description}",
        entry_type="Adjusting",
        source_reference=f"Fixed asset #{asset.id} depreciation",
        lines=[
            JournalEntryLine(
                account_id=asset_type.depreciation_expense_account_id,
                debit=to_dollars(amount_cents),
            ),
            JournalEntryLine(
                account_id=asset_type.accumulated_depreciation_account_id,
                credit=to_dollars(amount_cents),
            ),
        ],
    )
    conn = get_connection()
    cursor = conn.cursor()
    try:
        entry_id = entry.save(conn=conn)
        cursor.execute(
            """INSERT INTO depreciation_runs
               (fixed_asset_id, period_start, period_end, amount_cents,
                journal_entry_id) VALUES (?, ?, ?, ?, ?)""",
            (asset.id, period_end.replace(day=1).isoformat(), period_end.isoformat(),
             amount_cents, entry_id),
        )
        run_id = cursor.lastrowid
        AuditLog.write(
            cursor, asset.client_id, "depreciation_runs", run_id, "INSERT",
            new_values={"fixed_asset_id": asset.id,
                        "period_start": period_end.replace(day=1),
                        "period_end": period_end, "amount_cents": amount_cents,
                        "journal_entry_id": entry_id},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return run_id


def dispose_asset(fixed_asset_id: int, disposal_date: date, proceeds_cents: int,
                  deposit_account_id: int, gain_loss_account_id: int) -> int:
    from models.account import Account
    from models.audit_log import AuditLog
    from models.journal_entry import JournalEntry, JournalEntryLine

    asset = FixedAsset.get_by_id(fixed_asset_id)
    if asset is None:
        raise ValueError("Fixed asset not found.")
    if asset.status == "disposed":
        raise ValueError("Asset has already been disposed.")
    if disposal_date < asset.in_service_date:
        raise ValueError("Disposal date cannot precede the in-service date.")
    if proceeds_cents < 0:
        raise ValueError("Disposal proceeds cannot be negative.")
    if (Account.get_by_id(deposit_account_id, asset.client_id) is None
            or Account.get_by_id(gain_loss_account_id, asset.client_id) is None):
        raise ValueError("Disposal accounts must belong to the asset's client.")
    asset_type = FixedAssetType.get_by_id(asset.fixed_asset_type_id, asset.client_id)
    accumulated = asset.accumulated_depreciation_cents
    book_value = asset.cost_cents - accumulated
    gain_loss = proceeds_cents - book_value
    lines = [
        JournalEntryLine(account_id=asset_type.asset_account_id,
                         credit=to_dollars(asset.cost_cents)),
    ]
    if accumulated:
        lines.append(JournalEntryLine(
            account_id=asset_type.accumulated_depreciation_account_id,
            debit=to_dollars(accumulated),
        ))
    if proceeds_cents:
        lines.append(JournalEntryLine(
            account_id=deposit_account_id, debit=to_dollars(proceeds_cents)))
    if gain_loss > 0:
        lines.append(JournalEntryLine(
            account_id=gain_loss_account_id, credit=to_dollars(gain_loss)))
    elif gain_loss < 0:
        lines.append(JournalEntryLine(
            account_id=gain_loss_account_id, debit=to_dollars(-gain_loss)))

    entry = JournalEntry(
        client_id=asset.client_id,
        entry_date=disposal_date,
        description=f"Disposal — {asset.description}",
        entry_type="Adjusting",
        source_reference=f"Fixed asset #{asset.id} disposal",
        lines=lines,
    )
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE fixed_assets
               SET status = 'disposed', disposal_date = ?,
                   disposal_proceeds_cents = ?
               WHERE id = ? AND client_id = ? AND status = 'registered'""",
            (disposal_date.isoformat(), proceeds_cents, asset.id, asset.client_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Asset has already been disposed.")
        entry_id = entry.save(conn=conn)
        AuditLog.write(
            cursor, asset.client_id, "fixed_assets", asset.id, "UPDATE",
            old_values={"status": "registered", "disposal_date": None,
                        "disposal_proceeds_cents": None},
            new_values={"status": "disposed", "disposal_date": disposal_date,
                        "disposal_proceeds_cents": proceeds_cents,
                        "journal_entry_id": entry_id},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return entry_id


def propose_depreciation_run(fixed_asset_id: int, period_end: date,
                             rationale: str = "") -> dict:
    """Create a normal draft entry; approval remains a human ledger action."""
    from models.account import Account
    from models.draft_entry import DraftEntry, DraftLine

    asset = FixedAsset.get_by_id(fixed_asset_id)
    if asset is None:
        raise ValueError("Fixed asset not found.")
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM depreciation_runs WHERE fixed_asset_id = ? AND period_end = ?",
            (fixed_asset_id, period_end.isoformat()),
        )
        if cursor.fetchone():
            raise ValueError("Depreciation has already been run for this asset and period.")
    amount_cents = depreciation_amount_cents(asset, period_end)
    asset_type = FixedAssetType.get_by_id(asset.fixed_asset_type_id, asset.client_id)
    expense = Account.get_by_id(asset_type.depreciation_expense_account_id,
                                asset.client_id)
    accumulated = Account.get_by_id(
        asset_type.accumulated_depreciation_account_id, asset.client_id)
    draft = DraftEntry(
        client_id=asset.client_id,
        proposed_by="Assistant (MCP)",
        entry_date=period_end.isoformat(),
        entry_type="Adjusting",
        description=f"Proposed depreciation — {asset.description}",
        rationale=rationale or f"One month of {asset_type.method} depreciation.",
        lines=[
            DraftLine(account_number=expense.account_number,
                      debit_cents=amount_cents),
            DraftLine(account_number=accumulated.account_number,
                      credit_cents=amount_cents),
        ],
    )
    conn = get_connection()
    cursor = conn.cursor()
    try:
        draft_id = draft.save(conn=conn)
        cursor.execute(
            """INSERT INTO depreciation_draft_links
               (draft_entry_id, fixed_asset_id, period_end, method, amount_cents)
               VALUES (?, ?, ?, ?, ?)""",
            (draft_id, asset.id, period_end.isoformat(), asset_type.method,
             amount_cents),
        )
        from models.audit_log import AuditLog
        AuditLog.write(
            cursor, asset.client_id, "depreciation_draft_links", draft_id, "INSERT",
            new_values={"draft_entry_id": draft_id, "fixed_asset_id": asset.id,
                        "period_end": period_end, "method": asset_type.method,
                        "amount_cents": amount_cents},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"draft_id": draft_id, "status": "pending",
            "amount_cents": amount_cents,
            "note": "Filed for human review; this proposal did not post."}
