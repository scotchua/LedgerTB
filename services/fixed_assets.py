import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from database.connection import get_connection, get_cursor
from models.fixed_asset import FixedAsset, FixedAssetType
from money import to_dollars


def _month_end(value: date) -> date:
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def _require_open_period(conn, client_id: int, value: date) -> None:
    closed = conn.execute(
        "SELECT period_name FROM fiscal_periods WHERE client_id = ? "
        "AND is_closed = 1 AND start_date <= ? AND end_date >= ? LIMIT 1",
        (client_id, value.isoformat(), value.isoformat()),
    ).fetchone()
    if closed:
        raise ValueError(
            f"{closed['period_name']} is closed. Reopen it before posting depreciation or disposal."
        )


def _prior_run(conn, fixed_asset_id: int, period_end: date, run_seq: int):
    if type(run_seq) is not int or run_seq < 0:
        raise ValueError("Depreciation run sequence must be a nonnegative integer.")
    prior = conn.execute(
        "SELECT * FROM depreciation_runs WHERE fixed_asset_id = ? AND period_end = ? "
        "ORDER BY run_seq DESC LIMIT 1", (fixed_asset_id, period_end.isoformat()),
    ).fetchone()
    if prior and run_seq <= prior["run_seq"]:
        raise ValueError("Depreciation has already been run for this asset, period and sequence.")
    expected = prior["run_seq"] + 1 if prior else 0
    if run_seq != expected or (prior and prior["superseded_by"] is not None):
        raise ValueError(f"Depreciation run sequence must be {expected}.")
    return prior


