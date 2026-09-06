from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from database.connection import get_cursor


@dataclass
class FixedAssetType:
    id: Optional[int] = None
    client_id: int = 0
    name: str = ""
    asset_account_id: int = 0
    accumulated_depreciation_account_id: int = 0
    depreciation_expense_account_id: int = 0
    method: str = "straight_line"
    effective_life_months: Optional[int] = None
    annual_rate: Optional[float] = None
    convention: str = "full_month"
    total_units: Optional[int] = None

    @staticmethod
    def _from_row(row) -> "FixedAssetType":
        return FixedAssetType(**dict(row))

    @staticmethod
    def get_by_id(type_id: int, client_id: Optional[int] = None):
        query = "SELECT * FROM fixed_asset_types WHERE id = ?"
        params = [type_id]
        if client_id is not None:
            query += " AND client_id = ?"
            params.append(client_id)
        with get_cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        return FixedAssetType._from_row(row) if row else None

    @staticmethod
    def get_all(client_id: int) -> List["FixedAssetType"]:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM fixed_asset_types WHERE client_id = ? ORDER BY name",
                (client_id,),
            )
            rows = cursor.fetchall()
        return [FixedAssetType._from_row(row) for row in rows]

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Asset type name is required.")
        if self.convention not in {"full_month", "mid_month", "half_year"}:
            raise ValueError("Unsupported depreciation convention.")
        if self.method != "units_of_production" and self.total_units is not None:
            raise ValueError("Only units-of-production types can have total units.")
        if self.method == "straight_line":
            if not self.effective_life_months or self.effective_life_months <= 0:
                raise ValueError("Straight-line types need a positive useful life.")
            if self.annual_rate is not None:
                raise ValueError("Straight-line types cannot have an annual rate.")
            if self.convention == "half_year" and self.effective_life_months % 12:
                raise ValueError("Half-year straight-line types need whole years of useful life.")
        elif self.method == "declining_balance":
            if self.annual_rate is None or not 0 < self.annual_rate <= 1:
                raise ValueError("Declining-balance annual rate must be between 0 and 1.")
            if self.effective_life_months is not None:
                raise ValueError("Declining-balance types cannot have a useful life.")
        elif self.method == "units_of_production":
            if type(self.total_units) is not int or self.total_units <= 0:
                raise ValueError("Units-of-production types need positive integer total units.")
            if self.annual_rate is not None or self.effective_life_months is not None:
                raise ValueError("Units-of-production types cannot have a rate or useful life.")
        else:
            raise ValueError("Unsupported depreciation method.")

    def save(self) -> int:
        from models.account import Account
        from models.audit_log import AuditLog

        self.validate()
        accounts = [
            Account.get_by_id(account_id, self.client_id)
            for account_id in (
                self.asset_account_id,
                self.accumulated_depreciation_account_id,
                self.depreciation_expense_account_id,
            )
        ]
        if any(account is None for account in accounts):
            raise ValueError("Every fixed-asset type account must belong to the client.")
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                """INSERT INTO fixed_asset_types
                   (client_id, name, asset_account_id,
                    accumulated_depreciation_account_id,
                    depreciation_expense_account_id, method,
                    effective_life_months, annual_rate, convention, total_units)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.client_id, self.name.strip(), self.asset_account_id,
                 self.accumulated_depreciation_account_id,
                 self.depreciation_expense_account_id, self.method,
                 self.effective_life_months, self.annual_rate,
                 self.convention, self.total_units),
            )
            self.id = cursor.lastrowid
            AuditLog.write(
                cursor, self.client_id, "fixed_asset_types", self.id, "INSERT",
                new_values=self.__dict__,
            )
        return self.id


@dataclass
class FixedAsset:
    id: Optional[int] = None
    client_id: int = 0
    fixed_asset_type_id: int = 0
    description: str = ""
    acquisition_date: Optional[date] = None
    cost_cents: int = 0
    salvage_value_cents: int = 0
    in_service_date: Optional[date] = None
    status: str = "registered"
    disposal_date: Optional[date] = None
    disposal_proceeds_cents: Optional[int] = None

    @staticmethod
    def _from_row(row) -> "FixedAsset":
        values = dict(row)
        for name in ("acquisition_date", "in_service_date", "disposal_date"):
            values[name] = date.fromisoformat(values[name]) if values[name] else None
        return FixedAsset(**values)

    @staticmethod
    def get_by_id(asset_id: int, client_id: Optional[int] = None):
        query = "SELECT * FROM fixed_assets WHERE id = ?"
        params = [asset_id]
        if client_id is not None:
            query += " AND client_id = ?"
            params.append(client_id)
        with get_cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        return FixedAsset._from_row(row) if row else None

    @staticmethod
    def get_all(client_id: int) -> List["FixedAsset"]:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM fixed_assets WHERE client_id = ? ORDER BY description",
                (client_id,),
            )
            rows = cursor.fetchall()
        return [FixedAsset._from_row(row) for row in rows]

    @property
    def accumulated_depreciation_cents(self) -> int:
        if self.id is None:
            return 0
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) total "
                "FROM depreciation_runs WHERE fixed_asset_id = ? "
                "AND superseded_by IS NULL",
                (self.id,),
            )
            return int(cursor.fetchone()["total"])

    @property
    def book_value_cents(self) -> int:
        return self.cost_cents - self.accumulated_depreciation_cents

    def save(self) -> int:
        from models.audit_log import AuditLog

        if not self.description.strip():
            raise ValueError("Asset description is required.")
        if not self.acquisition_date or not self.in_service_date:
            raise ValueError("Acquisition and in-service dates are required.")
        if self.in_service_date < self.acquisition_date:
            raise ValueError("In-service date cannot precede acquisition date.")
        if self.cost_cents < 0 or not 0 <= self.salvage_value_cents <= self.cost_cents:
            raise ValueError("Cost and salvage value are invalid.")
        asset_type = FixedAssetType.get_by_id(self.fixed_asset_type_id, self.client_id)
        if asset_type is None:
            raise ValueError("Asset type must belong to the client.")
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                """INSERT INTO fixed_assets
                   (client_id, fixed_asset_type_id, description, acquisition_date,
                    cost_cents, salvage_value_cents, in_service_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (self.client_id, self.fixed_asset_type_id, self.description.strip(),
                 self.acquisition_date.isoformat(), self.cost_cents,
                 self.salvage_value_cents, self.in_service_date.isoformat()),
            )
            self.id = cursor.lastrowid
            AuditLog.write(
                cursor, self.client_id, "fixed_assets", self.id, "INSERT",
                new_values=self.__dict__,
            )
        return self.id
