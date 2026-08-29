"""Accounts receivable and payable workflows."""

from datetime import date
from typing import Iterable, Optional

from database.connection import get_connection, get_cursor
from models.audit_log import AuditLog
from models.journal_entry import JournalEntry, JournalEntryLine
from models.payables import Bill, BillLine, Vendor
from models.receivables import Customer, Invoice, InvoiceLine
from money import to_dollars


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
        result.append(line_type(
            description=description,
            quantity=quantity,
            unit_price_cents=unit_price_cents,
            **{account_field: account_id},
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


def create_customer(client_id: int, name: str, email: Optional[str] = None) -> Customer:
    name = _required_name(name, "Customer name")
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "INSERT INTO customers (client_id, name, email) VALUES (?, ?, ?)",
            (client_id, name, (email or "").strip() or None),
        )
        customer = Customer(cursor.lastrowid, client_id, name, (email or "").strip() or None)
        AuditLog.write(cursor, client_id, "customers", customer.id, "INSERT",
                       new_values={"name": customer.name, "email": customer.email})
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


def create_invoice(client_id: int, customer_id: int, lines: Iterable,
                   invoice_date=None, due_date=None) -> Invoice:
    invoice_date = _iso(invoice_date or date.today(), "invoice_date")
    due_date = _iso(due_date or invoice_date, "due_date")
    invoice_lines = _coerce_lines(lines, InvoiceLine, "revenue_account_id")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM customers WHERE id = ? AND client_id = ?", (customer_id, client_id))
        if not cursor.fetchone():
            raise ValueError("The customer must belong to this client.")
        for line in invoice_lines:
            _assert_account(cursor, client_id, line.revenue_account_id, "Revenue")
        cursor.execute(
            "INSERT INTO invoices (client_id, customer_id, invoice_date, due_date) VALUES (?, ?, ?, ?)",
            (client_id, customer_id, invoice_date, due_date),
        )
        invoice_id = cursor.lastrowid
        for line in invoice_lines:
            cursor.execute(
                "INSERT INTO invoice_lines (invoice_id, description, quantity, unit_price_cents, revenue_account_id) VALUES (?, ?, ?, ?, ?)",
                (invoice_id, line.description, line.quantity, line.unit_price_cents, line.revenue_account_id),
            )
            line.id, line.invoice_id = cursor.lastrowid, invoice_id
        invoice = Invoice(invoice_id, client_id, customer_id, date.fromisoformat(invoice_date),
                          date.fromisoformat(due_date), lines=invoice_lines)
        AuditLog.write(cursor, client_id, "invoices", invoice_id, "INSERT",
                       new_values={"customer_id": customer_id, "invoice_date": invoice_date,
                                   "due_date": due_date, "status": "draft", "total_cents": invoice.total_cents})
        conn.commit()
        return invoice
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_bill(client_id: int, vendor_id: int, lines: Iterable,
                bill_date=None, due_date=None) -> Bill:
    bill_date = _iso(bill_date or date.today(), "bill_date")
    due_date = _iso(due_date or bill_date, "due_date")
    bill_lines = _coerce_lines(lines, BillLine, "expense_account_id")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM vendors WHERE id = ? AND client_id = ?", (vendor_id, client_id))
        if not cursor.fetchone():
            raise ValueError("The vendor must belong to this client.")
        for line in bill_lines:
            _assert_account(cursor, client_id, line.expense_account_id, "Expense")
        cursor.execute(
            "INSERT INTO bills (client_id, vendor_id, bill_date, due_date) VALUES (?, ?, ?, ?)",
            (client_id, vendor_id, bill_date, due_date),
        )
        bill_id = cursor.lastrowid
        for line in bill_lines:
            cursor.execute(
                "INSERT INTO bill_lines (bill_id, description, quantity, unit_price_cents, expense_account_id) VALUES (?, ?, ?, ?, ?)",
                (bill_id, line.description, line.quantity, line.unit_price_cents, line.expense_account_id),
            )
            line.id, line.bill_id = cursor.lastrowid, bill_id
        bill = Bill(bill_id, client_id, vendor_id, date.fromisoformat(bill_date),
                    date.fromisoformat(due_date), lines=bill_lines)
        AuditLog.write(cursor, client_id, "bills", bill_id, "INSERT",
                       new_values={"vendor_id": vendor_id, "bill_date": bill_date,
                                   "due_date": due_date, "status": "draft", "total_cents": bill.total_cents})
        conn.commit()
        return bill
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _load_document(cursor, table: str, lines_table: str, record_id: int,
                   date_field: str, account_field: str, line_type, document_type):
    cursor.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"{document_type.__name__} not found.")
    cursor.execute(f"SELECT * FROM {lines_table} WHERE {table[:-1]}_id = ? ORDER BY id", (record_id,))
    lines = [line_type(
        id=item["id"], **{f"{table[:-1]}_id": record_id}, description=item["description"],
        quantity=item["quantity"], unit_price_cents=item["unit_price_cents"],
        **{account_field: item[account_field]},
    ) for item in cursor.fetchall()]
    party_field = "customer_id" if table == "invoices" else "vendor_id"
    return document_type(
        id=row["id"], client_id=row["client_id"], **{party_field: row[party_field]},
        **{date_field: date.fromisoformat(row[date_field])}, due_date=date.fromisoformat(row["due_date"]),
        status=row["status"], journal_entry_id=row["journal_entry_id"], lines=lines,
    )