def _depreciation_amount_cents(conn, fixed_asset_id: int, period_end: date,
                               run_seq: int = 0, units_produced=None) -> int:
    """Calculate from effective runs, excluding the run being corrected."""
    asset_row = conn.execute(
        "SELECT * FROM fixed_assets WHERE id = ?", (fixed_asset_id,),
    ).fetchone()
    if not asset_row:
        raise ValueError("Fixed asset not found.")
    asset = FixedAsset._from_row(asset_row)
    if period_end != _month_end(period_end):
        raise ValueError("Depreciation period_end must be a calendar month-end.")
    if asset.status != "registered":
        raise ValueError("Disposed assets cannot be depreciated.")
    if period_end < _month_end(asset.in_service_date):
        raise ValueError("Depreciation cannot precede the in-service month.")
    _require_open_period(conn, asset.client_id, period_end)
    prior = _prior_run(conn, asset.id, period_end, run_seq)
    run_summary = conn.execute(
        "SELECT MAX(period_end) latest, COUNT(*) run_count, "
        "COALESCE(SUM(amount_cents), 0) accumulated_cents, "
        "COALESCE(SUM(units_produced), 0) produced_units "
        "FROM depreciation_runs WHERE fixed_asset_id = ? AND superseded_by IS NULL "
        "AND id != ?", (asset.id, prior["id"] if prior else -1),
    ).fetchone()
    latest = run_summary["latest"]
    if latest and period_end <= date.fromisoformat(latest):
        raise ValueError(
            "Depreciation periods must be run in chronological order; "
            "only the latest period can be corrected."
        )
    remaining = (asset.cost_cents - int(run_summary["accumulated_cents"])
                 - asset.salvage_value_cents)
    if remaining <= 0:
        raise ValueError("Asset is already at its salvage value.")
    type_row = conn.execute(
        "SELECT * FROM fixed_asset_types WHERE id = ? AND client_id = ?",
        (asset.fixed_asset_type_id, asset.client_id),
    ).fetchone()
    if not type_row:
        raise ValueError("Fixed asset type not found.")
    asset_type = FixedAssetType._from_row(type_row)
    asset_type.validate()
    if asset_type.method == "units_of_production":
        if type(units_produced) is not int or units_produced <= 0:
            raise ValueError("Units produced must be a positive integer.")
        remaining_units = asset_type.total_units - int(run_summary["produced_units"])
        if units_produced > remaining_units:
            raise ValueError("Units produced exceed remaining lifetime units.")
        if units_produced == remaining_units:
            return remaining
        monthly = (Decimal(asset.cost_cents - asset.salvage_value_cents)
                   * Decimal(units_produced) / Decimal(asset_type.total_units))
    else:
        if units_produced is not None:
            raise ValueError("Only units-of-production runs can record units produced.")
        age = ((period_end.year - asset.in_service_date.year) * 12
               + period_end.month - asset.in_service_date.month)
        weight = Decimal(1)
        terminal = False
        if asset_type.convention != "full_month":
            if age != run_summary["run_count"]:
                raise ValueError(
                    "This convention requires consecutive depreciation months "
                    "from the in-service month."
                )
            if asset_type.convention == "mid_month":
                if age == 0:
                    weight = Decimal("0.5")
                if asset_type.method == "straight_line":
                    terminal = age >= asset_type.effective_life_months
            else:
                if period_end.year == asset.in_service_date.year:
                    weight = Decimal(6) / Decimal(13 - asset.in_service_date.month)
                if asset_type.method == "straight_line":
                    last_year = (asset.in_service_date.year
                                 + asset_type.effective_life_months // 12)
                    if period_end.year == last_year:
                        weight = Decimal("0.5")
                    terminal = period_end >= date(last_year, 12, 31)
        elif asset_type.method == "straight_line":
            terminal = run_summary["run_count"] + 1 >= asset_type.effective_life_months
        if asset_type.method == "straight_line":
            if terminal:
                return remaining
            monthly = (Decimal(asset.cost_cents - asset.salvage_value_cents)
                       / Decimal(asset_type.effective_life_months) * weight)
        else:
            book_value_cents = asset.cost_cents - int(run_summary["accumulated_cents"])
            monthly = (Decimal(book_value_cents) * Decimal(str(asset_type.annual_rate))
                       / Decimal(12) * weight)
    amount = int(monthly.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return min(max(amount, 1), remaining)


def depreciation_amount_cents(asset: FixedAsset, period_end: date, conn=None,
                               run_seq: int = 0, units_produced=None) -> int:
    """Return the next depreciation amount from current persisted state."""
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        return _depreciation_amount_cents(conn, asset.id, period_end, run_seq, units_produced)
    finally:
        if owns_connection:
            conn.close()


def _post_depreciation_run(conn, fixed_asset_id: int, period_end: date,
                           amount_cents: int, entry, run_seq: int = 0,
                           units_produced=None):
    """Post a replacement and link its predecessor in the caller's transaction."""
    from models.audit_log import AuditLog
    from models.journal_entry import JournalEntry

    prior = _prior_run(conn, fixed_asset_id, period_end, run_seq)
    if prior:
        JournalEntry.reverse(
            prior["journal_entry_id"], entry.client_id,
            memo=f"Depreciation correction, sequence {run_seq}", conn=conn,
            _depreciation_run_id=prior["id"],
        )
    entry_id = entry.save(conn=conn)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO depreciation_runs
           (fixed_asset_id, period_start, period_end, amount_cents,
            journal_entry_id, run_seq, units_produced) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (fixed_asset_id, period_end.replace(day=1).isoformat(), period_end.isoformat(),
         amount_cents, entry_id, run_seq, units_produced),
    )
    run_id = cursor.lastrowid
    AuditLog.write(
        cursor, entry.client_id, "depreciation_runs", run_id, "INSERT",
        new_values={"fixed_asset_id": fixed_asset_id,
                    "period_start": period_end.replace(day=1),
                    "period_end": period_end, "amount_cents": amount_cents,
                    "journal_entry_id": entry_id, "run_seq": run_seq,
                    "units_produced": units_produced},
    )
    if prior:
        cursor.execute(
            "UPDATE depreciation_runs SET superseded_by = ? "
            "WHERE id = ? AND superseded_by IS NULL", (run_id, prior["id"]),
        )
        if cursor.rowcount != 1:
            raise ValueError("Depreciation run was already superseded.")
        AuditLog.write(
            cursor, entry.client_id, "depreciation_runs", prior["id"], "UPDATE",
            old_values={"superseded_by": None}, new_values={"superseded_by": run_id},
        )
    return run_id, entry_id


def run_depreciation(fixed_asset_id: int, period_end: date, run_seq: int = 0,
                     units_produced=None) -> int:
    from models.journal_entry import JournalEntry, JournalEntryLine

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        amount_cents = _depreciation_amount_cents(
            conn, fixed_asset_id, period_end, run_seq, units_produced,
        )
        asset = FixedAsset._from_row(conn.execute(
            "SELECT * FROM fixed_assets WHERE id = ?", (fixed_asset_id,),
        ).fetchone())
        asset_type = FixedAssetType._from_row(conn.execute(
            "SELECT * FROM fixed_asset_types WHERE id = ? AND client_id = ?",
            (asset.fixed_asset_type_id, asset.client_id),
        ).fetchone())
        entry = JournalEntry(
            client_id=asset.client_id,
            entry_date=period_end,
            description=f"Depreciation — {asset.description}",
            entry_type="Adjusting",
            source_reference=f"Fixed asset #{asset.id} depreciation, sequence {run_seq}",
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
        run_id, _ = _post_depreciation_run(
            conn, asset.id, period_end, amount_cents, entry, run_seq, units_produced,
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
    from models.audit_log import AuditLog
    from models.journal_entry import JournalEntry, JournalEntryLine

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fixed_assets WHERE id = ?", (fixed_asset_id,))
        asset_row = cursor.fetchone()
        if not asset_row:
            raise ValueError("Fixed asset not found.")
        asset = FixedAsset._from_row(asset_row)
        _require_open_period(conn, asset.client_id, disposal_date)
        if asset.status == "disposed":
            raise ValueError("Asset has already been disposed.")
        if disposal_date < asset.in_service_date:
            raise ValueError("Disposal date cannot precede the in-service date.")
        if proceeds_cents < 0:
            raise ValueError("Disposal proceeds cannot be negative.")
        cursor.execute(
            "SELECT COUNT(DISTINCT id) account_count FROM accounts "
            "WHERE client_id = ? AND id IN (?, ?)",
            (asset.client_id, deposit_account_id, gain_loss_account_id),
        )
        expected_accounts = 1 if deposit_account_id == gain_loss_account_id else 2
        if cursor.fetchone()["account_count"] != expected_accounts:
            raise ValueError("Disposal accounts must belong to the asset's client.")
        cursor.execute(
            "SELECT * FROM fixed_asset_types WHERE id = ? AND client_id = ?",
            (asset.fixed_asset_type_id, asset.client_id),
        )
        type_row = cursor.fetchone()
        if not type_row:
            raise ValueError("Fixed asset type not found.")
        asset_type = FixedAssetType._from_row(type_row)
        cursor.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) accumulated_cents "
            "FROM depreciation_runs WHERE fixed_asset_id = ? AND period_end <= ? "
            "AND superseded_by IS NULL",
            (asset.id, disposal_date.isoformat()),
        )
        accumulated = int(cursor.fetchone()["accumulated_cents"])
        cursor.execute(
            "SELECT 1 FROM depreciation_runs WHERE fixed_asset_id = ? AND period_end > ? "
            "AND superseded_by IS NULL LIMIT 1",
            (asset.id, disposal_date.isoformat()),
        )
        if cursor.fetchone():
            raise ValueError("Disposal date cannot precede an existing depreciation run.")
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
                             rationale: str = "", run_seq: int = 0,
                             units_produced=None) -> dict:
    """Create a normal draft entry; approval remains a human ledger action."""
    from models.account import Account
    from models.audit_log import AuditLog
    from models.draft_entry import DraftEntry, DraftLine

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        amount_cents = _depreciation_amount_cents(
            conn, fixed_asset_id, period_end, run_seq, units_produced,
        )
        pending = conn.execute(
            "SELECT 1 FROM depreciation_draft_links ddl "
            "JOIN draft_entries de ON de.id = ddl.draft_entry_id "
            "WHERE ddl.fixed_asset_id = ? AND ddl.period_end = ? AND ddl.run_seq = ? "
            "AND de.status = 'pending' LIMIT 1",
            (fixed_asset_id, period_end.isoformat(), run_seq),
        ).fetchone()
        if pending:
            raise ValueError(
                "A depreciation proposal is already pending for this asset, period and sequence."
            )
        asset = FixedAsset._from_row(conn.execute(
            "SELECT * FROM fixed_assets WHERE id = ?", (fixed_asset_id,),
        ).fetchone())
        asset_type = FixedAssetType._from_row(conn.execute(
            "SELECT * FROM fixed_asset_types WHERE id = ? AND client_id = ?",
            (asset.fixed_asset_type_id, asset.client_id),
        ).fetchone())
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
            rationale=rationale or f"One month of {asset_type.method} depreciation, sequence {run_seq}.",
            lines=[
                DraftLine(account_number=expense.account_number,
                          debit_cents=amount_cents),
                DraftLine(account_number=accumulated.account_number,
                          credit_cents=amount_cents),
            ],
        )
        draft_id = draft.save(conn=conn)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO depreciation_draft_links
               (draft_entry_id, fixed_asset_id, period_end, method, amount_cents,
                run_seq, units_produced) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (draft_id, asset.id, period_end.isoformat(), asset_type.method,
             amount_cents, run_seq, units_produced),
        )
        AuditLog.write(
            cursor, asset.client_id, "depreciation_draft_links", draft_id, "INSERT",
            new_values={"draft_entry_id": draft_id, "fixed_asset_id": asset.id,
                        "period_end": period_end, "method": asset_type.method,
                        "amount_cents": amount_cents, "run_seq": run_seq,
                        "units_produced": units_produced},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"draft_id": draft_id, "status": "pending",
            "amount_cents": amount_cents, "run_seq": run_seq,
            "note": "Filed for human review; this proposal did not post."}


