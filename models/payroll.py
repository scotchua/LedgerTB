import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from database.connection import get_connection, get_cursor
from models.audit_log import AuditLog


@dataclass
class Employee:
    id: Optional[int] = None
    client_id: int = 0
    name: str = ""
    start_date: Optional[date] = None
    status: str = "active"
    created_at: Optional[datetime] = None

    @staticmethod
    def _from_row(row):
        return Employee(
            id=row["id"], client_id=row["client_id"], name=row["name"],
            start_date=date.fromisoformat(row["start_date"]), status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def get_all(client_id: int, active_only: bool = False) -> List["Employee"]:
        with get_cursor() as cursor:
            query = "SELECT * FROM employees WHERE client_id = ?"
            params = [client_id]
            if active_only:
                query += " AND status = 'active'"
            cursor.execute(query + " ORDER BY name", params)
            rows = cursor.fetchall()
        return [Employee._from_row(row) for row in rows]

    def save(self) -> int:
        if not self.name.strip():
            raise ValueError("Employee name is required.")
        if not self.start_date:
            raise ValueError("Employee start date is required.")
        if self.status not in ("active", "terminated"):
            raise ValueError("Employee status must be active or terminated.")

        conn = get_connection()
        try:
            cursor = conn.cursor()
            if self.id is None:
                cursor.execute(
                    "INSERT INTO employees (client_id, name, start_date, status) "
                    "VALUES (?, ?, ?, ?)",
                    (self.client_id, self.name.strip(), self.start_date.isoformat(), self.status),
                )
                self.id = cursor.lastrowid
                action = "INSERT"
                old_values = None
            else:
                cursor.execute(
                    "SELECT * FROM employees WHERE id = ? AND client_id = ?",
                    (self.id, self.client_id),
                )
                old = cursor.fetchone()
                if not old:
                    raise ValueError("Employee not found for the selected client.")
                old_values = {
                    "name": old["name"], "start_date": old["start_date"],
                    "status": old["status"],
                }
                cursor.execute(
                    "UPDATE employees SET name = ?, start_date = ?, status = ? "
                    "WHERE id = ? AND client_id = ?",
                    (self.name.strip(), self.start_date.isoformat(), self.status,
                     self.id, self.client_id),
                )
                action = "UPDATE"
            AuditLog.write(
                cursor, self.client_id, "employees", self.id, action,
                old_values=old_values,
                new_values={"name": self.name.strip(),
                            "start_date": self.start_date.isoformat(),
                            "status": self.status},
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.id

    def deactivate(self) -> None:
        self.status = "terminated"
        self.save()


@dataclass
class PayRun:
    id: Optional[int] = None
    client_id: int = 0
    pay_period_start: Optional[date] = None
    pay_period_end: Optional[date] = None
    pay_date: Optional[date] = None
    status: str = "draft"
    journal_entry_id: Optional[int] = None

    @staticmethod
    def _from_row(row):
        return PayRun(
            id=row["id"], client_id=row["client_id"],
            pay_period_start=date.fromisoformat(row["pay_period_start"]),
            pay_period_end=date.fromisoformat(row["pay_period_end"]),
            pay_date=date.fromisoformat(row["pay_date"]), status=row["status"],
            journal_entry_id=row["journal_entry_id"],
        )

    @staticmethod
    def get_by_id(pay_run_id: int) -> Optional["PayRun"]:
        with get_cursor() as cursor:
            cursor.execute("SELECT * FROM pay_runs WHERE id = ?", (pay_run_id,))
            row = cursor.fetchone()
        return PayRun._from_row(row) if row else None

    @staticmethod
    def get_all(client_id: int) -> List["PayRun"]:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM pay_runs WHERE client_id = ? "
                "ORDER BY pay_date DESC, id DESC", (client_id,),
            )
            rows = cursor.fetchall()
        return [PayRun._from_row(row) for row in rows]


@dataclass
class PayStub:
    id: Optional[int] = None
    pay_run_id: int = 0
    employee_id: int = 0
    gross_pay_cents: int = 0
    deductions: List[dict] = field(default_factory=list)
    net_pay_cents: int = 0

    @staticmethod
    def get_all(pay_run_id: int) -> List["PayStub"]:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM pay_stubs WHERE pay_run_id = ? ORDER BY id",
                (pay_run_id,),
            )
            rows = cursor.fetchall()
        return [PayStub(
            id=row["id"], pay_run_id=row["pay_run_id"],
            employee_id=row["employee_id"], gross_pay_cents=row["gross_pay_cents"],
            deductions=json.loads(row["deductions"]), net_pay_cents=row["net_pay_cents"],
        ) for row in rows]