def _post_document(record_id: int, control_account_id: int, is_invoice: bool):
    table = "invoices" if is_invoice else "bills"
    lines_table = "invoice_lines" if is_invoice else "bill_lines"
    date_field = "invoice_date" if is_invoice else "bill_date"
    account_field = "revenue_account_id" if is_invoice else "expense_account_id"
    line_type, document_type = (InvoiceLine, Invoice) if is_invoice else (BillLine, Bill)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        document = _load_document(cursor, table, lines_table, record_id, date_field,
                                  account_field, line_type, document_type)
        if document.status != "draft" or document.journal_entry_id is not None:
            raise ValueError(f"This {table[:-1]} has already been posted.")
        _assert_account(cursor, document.client_id, control_account_id,
                        "Asset" if is_invoice else "Liability")
        for line in document.lines:
            _assert_account(cursor, document.client_id, getattr(line, account_field),
                            "Revenue" if is_invoice else "Expense")
        total = document.total_cents
        lines = []
        if is_invoice:
            lines.append(JournalEntryLine(account_id=control_account_id, debit=to_dollars(total)))
            lines.extend(JournalEntryLine(account_id=line.revenue_account_id,
                                          credit=to_dollars(line.amount_cents), memo=line.description)
                         for line in document.lines)
        else:
            lines.extend(JournalEntryLine(account_id=line.expense_account_id,
                                          debit=to_dollars(line.amount_cents), memo=line.description)
                         for line in document.lines)
            lines.append(JournalEntryLine(account_id=control_account_id, credit=to_dollars(total)))
        entry = JournalEntry(
            client_id=document.client_id, entry_date=getattr(document, date_field),
            description=f"Posted {table[:-1]} #{record_id}",
            source_reference=f"{table[:-1].title()} {record_id}", lines=lines,
        )
        entry.save(conn=conn)
        cursor.execute(f"UPDATE {table} SET status = 'posted', journal_entry_id = ? WHERE id = ?",
                       (entry.id, record_id))
        AuditLog.write(cursor, document.client_id, table, record_id, "UPDATE",
                       old_values={"status": "draft", "journal_entry_id": None},
                       new_values={"status": "posted", "journal_entry_id": entry.id})
        conn.commit()
        document.status, document.journal_entry_id = "posted", entry.id
        return document
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def post_invoice(invoice_id: int, ar_account_id: int) -> Invoice:
    return _post_document(invoice_id, ar_account_id, True)


def post_bill(bill_id: int, ap_account_id: int) -> Bill:
    return _post_document(bill_id, ap_account_id, False)