def _register_rows(conn, client_id: int, as_of: date) -> list:
    rows = conn.execute(
        """SELECT fa.*, fat.accumulated_depreciation_account_id,
                  COALESCE(SUM(dr.amount_cents), 0) accumulated_cents
           FROM fixed_assets fa
           JOIN fixed_asset_types fat ON fat.id = fa.fixed_asset_type_id
           LEFT JOIN depreciation_runs dr ON dr.fixed_asset_id = fa.id
             AND dr.superseded_by IS NULL AND dr.period_end <= ?
           WHERE fa.client_id = ? AND fa.acquisition_date <= ?
           GROUP BY fa.id ORDER BY fa.description, fa.id""",
        (as_of.isoformat(), client_id, as_of.isoformat()),
    ).fetchall()
    result = []
    for row in rows:
        disposed = row["disposal_date"] and row["disposal_date"] <= as_of.isoformat()
        cost = 0 if disposed else row["cost_cents"]
        accumulated = 0 if disposed else int(row["accumulated_cents"])
        result.append({
            "fixed_asset_id": row["id"], "description": row["description"],
            "fixed_asset_type_id": row["fixed_asset_type_id"],
            "accumulated_depreciation_account_id": row["accumulated_depreciation_account_id"],
            "cost_cents": cost, "accumulated_depreciation_cents": accumulated,
            "book_value_cents": cost - accumulated,
            "status": "disposed" if disposed else "registered",
        })
    return result


