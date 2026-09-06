"""Typed counterparty identities for source-backed journal lines."""


def counterparty_for_source(cursor, client_id: int, kind: str, source_id: int) -> int:
    table = {"customer": "customers", "vendor": "vendors"}.get(kind)
    if table is None:
        raise ValueError("AR/AP counterparties must be customers or vendors.")
    cursor.execute(
        f"SELECT name FROM {table} WHERE id = ? AND client_id = ?",
        (source_id, client_id),
    )
    source = cursor.fetchone()
    if source is None:
        raise ValueError("Counterparty source must belong to the selected client.")
    cursor.execute(
        "INSERT INTO counterparties (client_id, kind, display_name, source_id) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(kind, source_id) DO NOTHING",
        (client_id, kind, source["name"], source_id),
    )
    cursor.execute(
        "SELECT id FROM counterparties WHERE client_id = ? AND kind = ? AND source_id = ?",
        (client_id, kind, source_id),
    )
    return cursor.fetchone()["id"]


def attribute_lines(cursor, client_id: int, kind: str, source_id: int, lines) -> None:
    counterparty_id = counterparty_for_source(cursor, client_id, kind, source_id)
    for line in lines:
        line.counterparty_id = counterparty_id
