from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class Customer:
    id: Optional[int] = None
    client_id: int = 0
    name: str = ""
    email: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class InvoiceLine:
    id: Optional[int] = None
    invoice_id: Optional[int] = None
    description: str = ""
    quantity: int = 1
    unit_price_cents: int = 0
    revenue_account_id: int = 0
    inventory_item_id: Optional[int] = None

    @property
    def amount_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass
class Invoice:
    id: Optional[int] = None
    client_id: int = 0
    customer_id: int = 0
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    status: str = "draft"
    journal_entry_id: Optional[int] = None
    voided_journal_entry_id: Optional[int] = None
    control_account_id: Optional[int] = None
    tax_rate: Optional[str] = None
    tax_amount_cents: int = 0
    tax_account_id: Optional[int] = None
    lines: List[InvoiceLine] = field(default_factory=list)

    @property
    def subtotal_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.tax_amount_cents


@dataclass
class CreditMemoLine:
    id: Optional[int] = None
    credit_memo_id: Optional[int] = None
    description: str = ""
    quantity: int = 1
    unit_price_cents: int = 0
    revenue_account_id: int = 0

    @property
    def amount_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass
class CreditMemo:
    id: Optional[int] = None
    client_id: int = 0
    customer_id: int = 0
    memo_date: Optional[date] = None
    status: str = "draft"
    original_invoice_id: Optional[int] = None
    tax_rate: Optional[str] = None
    tax_amount_cents: int = 0
    control_account_id: Optional[int] = None
    tax_account_id: Optional[int] = None
    journal_entry_id: Optional[int] = None
    voided_journal_entry_id: Optional[int] = None
    lines: List[CreditMemoLine] = field(default_factory=list)

    @property
    def subtotal_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.tax_amount_cents
