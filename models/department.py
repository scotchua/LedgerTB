from dataclasses import dataclass
from typing import List, Optional

from database.connection import get_connection, get_cursor
from models.audit_log import AuditLog


@dataclass
class Department:
    id: Optional[int] = None
    client_id: int = 0
    name: str = ""

    @staticmethod
    def _from_row(row):
        return Department(id=row["id"], client_id=row["client_id"], name=row["name"])

    @staticmethod
    def get_all(client_id: int) -> List["Department"]:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM departments WHERE client_id = ? ORDER BY name",
                (client_id,),
            )
            rows = cursor.fetchall()
        return [Department._from_row(row) for row in rows]

    def save(self) -> int:
        name = self.name.strip()
        if not name:
            raise ValueError("Department name is required.")
        if self.id is not None:
            raise ValueError("Departments cannot be edited in place.")

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO departments (client_id, name) VALUES (?, ?)",
                (self.client_id, name),
            )
            self.id = cursor.lastrowid
            AuditLog.write(
                cursor, self.client_id, "departments", self.id, "INSERT",
                new_values={"name": name},
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        self.name = name
        return self.id
