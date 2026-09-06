"""Conservative duplicate candidates for human review; no ledger writes."""

from database.connection import get_connection


def propose_duplicates(client_id: int, amount_tolerance_cents: int = 1,
                       date_window_days: int = 3) -> dict:
    for name, value, maximum in (
        ("amount_tolerance_cents", amount_tolerance_cents, 10000),
        ("date_window_days", date_window_days, 366),
    ):
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f"{name} must be an integer between 0 and {maximum}.")
    conn = get_connection()
    try:
        if not conn.execute("SELECT 1 FROM clients WHERE id = ?", (client_id,)).fetchone():
            raise ValueError("Client not found.")
        sources = {}
        reversed_entries = set()
        for row in conn.execute(
            "SELECT journal_entry_id, source_reference, reversed "
            "FROM journal_counterparty_sources WHERE client_id = ?", (client_id,),
        ):
            sources.setdefault(row["journal_entry_id"], set()).add(row["source_reference"])
            if row["reversed"]:
                reversed_entries.add(row["journal_entry_id"])
        proposals = {}
        rows = conn.execute(
            """
            SELECT a.id AS first_line_id, b.id AS second_line_id,
                   x.id AS first_entry_id, y.id AS second_entry_id,
                   a.counterparty_id, c.display_name,
                   a.debit - a.credit AS first_amount_cents,
                   b.debit - b.credit AS second_amount_cents,
                   x.entry_date AS first_date, y.entry_date AS second_date,
                   x.source_reference AS first_reference, y.source_reference AS second_reference
            FROM journal_entry_lines a
            JOIN journal_entries x ON x.id = a.journal_entry_id
            JOIN counterparties c ON c.id = a.counterparty_id AND c.client_id = x.client_id
            JOIN journal_entry_lines b
              ON b.counterparty_id = a.counterparty_id
             AND (b.debit - b.credit) BETWEEN (a.debit - a.credit) - ? AND (a.debit - a.credit) + ?
             AND b.account_id = a.account_id AND (b.debit > 0) = (a.debit > 0)
            JOIN journal_entries y ON y.id = b.journal_entry_id AND y.client_id = x.client_id
            WHERE x.client_id = ? AND x.id < y.id
              AND ABS(julianday(x.entry_date) - julianday(y.entry_date)) <= ?
              AND x.reverses_journal_entry_id IS NULL AND x.reversed_by_journal_entry_id IS NULL
              AND y.reverses_journal_entry_id IS NULL AND y.reversed_by_journal_entry_id IS NULL
            ORDER BY x.id, y.id, a.id, b.id
            """,
            (amount_tolerance_cents, amount_tolerance_cents, client_id, date_window_days),
        )
        for row in rows:
            first, second = row["first_entry_id"], row["second_entry_id"]
            if first in reversed_entries or second in reversed_entries:
                continue
            first_sources, second_sources = sources.get(first, set()), sources.get(second, set())
            # Separate source documents/payments establish separate occurrences,
            # even when their generated journal descriptions are identical.
            if first_sources and second_sources and first_sources != second_sources:
                continue
            first_ref = (row["first_reference"] or "").strip()
            second_ref = (row["second_reference"] or "").strip()
            if first_ref and second_ref and first_ref != second_ref:
                continue
            key = (first, second, row["counterparty_id"])
            if key not in proposals:
                proposals[key] = {
                    "status": "proposed",
                    "first_entry_id": first, "second_entry_id": second,
                    "counterparty_id": row["counterparty_id"],
                    "counterparty_name": row["display_name"],
                    "first_date": row["first_date"], "second_date": row["second_date"],
                    "reason": "Same counterparty and account, matching signed amount and nearby date.",
                    "matched_lines": [],
                }
            proposals[key]["matched_lines"].append({
                name: row[name] for name in (
                    "first_line_id", "second_line_id", "first_amount_cents", "second_amount_cents",
                )
            })
        return {
            "client_id": client_id,
            "amount_tolerance_cents": amount_tolerance_cents,
            "date_window_days": date_window_days,
            "proposals": list(proposals.values()),
            "note": "Review each proposal. Corrections to posted journals require a human reversal; no merge is available.",
        }
    finally:
        conn.close()
