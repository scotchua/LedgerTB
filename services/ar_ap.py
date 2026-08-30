"""Accounts receivable and payable workflows."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable, Optional

from database.connection import get_connection, get_cursor
from models.audit_log import AuditLog
from models.journal_entry import JournalEntry, JournalEntryLine
from models.payables import Bill, BillLine, Vendor
from models.receivables import CreditMemo, CreditMemoLine, Customer, Invoice, InvoiceLine
from money import to_dollars
from services.inventory import _record_movement


def _iso(value, field_name: str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an ISO date (YYYY-MM-DD).")


def _required_name(value: str, label: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{label} is required.")
    return value


def _normalize_name(value: str) -> str:
    return " ".join(value.split()).lower()


def _line_value(line, name, default=None):
    return line.get(name, default) if isinstance(line, dict) else getattr(line, name, default)


def _tax_values(lines, tax_rate):
    if tax_rate in (None, ""):
        return None, 0
    rate_text = str(tax_rate).strip()
    try:
        rate = Decimal(rate_text)
    except (InvalidOperation, ValueError):
        raise ValueError("Tax rate must be a decimal rate, such as 0.0650.")
    if not rate.is_finite() or rate < 0:
        raise ValueError("Tax rate must be a non-negative decimal rate.")
    subtotal = sum(line.amount_cents for line in lines)
    # One flat, header-level, tax-exclusive rate; line tax codes and stacking are out of scope.
    amount = int((Decimal(subtotal) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return rate_text, amount


def _coerce_lines(lines: Iterable, line_type, account_field: str):
    result = []
    for source in lines or []:
        quantity = int(_line_value(source, "quantity", 1))
        unit_price_cents = int(_line_value(source, "unit_price_cents", 0))
        account_id = int(_line_value(source, account_field, 0))
        description = _required_name(_line_value(source, "description", ""), "Line description")
        if quantity <= 0 or unit_price_cents <= 0:
            raise ValueError("Line quantity and unit price must be greater than zero.")
        if account_id <= 0:
            raise ValueError("Each line needs an account.")
        extra = {}
        if line_type is InvoiceLine:
            item_id = _line_value(source, "inventory_item_id")
            extra["inventory_item_id"] = int(item_id) if item_id not in (None, "") else None
        result.append(line_type(
            description=description, quantity=quantity, unit_price_cents=unit_price_cents,
            **{account_field: account_id}, **extra,
        ))
    if not result:
        raise ValueError("At least one line is required.")
    return result


def _assert_account(cursor, client_id: int, account_id: int, expected_type: Optional[str] = None):
    cursor.execute(
        "SELECT type FROM accounts WHERE id = ? AND client_id = ? AND is_active = 1",
        (account_id, client_id),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("The selected account must be active and belong to this client.")
    if expected_type and row["type"] != expected_type:
        raise ValueError(f"The selected account must be a {expected_type} account.")


def _transaction():
    conn = get_connection()
    conn.execute("BEGIN IMMEDIATE")
    return conn


def create_customer(client_id: int, name: str, email: Optional[str] = None) -> Customer:
    name = _required_name(name, "Customer name")
    email = (email or "").strip() or None
    with get_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO customers (client_id, name, email) VALUES (?, ?, ?)",
                       (client_id, name, email))
        customer = Customer(cursor.lastrowid, client_id, name, email)
        AuditLog.write(cursor, client_id, "customers", customer.id, "INSERT",
                       new_values={"name": name, "email": email})
    return customer


def create_vendor(client_id: int, name: str, email: Optional[str] = None) -> Vendor:
    name = _required_name(name, "Vendor name")
    normalized_name = _normalize_name(name)
    email = (email or "").strip() or None
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "INSERT INTO vendors (client_id, name, normalized_name, email) VALUES (?, ?, ?, ?)",
            (client_id, name, normalized_name, email),
        )
        vendor = Vendor(cursor.lastrowid, client_id, name, normalized_name, email)
        AuditLog.write(cursor, client_id, "vendors", vendor.id, "INSERT",
                       new_values={"name": name, "normalized_name": normalized_name, "email": email})
    return vendor


def _create_document(client_id: int, party_id: int, lines: Iterable, document_date,
                     due_date, is_invoice: bool, tax_rate=None):
    table = "invoices" if is_invoice else "bills"
    party_table = "customers" if is_invoice else "vendors"
    party_field = "customer_id" if is_invoice else "vendor_id"
    date_field = "invoice_date" if is_invoice else "bill_date"
    lines_table = "invoice_lines" if is_invoice else "bill_lines"
    account_field = "revenue_account_id" if is_invoice else "expense_account_id"
    line_type, document_type = (InvoiceLine, Invoice) if is_invoice else (BillLine, Bill)
    document_date = _iso(document_date or date.today(), date_field)
    due_date = _iso(due_date or document_date, "due_date")
    document_lines = _coerce_lines(lines, line_type, account_field)
    tax_rate, tax_amount_cents = _tax_values(document_lines, tax_rate)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT 1 FROM {party_table} WHERE id = ? AND client_id = ?",
                       (party_id, client_id))
        if not cursor.fetchone():
            raise ValueError(f"The {party_table[:-1]} must belong to this client.")
        for line in document_lines:
            _assert_account(cursor, client_id, getattr(line, account_field),
                            "Revenue" if is_invoice else "Expense")
            if is_invoice and line.inventory_item_id is not None:
                cursor.execute(
                    "SELECT 1 FROM inventory_items WHERE id = ? AND client_id = ?",
                    (line.inventory_item_id, client_id),
                )
                if not cursor.fetchone():
                    raise ValueError("The inventory item must belong to this client.")
        cursor.execute(
            f"INSERT INTO {table} (client_id, {party_field}, {date_field}, due_date, tax_rate, tax_amount_cents) VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, party_id, document_date, due_date, tax_rate, tax_amount_cents),
        )
        record_id = cursor.lastrowid
        for line in document_lines:
            if is_invoice:
                cursor.execute(
                    "INSERT INTO invoice_lines (invoice_id, description, quantity, "
                    "unit_price_cents, revenue_account_id, inventory_item_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (record_id, line.description, line.quantity, line.unit_price_cents,
                     line.revenue_account_id, line.inventory_item_id),
                )
            else:
                cursor.execute(
                    f"INSERT INTO {lines_table} ({table[:-1]}_id, description, quantity, unit_price_cents, {account_field}) VALUES (?, ?, ?, ?, ?)",
                    (record_id, line.description, line.quantity, line.unit_price_cents,
                     getattr(line, account_field)),
                )
            line.id = cursor.lastrowid
            setattr(line, f"{table[:-1]}_id", record_id)
        document = document_type(
            id=record_id, client_id=client_id, **{party_field: party_id},
            **{date_field: date.fromisoformat(document_date)}, due_date=date.fromisoformat(due_date),
            tax_rate=tax_rate, tax_amount_cents=tax_amount_cents, lines=document_lines,
        )
        AuditLog.write(cursor, client_id, table, record_id, "INSERT",
                       new_values={party_field: party_id, date_field: document_date,
                                   "due_date": due_date, "status": "draft",
                                   "total_cents": document.total_cents})
        conn.commit()
        return document
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_invoice(client_id: int, customer_id: int, lines: Iterable,
                   invoice_date=None, due_date=None, tax_rate=None) -> Invoice:
    return _create_document(client_id, customer_id, lines, invoice_date, due_date, True, tax_rate)


def create_bill(client_id: int, vendor_id: int, lines: Iterable,
                bill_date=None, due_date=None, tax_rate=None) -> Bill:
    return _create_document(client_id, vendor_id, lines, bill_date, due_date, False, tax_rate)


def _load_document(cursor, record_id: int, is_invoice: bool):
    table = "invoices" if is_invoice else "bills"
    lines_table = "invoice_lines" if is_invoice else "bill_lines"
    date_field = "invoice_date" if is_invoice else "bill_date"
    account_field = "revenue_account_id" if is_invoice else "expense_account_id"
    party_field = "customer_id" if is_invoice else "vendor_id"
    line_type, document_type = (InvoiceLine, Invoice) if is_invoice else (BillLine, Bill)
    cursor.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"{document_type.__name__} not found.")
    cursor.execute(f"SELECT * FROM {lines_table} WHERE {table[:-1]}_id = ? ORDER BY id",
                   (record_id,))
    lines = [line_type(
        id=item["id"], **{f"{table[:-1]}_id": record_id}, description=item["description"],
        quantity=item["quantity"], unit_price_cents=item["unit_price_cents"],
        **{account_field: item[account_field]},
        **({"inventory_item_id": item["inventory_item_id"]} if is_invoice else {}),
    ) for item in cursor.fetchall()]
    return document_type(
        id=row["id"], client_id=row["client_id"], **{party_field: row[party_field]},
        **{date_field: date.fromisoformat(row[date_field])}, due_date=date.fromisoformat(row["due_date"]),
        status=row["status"], journal_entry_id=row["journal_entry_id"],
        voided_journal_entry_id=row["voided_journal_entry_id"],
        control_account_id=row["control_account_id"], tax_rate=row["tax_rate"],
        tax_amount_cents=row["tax_amount_cents"], tax_account_id=row["tax_account_id"], lines=lines,
    )


def _post_document(record_id: int, control_account_id: int, is_invoice: bool,
                   tax_account_id: Optional[int] = None):
    table = "invoices" if is_invoice else "bills"
    date_field = "invoice_date" if is_invoice else "bill_date"
    account_field = "revenue_account_id" if is_invoice else "expense_account_id"
    conn = _transaction()
    try:
        cursor = conn.cursor()
        document = _load_document(cursor, record_id, is_invoice)
        if document.status != "draft" or document.journal_entry_id is not None:
            raise ValueError(f"This {table[:-1]} has already been posted.")
        _assert_account(cursor, document.client_id, control_account_id,
                        "Asset" if is_invoice else "Liability")
        line_account_ids = {getattr(line, account_field) for line in document.lines}
        if control_account_id in line_account_ids:
            raise ValueError("The control account must differ from every document line account.")
        if document.tax_amount_cents > 0:
            if tax_account_id is None:
                raise ValueError("A tax account is required for a taxed document.")
            _assert_account(cursor, document.client_id, tax_account_id, "Liability")
            if tax_account_id == control_account_id or tax_account_id in line_account_ids:
                raise ValueError("The tax account must differ from the control and line accounts.")
        else:
            tax_account_id = None
        for line in document.lines:
            _assert_account(cursor, document.client_id, getattr(line, account_field),
                            "Revenue" if is_invoice else "Expense")
        total = document.total_cents
        if is_invoice:
            lines = [JournalEntryLine(account_id=control_account_id, debit=to_dollars(total))]
            lines.extend(JournalEntryLine(account_id=line.revenue_account_id,
                                          credit=to_dollars(line.amount_cents), memo=line.description)
                         for line in document.lines)
            if document.tax_amount_cents:
                lines.append(JournalEntryLine(account_id=tax_account_id,
                                              credit=to_dollars(document.tax_amount_cents)))
        else:
            lines = [JournalEntryLine(account_id=line.expense_account_id,
                                      debit=to_dollars(line.amount_cents), memo=line.description)
                     for line in document.lines]
            if document.tax_amount_cents:
                lines.append(JournalEntryLine(account_id=tax_account_id,
                                              debit=to_dollars(document.tax_amount_cents)))
            lines.append(JournalEntryLine(account_id=control_account_id, credit=to_dollars(total)))
        entry = JournalEntry(
            client_id=document.client_id, entry_date=getattr(document, date_field),
            description=f"Posted {table[:-1]} #{record_id}",
            source_reference=f"{table[:-1].title()} {record_id}", lines=lines,
        )
        entry.save(conn=conn)
        if is_invoice:
            inventory_lines = []
            for line in document.lines:
                if line.inventory_item_id is None:
                    continue
                result = _record_movement(
                    conn, line.inventory_item_id, document.invoice_date, "sale",
                    -line.quantity, source_type="invoice", source_id=document.id,
                    source_line_id=line.id,
                )
                inventory_lines.append((line, result))
            if inventory_lines:
                cogs_lines = []
                movement_ids = []
                for line, result in inventory_lines:
                    cursor.execute(
                        "SELECT inventory_account_id, cogs_account_id FROM inventory_items WHERE id = ?",
                        (line.inventory_item_id,),
                    )
                    item = cursor.fetchone()
                    cursor.execute(
                        "SELECT unit_cost_cents FROM inventory_movements WHERE id = ?",
                        (result["movement_id"],),
                    )
                    amount_cents = line.quantity * cursor.fetchone()["unit_cost_cents"]
                    cogs_lines.extend([
                        JournalEntryLine(account_id=item["cogs_account_id"],
                                         debit=to_dollars(amount_cents), memo=line.description),
                        JournalEntryLine(account_id=item["inventory_account_id"],
                                         credit=to_dollars(amount_cents), memo=line.description),
                    ])
                    movement_ids.append(result["movement_id"])
                cogs_entry = JournalEntry(
                    client_id=document.client_id, entry_date=document.invoice_date,
                    description=f"Inventory sale: invoice #{record_id}",
                    source_reference=f"Invoice {record_id}", entry_type="Adjusting",
                    lines=cogs_lines,
                )
                cogs_entry.save(conn=conn)
                placeholders = ",".join("?" for _ in movement_ids)
                cursor.execute(
                    f"UPDATE inventory_movements SET journal_entry_id = ? WHERE id IN ({placeholders})",
                    (cogs_entry.id, *movement_ids),
                )
                for movement_id in movement_ids:
                    AuditLog.write(
                        cursor, document.client_id, "inventory_movements", movement_id,
                        "UPDATE", old_values={"journal_entry_id": None},
                        new_values={"journal_entry_id": cogs_entry.id},
                    )
        cursor.execute(
            f"UPDATE {table} SET status = 'posted', journal_entry_id = ?, control_account_id = ?, tax_account_id = ? WHERE id = ?",
            (entry.id, control_account_id, tax_account_id, record_id),
        )
        AuditLog.write(cursor, document.client_id, table, record_id, "UPDATE",
                       old_values={"status": "draft", "journal_entry_id": None,
                                   "control_account_id": None},
                       new_values={"status": "posted", "journal_entry_id": entry.id,
                                   "control_account_id": control_account_id,
                                   "tax_account_id": tax_account_id})
        conn.commit()
        document.status = "posted"
        document.journal_entry_id = entry.id
        document.control_account_id = control_account_id
        document.tax_account_id = tax_account_id
        return document
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def post_invoice(invoice_id: int, ar_account_id: int,
                 tax_account_id: Optional[int] = None) -> Invoice:
    return _post_document(invoice_id, ar_account_id, True, tax_account_id)


def post_bill(bill_id: int, ap_account_id: int,
              tax_account_id: Optional[int] = None) -> Bill:
    return _post_document(bill_id, ap_account_id, False, tax_account_id)


def _open_balance(cursor, record_id: int, is_invoice: bool) -> int:
    table = "invoices" if is_invoice else "bills"
    lines_table = "invoice_lines" if is_invoice else "bill_lines"
    allocations_table = "payment_allocations" if is_invoice else "bill_payment_allocations"
    payments_table = "payments" if is_invoice else "bill_payments_v2"
    cursor.execute(
        f"""SELECT COALESCE((SELECT SUM(quantity * unit_price_cents) FROM {lines_table}
                              WHERE {table[:-1]}_id = ?), 0) + d.tax_amount_cents -
                   COALESCE((SELECT SUM(a.amount_cents) FROM {allocations_table} a
                              JOIN {payments_table} p ON p.id = a.payment_id
                              WHERE a.{table[:-1]}_id = ? AND p.status = 'recorded'), 0) -
                   {"COALESCE((SELECT SUM(amount_cents) FROM credit_applications WHERE invoice_id = d.id), 0)" if is_invoice else "0"} balance
            FROM {table} d WHERE d.id = ?""",
        (record_id, record_id, record_id),
    )
    return int(cursor.fetchone()["balance"])


def _status_for_balance(total_cents: int, open_balance_cents: int) -> str:
    if open_balance_cents == total_cents:
        return "posted"
    return "paid" if open_balance_cents == 0 else "partially_paid"


def _set_document_status(cursor, client_id: int, record_id: int, is_invoice: bool,
                         old_status: str):
    table = "invoices" if is_invoice else "bills"
    document = _load_document(cursor, record_id, is_invoice)
    new_status = _status_for_balance(document.total_cents,
                                     _open_balance(cursor, record_id, is_invoice))
    if new_status != old_status:
        cursor.execute(f"UPDATE {table} SET status = ? WHERE id = ?", (new_status, record_id))
        AuditLog.write(cursor, client_id, table, record_id, "UPDATE",
                       old_values={"status": old_status}, new_values={"status": new_status})
    return new_status


def _after_allocation_insert():
    """Fault-injection seam for transaction rollback tests."""


def _coerce_allocations(allocations, document_field: str):
    result = []
    seen = set()
    for source in allocations or []:
        record_id = int(_line_value(source, document_field, 0))
        amount = int(_line_value(source, "amount_cents", 0))
        if record_id <= 0 or amount <= 0:
            raise ValueError("Every allocation needs a document and an amount greater than zero.")
        if record_id in seen:
            raise ValueError("Each document may appear only once in a payment.")
        seen.add(record_id)
        result.append((record_id, amount))
    return result


def _record_payment(client_id: int, party_id: int, payment_date, amount_cents: int,
                    money_account_id: int, allocations, memo: Optional[str], is_invoice: bool):
    table = "invoices" if is_invoice else "bills"
    party_field = "customer_id" if is_invoice else "vendor_id"
    document_field = "invoice_id" if is_invoice else "bill_id"
    payments_table = "payments" if is_invoice else "bill_payments_v2"
    allocations_table = "payment_allocations" if is_invoice else "bill_payment_allocations"
    money_field = "deposit_account_id" if is_invoice else "payment_account_id"
    amount_cents = int(amount_cents)
    if amount_cents <= 0:
        raise ValueError("Payment amount must be greater than zero.")
    payment_date = _iso(payment_date, "payment_date")
    allocations = _coerce_allocations(allocations, document_field)
    if sum(amount for _, amount in allocations) > amount_cents:
        raise ValueError("Allocated amounts cannot exceed the payment amount.")
    conn = _transaction()
    try:
        cursor = conn.cursor()
        _assert_account(cursor, client_id, money_account_id, "Asset")
        documents = []
        control_accounts = set()
        for record_id, allocation_amount in allocations:
            document = _load_document(cursor, record_id, is_invoice)
            if document.client_id != client_id:
                raise ValueError(f"Every {table[:-1]} must belong to this client.")
            if getattr(document, party_field) != party_id:
                raise ValueError(f"Every {table[:-1]} must belong to this payment's party.")
            if document.status in ("draft", "voided") or document.journal_entry_id is None:
                raise ValueError(f"Every {table[:-1]} must be posted before it can be paid.")
            if document.control_account_id is None:
                raise ValueError(
                    f"This legacy {table[:-1]} has no stored control account; repost it or void and recreate it."
                )
            balance = _open_balance(cursor, record_id, is_invoice)
            if allocation_amount > balance:
                raise ValueError(f"An allocation cannot exceed the {table[:-1]}'s open balance.")
            control_accounts.add(document.control_account_id)
            documents.append((document, allocation_amount))
        if not documents:
            cursor.execute(
                f"""SELECT DISTINCT control_account_id FROM {table}
                    WHERE client_id = ? AND {party_field} = ? AND control_account_id IS NOT NULL
                      AND status IN ('posted', 'partially_paid')""",
                (client_id, party_id),
            )
            control_accounts = {row["control_account_id"] for row in cursor.fetchall()}
            if not control_accounts:
                raise ValueError("An unallocated payment needs a posted document to establish its control account.")
            if len(control_accounts) != 1:
                raise ValueError("An unallocated payment is ambiguous because this party has multiple open control accounts.")
        if len(control_accounts) != 1:
            raise ValueError("All documents in one payment must share the same control account.")
        control_account_id = control_accounts.pop()
        if money_account_id == control_account_id:
            raise ValueError("The money account must differ from the control account.")
        entry_lines = [
            JournalEntryLine(account_id=money_account_id, debit=to_dollars(amount_cents)),
            JournalEntryLine(account_id=control_account_id, credit=to_dollars(amount_cents)),
        ] if is_invoice else [
            JournalEntryLine(account_id=control_account_id, debit=to_dollars(amount_cents)),
            JournalEntryLine(account_id=money_account_id, credit=to_dollars(amount_cents)),
        ]
        entry = JournalEntry(
            client_id=client_id, entry_date=date.fromisoformat(payment_date),
            description="Customer payment" if is_invoice else "Vendor payment",
            source_reference=f"Payment party {party_id}", lines=entry_lines,
        )
        entry.save(conn=conn)
        cursor.execute(
            f"INSERT INTO {payments_table} (client_id, {party_field}, payment_date, amount_cents, {money_field}, control_account_id, memo, journal_entry_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (client_id, party_id, payment_date, amount_cents, money_account_id,
             control_account_id, (memo or "").strip() or None, entry.id),
        )
        payment_id = cursor.lastrowid
        for document, allocation_amount in documents:
            cursor.execute(
                f"INSERT INTO {allocations_table} (payment_id, {document_field}, amount_cents) VALUES (?, ?, ?)",
                (payment_id, document.id, allocation_amount),
            )
            allocation_id = cursor.lastrowid
            AuditLog.write(cursor, client_id, allocations_table, allocation_id, "INSERT",
                           new_values={"payment_id": payment_id, document_field: document.id,
                                       "amount_cents": allocation_amount})
        _after_allocation_insert()
        AuditLog.write(cursor, client_id, payments_table, payment_id, "INSERT",
                       new_values={party_field: party_id, "payment_date": payment_date,
                                   "amount_cents": amount_cents, money_field: money_account_id,
                                   "journal_entry_id": entry.id})
        for document, _ in documents:
            _set_document_status(cursor, client_id, document.id, is_invoice, document.status)
        conn.commit()
        return payment_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_customer_payment(client_id: int, customer_id: int, payment_date,
                            amount_cents: int, deposit_account_id: int, allocations,
                            memo: Optional[str] = None) -> int:
    return _record_payment(client_id, customer_id, payment_date, amount_cents,
                           deposit_account_id, allocations, memo, True)


def record_vendor_payment(client_id: int, vendor_id: int, payment_date,
                          amount_cents: int, payment_account_id: int, allocations,
                          memo: Optional[str] = None) -> int:
    return _record_payment(client_id, vendor_id, payment_date, amount_cents,
                           payment_account_id, allocations, memo, False)


def record_sales_tax_remittance(client_id: int, tax_account_id: int, bank_account_id: int,
                                amount_cents: int, payment_date, memo: Optional[str] = None) -> int:
    amount_cents = int(amount_cents)
    if amount_cents <= 0:
        raise ValueError("Remittance amount must be greater than zero.")
    payment_date = _iso(payment_date, "payment_date")
    conn = _transaction()
    try:
        cursor = conn.cursor()
        _assert_account(cursor, client_id, tax_account_id, "Liability")
        _assert_account(cursor, client_id, bank_account_id, "Asset")
        if tax_account_id == bank_account_id:
            raise ValueError("The tax and bank accounts must differ.")
        entry = JournalEntry(
            client_id=client_id, entry_date=date.fromisoformat(payment_date),
            description="Sales tax remittance", source_reference="Sales tax remittance",
            lines=[
                JournalEntryLine(account_id=tax_account_id, debit=to_dollars(amount_cents)),
                JournalEntryLine(account_id=bank_account_id, credit=to_dollars(amount_cents)),
            ],
        )
        entry.save(conn=conn)
        AuditLog.write(cursor, client_id, "sales_tax_remittances", entry.id, "INSERT",
                       new_values={"tax_account_id": tax_account_id,
                                   "bank_account_id": bank_account_id,
                                   "amount_cents": amount_cents, "payment_date": payment_date,
                                   "memo": (memo or "").strip() or None})
        conn.commit()
        return entry.id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _credit_balance(cursor, payment_id: int, is_invoice: bool) -> int:
    payments_table = "payments" if is_invoice else "bill_payments_v2"
    allocations_table = "payment_allocations" if is_invoice else "bill_payment_allocations"
    refunds_table = "payment_refunds" if is_invoice else "bill_payment_refunds"
    cursor.execute(
        f"""SELECT p.amount_cents -
                   COALESCE((SELECT SUM(amount_cents) FROM {allocations_table} WHERE payment_id = p.id), 0) -
                   COALESCE((SELECT SUM(amount_cents) FROM {refunds_table} WHERE payment_id = p.id), 0) balance
            FROM {payments_table} p WHERE p.id = ? AND p.status = 'recorded'""",
        (payment_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("Payment not found or already voided.")
    return int(row["balance"])


def _apply_credit(payment_id: int, record_id: int, amount_cents: int, is_invoice: bool):
    table = "invoices" if is_invoice else "bills"
    party_field = "customer_id" if is_invoice else "vendor_id"
    document_field = "invoice_id" if is_invoice else "bill_id"
    payments_table = "payments" if is_invoice else "bill_payments_v2"
    allocations_table = "payment_allocations" if is_invoice else "bill_payment_allocations"
    amount_cents = int(amount_cents)
    if amount_cents <= 0:
        raise ValueError("Credit application amount must be greater than zero.")
    conn = _transaction()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {payments_table} WHERE id = ?", (payment_id,))
        payment = cursor.fetchone()
        if not payment or payment["status"] != "recorded":
            raise ValueError("Payment not found or already voided.")
        document = _load_document(cursor, record_id, is_invoice)
        if document.client_id != payment["client_id"] or getattr(document, party_field) != payment[party_field]:
            raise ValueError("The credit and document must belong to the same client and party.")
        if document.status in ("draft", "voided") or document.journal_entry_id is None:
            raise ValueError(f"The {table[:-1]} must be posted before credit can be applied.")
        if document.control_account_id is None:
            raise ValueError(f"This legacy {table[:-1]} has no stored control account; repost it or void and recreate it.")
        if payment["control_account_id"] != document.control_account_id:
            raise ValueError("The credit can only be applied to a document using the same control account.")
        if amount_cents > _credit_balance(cursor, payment_id, is_invoice):
            raise ValueError("Credit application cannot exceed the remaining on-account credit.")
        if amount_cents > _open_balance(cursor, record_id, is_invoice):
            raise ValueError(f"Credit application cannot exceed the {table[:-1]}'s open balance.")
        cursor.execute(
            f"INSERT INTO {allocations_table} (payment_id, {document_field}, amount_cents, applied_later) VALUES (?, ?, ?, 1)",
            (payment_id, record_id, amount_cents),
        )
        allocation_id = cursor.lastrowid
        AuditLog.write(cursor, document.client_id, allocations_table, allocation_id, "INSERT",
                       new_values={"payment_id": payment_id, document_field: record_id,
                                   "amount_cents": amount_cents})
        _set_document_status(cursor, document.client_id, record_id, is_invoice, document.status)
        conn.commit()
        return allocation_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_customer_credit(payment_id: int, invoice_id: int, amount_cents: int) -> int:
    return _apply_credit(payment_id, invoice_id, amount_cents, True)


def apply_vendor_credit(payment_id: int, bill_id: int, amount_cents: int) -> int:
    return _apply_credit(payment_id, bill_id, amount_cents, False)


def _refund_credit(payment_id: int, amount_cents: int, money_account_id: int,
                   refund_date, is_invoice: bool):
    payments_table = "payments" if is_invoice else "bill_payments_v2"
    allocations_table = "payment_allocations" if is_invoice else "bill_payment_allocations"
    refunds_table = "payment_refunds" if is_invoice else "bill_payment_refunds"
    amount_cents = int(amount_cents)
    if amount_cents <= 0:
        raise ValueError("Refund amount must be greater than zero.")
    refund_date = _iso(refund_date or date.today(), "refund_date")
    conn = _transaction()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {payments_table} WHERE id = ?", (payment_id,))
        payment = cursor.fetchone()
        if not payment or payment["status"] != "recorded":
            raise ValueError("Payment not found or already voided.")
        if amount_cents > _credit_balance(cursor, payment_id, is_invoice):
            raise ValueError("Refund cannot exceed the remaining on-account credit.")
        control_account_id = payment["control_account_id"]
        _assert_account(cursor, payment["client_id"], money_account_id, "Asset")
        if money_account_id == control_account_id:
            raise ValueError("The money account must differ from the control account.")
        lines = [
            JournalEntryLine(account_id=control_account_id, debit=to_dollars(amount_cents)),
            JournalEntryLine(account_id=money_account_id, credit=to_dollars(amount_cents)),
        ] if is_invoice else [
            JournalEntryLine(account_id=money_account_id, debit=to_dollars(amount_cents)),
            JournalEntryLine(account_id=control_account_id, credit=to_dollars(amount_cents)),
        ]
        entry = JournalEntry(
            client_id=payment["client_id"], entry_date=date.fromisoformat(refund_date),
            description=f"Refund of payment #{payment_id}",
            source_reference=f"Payment refund {payment_id}", lines=lines,
        )
        entry.save(conn=conn)
        cursor.execute(
            f"INSERT INTO {refunds_table} (payment_id, refund_date, amount_cents, from_account_id, journal_entry_id) VALUES (?, ?, ?, ?, ?)",
            (payment_id, refund_date, amount_cents, money_account_id, entry.id),
        )
        refund_id = cursor.lastrowid
        AuditLog.write(cursor, payment["client_id"], refunds_table, refund_id, "INSERT",
                       new_values={"payment_id": payment_id, "refund_date": refund_date,
                                   "amount_cents": amount_cents, "from_account_id": money_account_id,
                                   "journal_entry_id": entry.id})
        conn.commit()
        return refund_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def refund_customer_credit(payment_id: int, amount_cents: int, from_account_id: int,
                           refund_date=None) -> int:
    return _refund_credit(payment_id, amount_cents, from_account_id, refund_date, True)


def refund_vendor_credit(payment_id: int, amount_cents: int, from_account_id: int,
                         refund_date=None) -> int:
    return _refund_credit(payment_id, amount_cents, from_account_id, refund_date, False)


def _reversal_entry(cursor, client_id: int, original_entry_id: int, reversal_date,
                    description: str, source_reference: str):
    cursor.execute(
        "SELECT account_id, debit, credit, memo FROM journal_entry_lines WHERE journal_entry_id = ? ORDER BY id",
        (original_entry_id,),
    )
    rows = cursor.fetchall()
    if not rows:
        raise ValueError("The original journal entry has no lines to reverse.")
    return JournalEntry(
        client_id=client_id, entry_date=date.fromisoformat(_iso(reversal_date, "void_date")),
        description=description, source_reference=source_reference,
        lines=[JournalEntryLine(account_id=row["account_id"], debit=to_dollars(row["credit"]),
                                credit=to_dollars(row["debit"]), memo=row["memo"])
               for row in rows],
    )


def _void_payment(payment_id: int, void_date, is_invoice: bool):
    payments_table = "payments" if is_invoice else "bill_payments_v2"
    allocations_table = "payment_allocations" if is_invoice else "bill_payment_allocations"
    refunds_table = "payment_refunds" if is_invoice else "bill_payment_refunds"
    document_field = "invoice_id" if is_invoice else "bill_id"
    conn = _transaction()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {payments_table} WHERE id = ?", (payment_id,))
        payment = cursor.fetchone()
        if not payment:
            raise ValueError("Payment not found.")
        if payment["status"] == "voided":
            raise ValueError("This payment has already been voided.")
        blockers = []
        cursor.execute(f"SELECT COUNT(*) count FROM {refunds_table} WHERE payment_id = ?", (payment_id,))
        if cursor.fetchone()["count"]:
            blockers.append("credit refunds")
        cursor.execute(
            f"SELECT id, {document_field}, amount_cents, applied_later FROM {allocations_table} WHERE payment_id = ? ORDER BY id",
            (payment_id,),
        )
        allocations = cursor.fetchall()
        if any(row["applied_later"] for row in allocations):
            blockers.append("subsequent credit applications")
        if blockers:
            raise ValueError("Cannot void this payment because it has " + " and ".join(blockers) + ".")
        documents = [_load_document(cursor, row[document_field], is_invoice) for row in allocations]
        reversal = _reversal_entry(
            cursor, payment["client_id"], payment["journal_entry_id"], void_date,
            f"Void payment #{payment_id}", f"Void payment {payment_id}",
        )
        reversal.save(conn=conn)
        cursor.execute(
            f"UPDATE {payments_table} SET status = 'voided', voided_journal_entry_id = ? WHERE id = ?",
            (reversal.id, payment_id),
        )
        AuditLog.write(cursor, payment["client_id"], payments_table, payment_id, "UPDATE",
                       old_values={"status": "recorded", "voided_journal_entry_id": None},
                       new_values={"status": "voided", "voided_journal_entry_id": reversal.id})
        for document in documents:
            _set_document_status(cursor, payment["client_id"], document.id, is_invoice,
                                 document.status)
        conn.commit()
        return reversal.id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def void_payment(payment_id: int, void_date=None) -> int:
    return _void_payment(payment_id, void_date or date.today(), True)


def void_vendor_payment(payment_id: int, void_date=None) -> int:
    return _void_payment(payment_id, void_date or date.today(), False)


def _void_document(record_id: int, void_date, is_invoice: bool):
    table = "invoices" if is_invoice else "bills"
    allocations_table = "payment_allocations" if is_invoice else "bill_payment_allocations"
    payments_table = "payments" if is_invoice else "bill_payments_v2"
    document_field = "invoice_id" if is_invoice else "bill_id"
    conn = _transaction()
    try:
        cursor = conn.cursor()
        document = _load_document(cursor, record_id, is_invoice)
        if document.status == "draft" or document.journal_entry_id is None:
            raise ValueError(f"A draft {table[:-1]} has nothing posted to reverse.")
        if document.status == "voided":
            raise ValueError(f"This {table[:-1]} has already been voided.")
        cursor.execute(
            f"""SELECT 1 FROM {allocations_table} a JOIN {payments_table} p ON p.id = a.payment_id
                WHERE a.{document_field} = ? AND p.status = 'recorded' LIMIT 1""", (record_id,),
        )
        if cursor.fetchone():
            raise ValueError(f"Void the payment first before voiding this {table[:-1]}.")
        if is_invoice:
            cursor.execute("SELECT 1 FROM credit_applications WHERE invoice_id = ? LIMIT 1",
                           (record_id,))
            if cursor.fetchone():
                raise ValueError("Unapply is not supported; void blocked by a credit application.")
        reversal = _reversal_entry(
            cursor, document.client_id, document.journal_entry_id, void_date,
            f"Void {table[:-1]} #{record_id}", f"Void {table[:-1]} {record_id}",
        )
        reversal.save(conn=conn)
        if is_invoice:
            inventory_lines = []
            for line in document.lines:
                if line.inventory_item_id is None:
                    continue
                cursor.execute(
                    "SELECT id, unit_cost_cents FROM inventory_movements "
                    "WHERE source_type = 'invoice' AND source_id = ? AND source_line_id = ?",
                    (document.id, line.id),
                )
                original = cursor.fetchone()
                if not original:
                    raise ValueError(
                        f"Original inventory movement is missing for invoice line {line.id}."
                    )
                inventory_lines.append((line, original))
            if inventory_lines:
                cogs_lines = []
                movement_ids = []
                reversal_date = date.fromisoformat(_iso(void_date, "void_date"))
                for line, original in inventory_lines:
                    result = _record_movement(
                        conn, line.inventory_item_id, reversal_date, "adjustment",
                        line.quantity, unit_cost_cents=original["unit_cost_cents"],
                        source_type="invoice_void", source_id=document.id,
                        source_line_id=line.id, automatic_journal_entry=False,
                    )
                    cursor.execute(
                        "SELECT inventory_account_id, cogs_account_id FROM inventory_items WHERE id = ?",
                        (line.inventory_item_id,),
                    )
                    item = cursor.fetchone()
                    amount_cents = line.quantity * original["unit_cost_cents"]
                    cogs_lines.extend([
                        JournalEntryLine(account_id=item["inventory_account_id"],
                                         debit=to_dollars(amount_cents), memo=line.description),
                        JournalEntryLine(account_id=item["cogs_account_id"],
                                         credit=to_dollars(amount_cents), memo=line.description),
                    ])
                    movement_ids.append(result["movement_id"])
                cogs_reversal = JournalEntry(
                    client_id=document.client_id, entry_date=reversal_date,
                    description=f"Void inventory sale: invoice #{record_id}",
                    source_reference=f"Void invoice {record_id}", entry_type="Adjusting",
                    lines=cogs_lines,
                )
                cogs_reversal.save(conn=conn)
                placeholders = ",".join("?" for _ in movement_ids)
                cursor.execute(
                    f"UPDATE inventory_movements SET journal_entry_id = ? WHERE id IN ({placeholders})",
                    (cogs_reversal.id, *movement_ids),
                )
                for movement_id in movement_ids:
                    AuditLog.write(
                        cursor, document.client_id, "inventory_movements", movement_id,
                        "UPDATE", old_values={"journal_entry_id": None},
                        new_values={"journal_entry_id": cogs_reversal.id},
                    )
        cursor.execute(
            f"UPDATE {table} SET status = 'voided', voided_journal_entry_id = ? WHERE id = ?",
            (reversal.id, record_id),
        )
        AuditLog.write(cursor, document.client_id, table, record_id, "UPDATE",
                       old_values={"status": document.status, "voided_journal_entry_id": None},
                       new_values={"status": "voided", "voided_journal_entry_id": reversal.id})
        conn.commit()
        return reversal.id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def void_invoice(invoice_id: int, void_date=None) -> int:
    return _void_document(invoice_id, void_date or date.today(), True)


def void_bill(bill_id: int, void_date=None) -> int:
    return _void_document(bill_id, void_date or date.today(), False)


def _load_credit_memo(cursor, memo_id: int) -> CreditMemo:
    cursor.execute("SELECT * FROM credit_memos WHERE id = ?", (memo_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Credit memo not found.")
    cursor.execute("SELECT * FROM credit_memo_lines WHERE credit_memo_id = ? ORDER BY id",
                   (memo_id,))
    lines = [CreditMemoLine(
        id=line["id"], credit_memo_id=memo_id, description=line["description"],
        quantity=line["quantity"], unit_price_cents=line["unit_price_cents"],
        revenue_account_id=line["revenue_account_id"],
    ) for line in cursor.fetchall()]
    return CreditMemo(
        id=row["id"], client_id=row["client_id"], customer_id=row["customer_id"],
        memo_date=date.fromisoformat(row["memo_date"]), status=row["status"],
        original_invoice_id=row["original_invoice_id"], tax_rate=row["tax_rate"],
        tax_amount_cents=row["tax_amount_cents"], control_account_id=row["control_account_id"],
        tax_account_id=row["tax_account_id"], journal_entry_id=row["journal_entry_id"],
        voided_journal_entry_id=row["voided_journal_entry_id"], lines=lines,
    )


def create_credit_memo(client_id: int, customer_id: int, lines: Iterable, memo_date=None,
                       tax_rate=None, original_invoice_id: Optional[int] = None) -> CreditMemo:
    memo_date = _iso(memo_date or date.today(), "memo_date")
    memo_lines = _coerce_lines(lines, CreditMemoLine, "revenue_account_id")
    tax_rate, tax_amount_cents = _tax_values(memo_lines, tax_rate)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM customers WHERE id = ? AND client_id = ?",
                       (customer_id, client_id))
        if not cursor.fetchone():
            raise ValueError("The customer must belong to this client.")
        if original_invoice_id is not None:
            cursor.execute("SELECT client_id, customer_id FROM invoices WHERE id = ?",
                           (original_invoice_id,))
            original = cursor.fetchone()
            if not original or original["client_id"] != client_id or original["customer_id"] != customer_id:
                raise ValueError("The original invoice must belong to the same client and customer.")
        for line in memo_lines:
            _assert_account(cursor, client_id, line.revenue_account_id, "Revenue")
        cursor.execute(
            "INSERT INTO credit_memos (client_id, customer_id, memo_date, original_invoice_id, tax_rate, tax_amount_cents) VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, customer_id, memo_date, original_invoice_id, tax_rate, tax_amount_cents),
        )
        memo_id = cursor.lastrowid
        for line in memo_lines:
            cursor.execute(
                "INSERT INTO credit_memo_lines (credit_memo_id, description, quantity, unit_price_cents, revenue_account_id) VALUES (?, ?, ?, ?, ?)",
                (memo_id, line.description, line.quantity, line.unit_price_cents,
                 line.revenue_account_id),
            )
            line.id = cursor.lastrowid
            line.credit_memo_id = memo_id
        memo = CreditMemo(
            id=memo_id, client_id=client_id, customer_id=customer_id,
            memo_date=date.fromisoformat(memo_date), original_invoice_id=original_invoice_id,
            tax_rate=tax_rate, tax_amount_cents=tax_amount_cents, lines=memo_lines,
        )
        AuditLog.write(cursor, client_id, "credit_memos", memo_id, "INSERT",
                       new_values={"customer_id": customer_id, "memo_date": memo_date,
                                   "original_invoice_id": original_invoice_id,
                                   "tax_rate": tax_rate, "tax_amount_cents": tax_amount_cents,
                                   "total_cents": memo.total_cents})
        conn.commit()
        return memo
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def post_credit_memo(memo_id: int, control_account_id: int,
                     tax_account_id: Optional[int] = None) -> CreditMemo:
    conn = _transaction()
    try:
        cursor = conn.cursor()
        memo = _load_credit_memo(cursor, memo_id)
        if memo.status != "draft" or memo.journal_entry_id is not None:
            raise ValueError("This credit memo has already been posted.")
        _assert_account(cursor, memo.client_id, control_account_id, "Asset")
        line_accounts = {line.revenue_account_id for line in memo.lines}
        if control_account_id in line_accounts:
            raise ValueError("The control account must differ from every credit memo line account.")
        if memo.original_invoice_id is not None:
            cursor.execute("SELECT control_account_id FROM invoices WHERE id = ?",
                           (memo.original_invoice_id,))
            original_control = cursor.fetchone()["control_account_id"]
            if original_control is None or original_control != control_account_id:
                raise ValueError("The credit memo control account must equal the original invoice control account.")
        for line in memo.lines:
            _assert_account(cursor, memo.client_id, line.revenue_account_id, "Revenue")
        if memo.tax_amount_cents:
            if tax_account_id is None:
                raise ValueError("A tax account is required for a taxed credit memo.")
            _assert_account(cursor, memo.client_id, tax_account_id, "Liability")
            if tax_account_id == control_account_id or tax_account_id in line_accounts:
                raise ValueError("The tax account must differ from the control and line accounts.")
        else:
            tax_account_id = None
        lines = [JournalEntryLine(account_id=line.revenue_account_id,
                                  debit=to_dollars(line.amount_cents), memo=line.description)
                 for line in memo.lines]
        if memo.tax_amount_cents:
            lines.append(JournalEntryLine(account_id=tax_account_id,
                                          debit=to_dollars(memo.tax_amount_cents)))
        lines.append(JournalEntryLine(account_id=control_account_id,
                                      credit=to_dollars(memo.total_cents)))
        entry = JournalEntry(
            client_id=memo.client_id, entry_date=memo.memo_date,
            description=f"Posted credit memo #{memo_id}",
            source_reference=f"Credit memo {memo_id}", lines=lines,
        )
        entry.save(conn=conn)
        cursor.execute(
            "UPDATE credit_memos SET status = 'posted', journal_entry_id = ?, control_account_id = ?, tax_account_id = ? WHERE id = ?",
            (entry.id, control_account_id, tax_account_id, memo_id),
        )
        AuditLog.write(cursor, memo.client_id, "credit_memos", memo_id, "UPDATE",
                       old_values={"status": "draft", "journal_entry_id": None},
                       new_values={"status": "posted", "journal_entry_id": entry.id,
                                   "control_account_id": control_account_id,
                                   "tax_account_id": tax_account_id})
        conn.commit()
        memo.status = "posted"
        memo.journal_entry_id = entry.id
        memo.control_account_id = control_account_id
        memo.tax_account_id = tax_account_id
        return memo
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _credit_memo_balance(cursor, memo_id: int) -> int:
    cursor.execute(
        """SELECT COALESCE((SELECT SUM(quantity * unit_price_cents)
                              FROM credit_memo_lines WHERE credit_memo_id = cm.id), 0) +
                       cm.tax_amount_cents - COALESCE((SELECT SUM(amount_cents)
                           FROM credit_applications WHERE credit_memo_id = cm.id), 0) balance
             FROM credit_memos cm WHERE cm.id = ?""", (memo_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("Credit memo not found.")
    return int(row["balance"])


def apply_credit_memo(memo_id: int, invoice_id: int, amount_cents: int) -> int:
    amount_cents = int(amount_cents)
    if amount_cents <= 0:
        raise ValueError("Application amount must be greater than zero.")
    conn = _transaction()
    try:
        cursor = conn.cursor()
        memo = _load_credit_memo(cursor, memo_id)
        if memo.status not in ("posted", "applied") or memo.journal_entry_id is None:
            raise ValueError("The credit memo must be posted and not voided.")
        invoice = _load_document(cursor, invoice_id, True)
        if invoice.status in ("draft", "voided") or invoice.journal_entry_id is None:
            raise ValueError("The invoice must be posted with an open balance.")
        if invoice.client_id != memo.client_id or invoice.customer_id != memo.customer_id:
            raise ValueError("The invoice must belong to the same client and customer.")
        if invoice.control_account_id != memo.control_account_id:
            raise ValueError("The credit memo and invoice must use the same control account.")
        remaining = _credit_memo_balance(cursor, memo_id)
        invoice_balance = _open_balance(cursor, invoice_id, True)
        if amount_cents > remaining:
            raise ValueError("The application cannot exceed the credit memo's remaining balance.")
        if amount_cents > invoice_balance:
            raise ValueError("The application cannot exceed the invoice's open balance.")
        cursor.execute(
            "INSERT INTO credit_applications (credit_memo_id, invoice_id, amount_cents) VALUES (?, ?, ?)",
            (memo_id, invoice_id, amount_cents),
        )
        application_id = cursor.lastrowid
        AuditLog.write(cursor, memo.client_id, "credit_applications", application_id, "INSERT",
                       new_values={"credit_memo_id": memo_id, "invoice_id": invoice_id,
                                   "amount_cents": amount_cents})
        _set_document_status(cursor, memo.client_id, invoice_id, True, invoice.status)
        if _credit_memo_balance(cursor, memo_id) == 0:
            cursor.execute("UPDATE credit_memos SET status = 'applied' WHERE id = ?", (memo_id,))
            AuditLog.write(cursor, memo.client_id, "credit_memos", memo_id, "UPDATE",
                           old_values={"status": memo.status}, new_values={"status": "applied"})
        conn.commit()
        return application_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def void_credit_memo(memo_id: int, void_date=None) -> int:
    conn = _transaction()
    try:
        cursor = conn.cursor()
        memo = _load_credit_memo(cursor, memo_id)
        if memo.status == "draft" or memo.journal_entry_id is None:
            raise ValueError("A draft credit memo has nothing posted to reverse.")
        if memo.status == "voided":
            raise ValueError("This credit memo has already been voided.")
        cursor.execute("SELECT 1 FROM credit_applications WHERE credit_memo_id = ? LIMIT 1",
                       (memo_id,))
        if cursor.fetchone():
            raise ValueError("Unapply is not supported; void blocked while applications exist.")
        reversal = _reversal_entry(
            cursor, memo.client_id, memo.journal_entry_id, void_date or date.today(),
            f"Void credit memo #{memo_id}", f"Void credit memo {memo_id}",
        )
        reversal.save(conn=conn)
        cursor.execute(
            "UPDATE credit_memos SET status = 'voided', voided_journal_entry_id = ? WHERE id = ?",
            (reversal.id, memo_id),
        )
        AuditLog.write(cursor, memo.client_id, "credit_memos", memo_id, "UPDATE",
                       old_values={"status": memo.status, "voided_journal_entry_id": None},
                       new_values={"status": "voided",
                                   "voided_journal_entry_id": reversal.id})
        conn.commit()
        return reversal.id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_credit_memos(client_id: int):
    with get_cursor() as cursor:
        cursor.execute(
            """SELECT cm.*, c.name party_name,
                       COALESCE((SELECT SUM(quantity * unit_price_cents)
                           FROM credit_memo_lines WHERE credit_memo_id = cm.id), 0) +
                           cm.tax_amount_cents total_cents,
                       COALESCE((SELECT SUM(amount_cents) FROM credit_applications
                           WHERE credit_memo_id = cm.id), 0) applied_cents
                 FROM credit_memos cm JOIN customers c ON c.id = cm.customer_id
                WHERE cm.client_id = ? ORDER BY cm.memo_date DESC, cm.id DESC""",
            (client_id,),
        )
        rows = []
        for row in cursor.fetchall():
            item = dict(row)
            item["remaining_balance_cents"] = item["total_cents"] - item["applied_cents"]
            rows.append(item)
        return rows


def _list_documents(client_id: int, is_invoice: bool):
    table = "invoices" if is_invoice else "bills"
    lines_table = "invoice_lines" if is_invoice else "bill_lines"
    party_table = "customers" if is_invoice else "vendors"
    party_field = "customer_id" if is_invoice else "vendor_id"
    allocations_table = "payment_allocations" if is_invoice else "bill_payment_allocations"
    payments_table = "payments" if is_invoice else "bill_payments_v2"
    date_field = "invoice_date" if is_invoice else "bill_date"
    with get_cursor() as cursor:
        cursor.execute(
            f"""SELECT d.*, p.name party_name,
                       COALESCE((SELECT SUM(quantity * unit_price_cents) FROM {lines_table}
                                 WHERE {table[:-1]}_id = d.id), 0) + d.tax_amount_cents total_cents,
                       COALESCE((SELECT SUM(a.amount_cents) FROM {allocations_table} a
                                 JOIN {payments_table} pm ON pm.id = a.payment_id
                                 WHERE a.{table[:-1]}_id = d.id AND pm.status = 'recorded'), 0) allocated_cents
                FROM {table} d JOIN {party_table} p ON p.id = d.{party_field}
                WHERE d.client_id = ? ORDER BY d.{date_field} DESC, d.id DESC""",
            (client_id,),
        )
        rows = []
        for row in cursor.fetchall():
            item = dict(row)
            credit_applications = 0
            if is_invoice:
                cursor.execute("SELECT COALESCE(SUM(amount_cents), 0) amount FROM credit_applications WHERE invoice_id = ?",
                               (item["id"],))
                credit_applications = cursor.fetchone()["amount"]
            item["open_balance_cents"] = (item["total_cents"] - item["allocated_cents"] -
                                           credit_applications)
            rows.append(item)
        return rows


def list_invoices(client_id: int):
    return _list_documents(client_id, True)


def list_bills(client_id: int):
    return _list_documents(client_id, False)


def _list_open_credits(client_id: int, is_invoice: bool):
    payments_table = "payments" if is_invoice else "bill_payments_v2"
    allocations_table = "payment_allocations" if is_invoice else "bill_payment_allocations"
    refunds_table = "payment_refunds" if is_invoice else "bill_payment_refunds"
    party_table = "customers" if is_invoice else "vendors"
    party_field = "customer_id" if is_invoice else "vendor_id"
    with get_cursor() as cursor:
        cursor.execute(
            f"""SELECT p.id payment_id, p.{party_field}, party.name party_name, p.payment_date,
                       p.amount_cents - COALESCE(SUM(a.amount_cents), 0) -
                       COALESCE((SELECT SUM(r.amount_cents) FROM {refunds_table} r
                                 WHERE r.payment_id = p.id), 0) open_credit_cents
                FROM {payments_table} p JOIN {party_table} party ON party.id = p.{party_field}
                LEFT JOIN {allocations_table} a ON a.payment_id = p.id
                WHERE p.client_id = ? AND p.status = 'recorded'
                GROUP BY p.id HAVING open_credit_cents > 0 ORDER BY p.payment_date, p.id""",
            (client_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def list_customer_credits(client_id: int):
    return _list_open_credits(client_id, True)


def list_vendor_credits(client_id: int):
    return _list_open_credits(client_id, False)


def _aging(client_id: int, as_of, is_invoice: bool):
    as_of = date.fromisoformat(_iso(as_of, "as_of"))
    table = "invoices" if is_invoice else "bills"
    lines_table = "invoice_lines" if is_invoice else "bill_lines"
    party_table = "customers" if is_invoice else "vendors"
    party_field = "customer_id" if is_invoice else "vendor_id"
    date_field = "invoice_date" if is_invoice else "bill_date"
    allocations_table = "payment_allocations" if is_invoice else "bill_payment_allocations"
    payments_table = "payments" if is_invoice else "bill_payments_v2"
    refunds_table = "payment_refunds" if is_invoice else "bill_payment_refunds"
    rows = []
    with get_cursor() as cursor:
        cursor.execute(
            f"""SELECT d.id, d.{party_field}, party.name party_name, d.due_date,
                       COALESCE((SELECT SUM(quantity * unit_price_cents) FROM {lines_table}
                                 WHERE {table[:-1]}_id = d.id), 0) + d.tax_amount_cents -
                       COALESCE((SELECT SUM(a.amount_cents) FROM {allocations_table} a
                                 JOIN {payments_table} p ON p.id = a.payment_id
                                 WHERE a.{table[:-1]}_id = d.id AND p.payment_date <= ?
                                   AND NOT (p.status = 'voided' AND EXISTS (
                                       SELECT 1 FROM journal_entries pv
                                       WHERE pv.id = p.voided_journal_entry_id
                                   AND pv.entry_date <= ?))), 0) -
                       {"COALESCE((SELECT SUM(ca.amount_cents) FROM credit_applications ca JOIN credit_memos cm ON cm.id = ca.credit_memo_id WHERE ca.invoice_id = d.id AND cm.memo_date <= ? AND cm.status != 'voided'), 0)" if is_invoice else "0"} open_balance_cents
                FROM {table} d JOIN {party_table} party ON party.id = d.{party_field}
                WHERE d.client_id = ? AND d.status != 'draft' AND d.{date_field} <= ?
                  AND NOT (d.status = 'voided' AND EXISTS (
                      SELECT 1 FROM journal_entries vje
                      WHERE vje.id = d.voided_journal_entry_id AND vje.entry_date <= ?))
                ORDER BY d.due_date, d.id""",
            ((as_of.isoformat(), as_of.isoformat(), as_of.isoformat(), client_id,
              as_of.isoformat(), as_of.isoformat()) if is_invoice else
             (as_of.isoformat(), as_of.isoformat(), client_id, as_of.isoformat(),
              as_of.isoformat())),
        )
        documents = [dict(row) for row in cursor.fetchall()]
    for document in documents:
        if document["open_balance_cents"] <= 0:
            continue
        days = (as_of - date.fromisoformat(document["due_date"])).days
        bucket = "current" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        rows.append({
            "party_id": document["customer_id" if is_invoice else "vendor_id"],
            "party_name": document["party_name"], "document_id": document["id"],
            "kind": "invoice" if is_invoice else "bill", "due_date": document["due_date"],
            "bucket": bucket, "amount_cents": document["open_balance_cents"],
        })
    with get_cursor() as cursor:
        cursor.execute(
            f"""SELECT p.id payment_id, p.{party_field}, party.name party_name, p.payment_date,
                       p.amount_cents - COALESCE((SELECT SUM(a.amount_cents)
                           FROM {allocations_table} a
                           JOIN {table} ad ON ad.id = a.{table[:-1]}_id
                           WHERE a.payment_id = p.id AND ad.{date_field} <= ?), 0) -
                       COALESCE((SELECT SUM(r.amount_cents) FROM {refunds_table} r
                           WHERE r.payment_id = p.id AND r.refund_date <= ?), 0) open_credit_cents
                FROM {payments_table} p JOIN {party_table} party ON party.id = p.{party_field}
                WHERE p.client_id = ? AND p.payment_date <= ?
                  AND NOT (p.status = 'voided' AND EXISTS (
                      SELECT 1 FROM journal_entries vje
                      WHERE vje.id = p.voided_journal_entry_id AND vje.entry_date <= ?))
                ORDER BY p.payment_date, p.id""",
            (as_of.isoformat(), as_of.isoformat(), client_id, as_of.isoformat(), as_of.isoformat()),
        )
        credits = [dict(row) for row in cursor.fetchall()]
    for credit in credits:
        if credit["open_credit_cents"] > 0:
            rows.append({
                "party_id": credit[party_field], "party_name": credit["party_name"],
                "document_id": credit["payment_id"], "kind": "credit",
                "due_date": credit["payment_date"], "bucket": "current",
                "amount_cents": -credit["open_credit_cents"],
            })
    if is_invoice:
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT cm.id, cm.customer_id, c.name party_name, cm.memo_date,
                           COALESCE((SELECT SUM(quantity * unit_price_cents)
                               FROM credit_memo_lines WHERE credit_memo_id = cm.id), 0) +
                           cm.tax_amount_cents - COALESCE((SELECT SUM(ca.amount_cents)
                               FROM credit_applications ca JOIN invoices i ON i.id = ca.invoice_id
                               WHERE ca.credit_memo_id = cm.id AND cm.memo_date <= ?), 0) remaining
                     FROM credit_memos cm JOIN customers c ON c.id = cm.customer_id
                    WHERE cm.client_id = ? AND cm.memo_date <= ? AND cm.status != 'draft'
                      AND NOT (cm.status = 'voided' AND EXISTS (
                          SELECT 1 FROM journal_entries vje
                          WHERE vje.id = cm.voided_journal_entry_id AND vje.entry_date <= ?))
                    ORDER BY cm.memo_date, cm.id""",
                (as_of.isoformat(), client_id, as_of.isoformat(), as_of.isoformat()),
            )
            memo_credits = [dict(row) for row in cursor.fetchall()]
        for credit in memo_credits:
            if credit["remaining"] > 0:
                rows.append({
                    "party_id": credit["customer_id"], "party_name": credit["party_name"],
                    "document_id": credit["id"], "kind": "credit_memo",
                    "due_date": credit["memo_date"], "bucket": "current",
                    "amount_cents": -credit["remaining"],
                })
    return rows


def get_ar_aging(client_id: int, as_of):
    return _aging(client_id, as_of, True)


def get_ap_aging(client_id: int, as_of):
    return _aging(client_id, as_of, False)
