import uuid
from dataclasses import dataclass
from typing import Literal, Optional

from database.connection import get_connection
from models.audit_log import AuditLog
from utils.actor import current_actor


CodingState = Literal["unreviewed", "human_coded", "human_cleared", "assistant", "stale"]


@dataclass(frozen=True)
class Coding:
    state: CodingState
    account_id: Optional[int] = None
    suggestion_id: Optional[int] = None
    confidence: Optional[str] = None
    reason: str = ""
    source: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None


def effective_coding(client_id: int, cursor=None) -> dict[int, Coding]:
    owns_connection = cursor is None
    conn = get_connection() if owns_connection else None
    cursor = conn.cursor() if owns_connection else cursor
    try:
        cursor.execute(
            """
            WITH newest AS (
                SELECT s.*, ROW_NUMBER() OVER (
                    PARTITION BY s.imported_transaction_id
                    ORDER BY s.created_at DESC, s.id DESC
                ) AS ordinal
                FROM import_suggestions s
            )
            SELECT it.id, it.decided_account_id, it.decided_at, it.decided_by,
                   it.decided_suggestion_id, n.id suggestion_id,
                   n.suggested_account_id, n.confidence, n.reason, n.source,
                   a.is_active, a.type account_type
            FROM imported_transactions it
            LEFT JOIN newest n ON n.imported_transaction_id = it.id AND n.ordinal = 1
            LEFT JOIN accounts a ON a.id = n.suggested_account_id
            WHERE it.client_id = ? AND it.status = 'Pending'
            """,
            (client_id,),
        )
        result = {}
        for row in cursor.fetchall():
            common = dict(decided_by=row["decided_by"], decided_at=row["decided_at"])
            if row["decided_at"] is not None:
                state = "human_coded" if row["decided_account_id"] is not None else "human_cleared"
                result[row["id"]] = Coding(
                    state, row["decided_account_id"], row["decided_suggestion_id"], **common
                )
            elif row["suggestion_id"] is None:
                result[row["id"]] = Coding("unreviewed")
            elif row["is_active"] and row["account_type"] in ("Revenue", "Expense"):
                result[row["id"]] = Coding(
                    "assistant", row["suggested_account_id"], row["suggestion_id"],
                    row["confidence"], row["reason"], row["source"],
                )
            else:
                result[row["id"]] = Coding(
                    "stale", suggestion_id=row["suggestion_id"],
                    confidence=row["confidence"], reason=row["reason"], source=row["source"],
                )
        return result
    finally:
        if conn is not None:
            conn.close()


def record_decision(transaction_id: int, client_id: int,
                    account_id: Optional[int], suggestion_id: Optional[int], cursor,
                    operation_id: Optional[str] = None) -> None:
    cursor.execute(
        "SELECT decided_account_id, decided_at, decided_by, decided_suggestion_id "
        "FROM imported_transactions WHERE id = ? AND client_id = ? AND status = 'Pending'",
        (transaction_id, client_id),
    )
    old = cursor.fetchone()
    if old is None:
        raise ValueError("Pending imported transaction not found for the selected client.")
    if suggestion_id is not None:
        suggestion = cursor.execute(
            "SELECT id FROM import_suggestions "
            "WHERE id = ? AND imported_transaction_id = ?",
            (suggestion_id, transaction_id),
        ).fetchone()
        if suggestion is None:
            raise ValueError("Suggestion does not belong to the selected transaction.")
    if account_id is not None:
        account = cursor.execute(
            "SELECT id FROM accounts WHERE id = ? AND client_id = ? AND is_active = 1",
            (account_id, client_id),
        ).fetchone()
        if account is None:
            raise ValueError("Choose an active account for the selected client.")
    decided_by = current_actor()
    cursor.execute(
        """
        UPDATE imported_transactions
        SET decided_account_id = ?, decided_at = datetime('now', 'localtime'),
            decided_by = ?, decided_suggestion_id = ?
        WHERE id = ? AND client_id = ? AND status = 'Pending'
        """,
        (account_id, decided_by, suggestion_id, transaction_id, client_id),
    )
    new = cursor.execute(
        "SELECT decided_account_id, decided_at, decided_by, decided_suggestion_id "
        "FROM imported_transactions WHERE id = ?", (transaction_id,),
    ).fetchone()
    new_values = dict(new)
    if operation_id:
        new_values["operation_id"] = operation_id
    AuditLog.write(
        cursor, client_id, "imported_transactions", transaction_id, "UPDATE",
        old_values=dict(old), new_values=new_values,
    )


def record_decisions(decisions: list, client_id: int, cursor=None) -> str:
    owns_connection = cursor is None
    conn = get_connection() if owns_connection else None
    cursor = conn.cursor() if owns_connection else cursor
    operation_id = uuid.uuid4().hex
    try:
        if owns_connection:
            cursor.execute("BEGIN IMMEDIATE")
        for decision in decisions:
            record_decision(
                decision["transaction_id"], client_id, decision.get("account_id"),
                decision.get("suggestion_id"), cursor, operation_id,
            )
        if owns_connection:
            conn.commit()
        return operation_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()
