from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from utils.actor import current_actor


@dataclass
class ImportSuggestion:
    id: Optional[int] = None
    imported_transaction_id: int = 0
    suggested_account_id: int = 0
    confidence: str = ""
    reason: str = ""
    source: str = ""
    request_id: str = ""
    created_at: Optional[str] = None
    created_by: Optional[str] = None

    @staticmethod
    def insert(cursor, imported_transaction_id: int, suggested_account_id: int,
               confidence: str, reason: str, source: str, request_id: str,
               created_by: Optional[str] = None) -> int:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            INSERT INTO import_suggestions
                (imported_transaction_id, suggested_account_id, confidence,
                 reason, source, request_id, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (imported_transaction_id, suggested_account_id, confidence, reason,
             source, request_id, created_at, created_by or current_actor()),
        )
        return cursor.lastrowid