def fixed_asset_register(client_id: int, as_of: date) -> list:
    """Return carrying balances as of a date, restating corrected runs."""
    with get_cursor() as cursor:
        return _register_rows(cursor.connection, client_id, as_of)


def depreciation_roll_forward(client_id: int, start_date: date, end_date: date) -> list:
    """Opening accumulated depreciation + charges - disposals = closing."""
    if start_date > end_date:
        raise ValueError("Roll-forward start date cannot follow its end date.")
    with get_cursor() as cursor:
        cursor.execute(
            """SELECT fat.accumulated_depreciation_account_id account_id,
                      COALESCE(SUM(CASE WHEN dr.period_end < :start
                        AND (fa.disposal_date IS NULL OR fa.disposal_date >= :start)
                        THEN dr.amount_cents ELSE 0 END), 0) opening_cents,
                      COALESCE(SUM(CASE WHEN dr.period_end >= :start
                        THEN dr.amount_cents ELSE 0 END), 0) depreciation_cents,
                      COALESCE(SUM(CASE WHEN fa.disposal_date BETWEEN :start AND :end
                        THEN dr.amount_cents ELSE 0 END), 0) disposals_cents
               FROM fixed_asset_types fat
               LEFT JOIN fixed_assets fa ON fa.fixed_asset_type_id = fat.id
               LEFT JOIN depreciation_runs dr ON dr.fixed_asset_id = fa.id
                 AND dr.superseded_by IS NULL AND dr.period_end <= :end
               WHERE fat.client_id = :client_id
               GROUP BY fat.accumulated_depreciation_account_id ORDER BY account_id""",
            {"client_id": client_id, "start": start_date.isoformat(),
             "end": end_date.isoformat()},
        )
        result = [dict(row) for row in cursor.fetchall()]
    for row in result:
        row["closing_cents"] = (row["opening_cents"] + row["depreciation_cents"]
                                - row["disposals_cents"])
    return result


def depreciation_gl_tie_out(client_id: int, as_of: date) -> list:
    """Compare effective register balances with actual GL credits minus debits."""
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        register = _register_rows(conn, client_id, as_of)
        rows = conn.execute(
            """SELECT a.id account_id, COALESCE(SUM(jel.credit - jel.debit), 0) gl_cents
               FROM accounts a
               LEFT JOIN journal_entry_lines jel ON jel.account_id = a.id
                 AND jel.journal_entry_id IN (
                   SELECT id FROM journal_entries WHERE client_id = ? AND entry_date <= ?)
               WHERE a.client_id = ? AND a.id IN (
                 SELECT accumulated_depreciation_account_id FROM fixed_asset_types
                 WHERE client_id = ?)
               GROUP BY a.id ORDER BY a.id""",
            (client_id, as_of.isoformat(), client_id, client_id),
        ).fetchall()
        balances = {}
        for asset in register:
            account_id = asset["accumulated_depreciation_account_id"]
            balances[account_id] = (balances.get(account_id, 0)
                                    + asset["accumulated_depreciation_cents"])
        return [{"account_id": row["account_id"],
                 "subledger_cents": balances.get(row["account_id"], 0),
                 "gl_cents": int(row["gl_cents"]),
                 "difference_cents": balances.get(row["account_id"], 0) - int(row["gl_cents"])}
                for row in rows]
    finally:
        conn.close()