def _record_payment(record_id: int, amount_cents: int, money_account_id: int,
                    control_account_id: int, payment_date, is_invoice: bool):
    table = "invoices" if is_invoice else "bills"
    lines_table = "invoice_lines" if is_invoice else "bill_lines"
    payments_table = "invoice_payments" if is_invoice else "bill_payments"
    date_field = "invoice_date" if is_invoice else "bill_date"
    line_account = "revenue_account_id" if is_invoice else "expense_account_id"
    payment_account = "deposit_account_id" if is_invoice else "payment_account_id"
    line_type, document_type = (InvoiceLine, Invoice) if is_invoice else (BillLine, Bill)
    amount_cents = int(amount_cents)
    if amount_cents <= 0:
        raise ValueError("Payment amount must be greater than zero.")
    payment_date = _iso(payment_date, "payment_date")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        document = _load_document(cursor, table, lines_table, record_id, date_field,
                                  line_account, line_type, document_type)
        if document.status == "draft" or document.journal_entry_id is None:
            raise ValueError(f"Post the {table[:-1]} before recording a payment.")
        if document.status == "paid":
            raise ValueError(f"This {table[:-1]} is already paid.")
        _assert_account(cursor, document.client_id, money_account_id, "Asset")
        _assert_account(cursor, document.client_id, control_account_id,
                        "Asset" if is_invoice else "Liability")
        cursor.execute(f"SELECT COALESCE(SUM(amount_cents), 0) paid FROM {payments_table} WHERE {table[:-1]}_id = ?",
                       (record_id,))
        paid_before = cursor.fetchone()["paid"]
        if paid_before + amount_cents > document.total_cents:
            raise ValueError("Payment cannot exceed the remaining balance.")
        entry_lines = [
            JournalEntryLine(account_id=money_account_id, debit=to_dollars(amount_cents)),
            JournalEntryLine(account_id=control_account_id, credit=to_dollars(amount_cents)),
        ] if is_invoice else [
            JournalEntryLine(account_id=control_account_id, debit=to_dollars(amount_cents)),
            JournalEntryLine(account_id=money_account_id, credit=to_dollars(amount_cents)),
        ]
        entry = JournalEntry(
            client_id=document.client_id, entry_date=date.fromisoformat(payment_date),
            description=f"Payment for {table[:-1]} #{record_id}",
            source_reference=f"{table[:-1].title()} payment {record_id}", lines=entry_lines,
        )
        entry.save(conn=conn)
        cursor.execute(
            f"INSERT INTO {payments_table} ({table[:-1]}_id, payment_date, amount_cents, {payment_account}, journal_entry_id) VALUES (?, ?, ?, ?, ?)",
            (record_id, payment_date, amount_cents, money_account_id, entry.id),
        )
        payment_id = cursor.lastrowid
        paid_after = paid_before + amount_cents
        new_status = "paid" if paid_after >= document.total_cents else "partially_paid"
        cursor.execute(f"UPDATE {table} SET status = ? WHERE id = ?", (new_status, record_id))
        AuditLog.write(cursor, document.client_id, payments_table, payment_id, "INSERT",
                       new_values={f"{table[:-1]}_id": record_id, "payment_date": payment_date,
                                   "amount_cents": amount_cents, payment_account: money_account_id,
                                   "journal_entry_id": entry.id})
        AuditLog.write(cursor, document.client_id, table, record_id, "UPDATE",
                       old_values={"status": document.status}, new_values={"status": new_status})
        conn.commit()
        document.status = new_status
        return document
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_invoice_payment(invoice_id: int, amount_cents: int, deposit_account_id: int,
                           payment_date, ar_account_id: int) -> Invoice:
    return _record_payment(invoice_id, amount_cents, deposit_account_id,
                           ar_account_id, payment_date, True)


def record_bill_payment(bill_id: int, amount_cents: int, payment_account_id: int,
                        payment_date, ap_account_id: int) -> Bill:
    return _record_payment(bill_id, amount_cents, payment_account_id,
                           ap_account_id, payment_date, False)


def list_invoices(client_id: int):
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT i.*, c.name party_name, COALESCE(SUM(il.quantity * il.unit_price_cents), 0) total_cents "
            "FROM invoices i JOIN customers c ON c.id = i.customer_id "
            "LEFT JOIN invoice_lines il ON il.invoice_id = i.id WHERE i.client_id = ? "
            "GROUP BY i.id ORDER BY i.invoice_date DESC, i.id DESC", (client_id,))
        return [dict(row) for row in cursor.fetchall()]


def list_bills(client_id: int):
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT b.*, v.name party_name, COALESCE(SUM(bl.quantity * bl.unit_price_cents), 0) total_cents "
            "FROM bills b JOIN vendors v ON v.id = b.vendor_id "
            "LEFT JOIN bill_lines bl ON bl.bill_id = b.id WHERE b.client_id = ? "
            "GROUP BY b.id ORDER BY b.bill_date DESC, b.id DESC", (client_id,))
        return [dict(row) for row in cursor.fetchall()]
