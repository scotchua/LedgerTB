"""Period-end inventory movements, valuation postings, and rollforwards."""

import csv
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from database.connection import get_connection, get_cursor
from models.audit_log import AuditLog
from models.fiscal_period import FiscalPeriod
from models.journal_entry import JournalEntry, JournalEntryLine
from money import to_dollars
from utils.fiscal_dates import require_valid_range


MOVEMENT_TYPES = ("purchase", "sale", "adjustment", "count")
CENT = Decimal("1")


def _decimal(value, label):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number.") from exc


def _movement_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("Movement date must use YYYY-MM-DD format.") from exc


def _round_cents(value):
    return int(Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP))


def _item(cursor, item_id):
    cursor.execute("SELECT * FROM inventory_items WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError("Inventory item not found.")
    return row


def create_item(client_id, sku, description, inventory_account_id, cogs_account_id):
    """Create an inventory register item and its audit record."""
    sku = (sku or "").strip()
    if not sku:
        raise ValueError("SKU is required.")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, type FROM accounts WHERE client_id = ? AND id IN (?, ?)",
            (client_id, inventory_account_id, cogs_account_id),
        )
        account_types = {row["id"]: row["type"] for row in cursor.fetchall()}
        if account_types.get(inventory_account_id) != "Asset":
            raise ValueError("Inventory account must be an Asset account for this client.")
        if account_types.get(cogs_account_id) != "Expense":
            raise ValueError("COGS account must be an Expense account for this client.")
        cursor.execute(
            """
            INSERT INTO inventory_items
                (client_id, sku, description, inventory_account_id, cogs_account_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (client_id, sku, (description or "").strip(),
             inventory_account_id, cogs_account_id),
        )
        item_id = cursor.lastrowid
        AuditLog.write(
            cursor, client_id, "inventory_items", item_id, "INSERT",
            new_values={
                "sku": sku, "description": (description or "").strip(),
                "inventory_account_id": inventory_account_id,
                "cogs_account_id": cogs_account_id,
            },
        )
        conn.commit()
        return item_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_items(client_id):
    """Return register items with quantity and cost derived from movements."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM inventory_items WHERE client_id = ? ORDER BY sku", (client_id,)
        )
        items = [dict(row) for row in cursor.fetchall()]
    for item in items:
        item.update(inventory_position(item["id"]))
    return items


def inventory_position(item_id, through_date=None, conn=None):
    """Derive quantity, weighted-average unit cost, and value from history."""
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        cursor = conn.cursor()
        _item(cursor, item_id)
        params = [item_id]
        date_filter = ""
        if through_date is not None:
            date_filter = " AND movement_date <= ?"
            params.append(_movement_date(through_date).isoformat())
        cursor.execute(
            "SELECT quantity, unit_cost_cents FROM inventory_movements "
            "WHERE inventory_item_id = ?" + date_filter +
            " ORDER BY movement_date, id",
            params,
        )
        quantity = Decimal("0")
        value_cents = Decimal("0")
        average_cents = Decimal("0")
        for row in cursor.fetchall():
            movement_quantity = Decimal(str(row["quantity"]))
            # Older rows may not have a stored cost; preserve their historical
            # running-average valuation without migrating existing data.
            unit_cost = (
                Decimal(row["unit_cost_cents"])
                if row["unit_cost_cents"] is not None else average_cents
            )
            value_cents += movement_quantity * unit_cost
            quantity += movement_quantity
            if quantity < 0:
                raise ValueError("Inventory movement history cannot produce negative quantity.")
            average_cents = value_cents / quantity if quantity else Decimal("0")
            if not quantity:
                value_cents = Decimal("0")
        return {
            "quantity": float(quantity),
            "weighted_average_unit_cost_cents": _round_cents(average_cents),
            "value_cents": _round_cents(value_cents),
        }
    finally:
        if owns_conn:
            conn.close()


def _record_movement(
    conn, item_id, movement_date, movement_type, movement_quantity, closed_period=None,
    unit_cost_cents=None, post_journal_entry=False, offset_account_id=None,
):
    """Record and validate one movement in the caller's transaction."""
    cursor = conn.cursor()
    item = _item(cursor, item_id)
    if closed_period:
        raise ValueError(
            f"{closed_period.period_name} is closed. Reopen the year before recording "
            f"inventory movements dated {movement_date.isoformat()}."
        )
    before = inventory_position(item_id, conn=conn)
    effective_cost = (
        _decimal(unit_cost_cents, "Unit cost")
        if unit_cost_cents is not None else
        Decimal(before["weighted_average_unit_cost_cents"])
    )
    if (
        movement_type in ("adjustment", "count")
        and movement_quantity > 0 and not before["quantity"]
        and unit_cost_cents is None
    ):
        raise ValueError(
            "Unit cost is required for a positive adjustment with no inventory on hand."
        )
    if effective_cost < 0:
        raise ValueError("Unit cost cannot be negative.")
    if movement_type in ("sale", "adjustment", "count"):
        if Decimal(str(before["quantity"])) + movement_quantity < 0:
            raise ValueError("Movement cannot reduce inventory below zero.")

    stored_cost = _round_cents(effective_cost)
    journal_entry_id = None
    should_post = post_journal_entry or movement_type in ("adjustment", "count")
    if should_post:
        offset_id = (
            offset_account_id
            if offset_account_id is not None else item["cogs_account_id"]
        )
        cursor.execute(
            "SELECT id FROM accounts WHERE client_id = ? AND id IN (?, ?)",
            (item["client_id"], item["inventory_account_id"], offset_id),
        )
        if {row["id"] for row in cursor.fetchall()} != {
            item["inventory_account_id"], offset_id
        }:
            raise ValueError("Posting accounts must belong to the inventory item's client.")
        amount_cents = abs(_round_cents(movement_quantity * stored_cost))
        if not amount_cents:
            raise ValueError("A posted movement must have a non-zero valuation.")
        amount = to_dollars(amount_cents)
        increase = movement_quantity > 0
        entry = JournalEntry(
            client_id=item["client_id"], entry_date=movement_date,
            description=f"Inventory {movement_type}: {item['sku']}",
            source_reference=f"Inventory item {item_id}", entry_type="Adjusting",
            lines=[
                JournalEntryLine(
                    account_id=item["inventory_account_id"],
                    debit=amount if increase else 0,
                    credit=0 if increase else amount,
                ),
                JournalEntryLine(
                    account_id=offset_id,
                    debit=0 if increase else amount,
                    credit=amount if increase else 0,
                ),
            ],
        )
        journal_entry_id = entry.save(conn=conn)

    cursor.execute(
        """
        INSERT INTO inventory_movements
            (inventory_item_id, movement_date, movement_type, quantity,
             unit_cost_cents, journal_entry_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (item_id, movement_date.isoformat(), movement_type,
         float(movement_quantity), stored_cost, journal_entry_id),
    )
    movement_id = cursor.lastrowid
    AuditLog.write(
        cursor, item["client_id"], "inventory_movements", movement_id, "INSERT",
        new_values={
            "inventory_item_id": item_id,
            "movement_date": movement_date.isoformat(),
            "movement_type": movement_type,
            "quantity": float(movement_quantity),
            "unit_cost_cents": stored_cost,
            "journal_entry_id": journal_entry_id,
        },
    )
    result = inventory_position(item_id, conn=conn)
    result.update({"movement_id": movement_id, "journal_entry_id": journal_entry_id})
    return result


def record_movement(
    item_id, date, movement_type, quantity, unit_cost_cents=None,
    post_journal_entry=False, offset_account_id=None,
):
    """Append one movement and optionally post its inventory valuation entry.

    Purchases require ``unit_cost_cents`` and post only when
    ``post_journal_entry`` is true. Sales/reductions use the current weighted
    average and never post here. Adjustments/counts always post, using the
    item's COGS account unless ``offset_account_id`` is supplied.
    """
    movement_type = (movement_type or "").strip().lower()
    if movement_type not in MOVEMENT_TYPES:
        raise ValueError(f"Movement type must be one of: {', '.join(MOVEMENT_TYPES)}.")
    movement_date = _movement_date(date)
    movement_quantity = _decimal(quantity, "Quantity")
    if not movement_quantity:
        raise ValueError("Quantity cannot be zero.")
    if movement_type == "purchase" and movement_quantity < 0:
        raise ValueError("Purchase quantity must be positive.")
    if movement_type == "sale" and movement_quantity > 0:
        raise ValueError("Sale quantity must be negative.")
    if movement_type == "purchase" and unit_cost_cents is None:
        raise ValueError("Purchase unit cost is required.")
    if movement_type == "sale" and unit_cost_cents is not None:
        raise ValueError("Sale unit cost is derived from the current weighted average.")
    if post_journal_entry and movement_type == "sale":
        raise ValueError("Sale journal posting is outside this close-oriented subledger.")
    if post_journal_entry and movement_type == "purchase" and offset_account_id is None:
        raise ValueError("A payment or payable offset account is required to post a purchase.")

    with get_cursor() as cursor:
        item = _item(cursor, item_id)
    closed_period = FiscalPeriod.get_closed_period_for_date(
        item["client_id"], movement_date
    )
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        result = _record_movement(
            conn, item_id, movement_date, movement_type, movement_quantity,
            closed_period, unit_cost_cents, post_journal_entry, offset_account_id,
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_movements_from_csv(item_id, file):
    """Import movements from CSV.

    Expected columns are ``date``, ``quantity``, and ``unit_cost``. Dates use
    YYYY-MM-DD, quantity is positive for purchases and negative for sales, and
    unit_cost is a dollar amount required for positive rows and blank for
    negative rows. CSV imports record subledger movements only; they do not
    create journal entries.
    """
    if hasattr(file, "seek"):
        file.seek(0)
    content = file.read() if hasattr(file, "read") else file
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    reader = csv.DictReader(str(content).splitlines())
    expected = {"date", "quantity", "unit_cost"}
    if not reader.fieldnames or set(reader.fieldnames) != expected:
        raise ValueError("CSV columns must be exactly: date, quantity, unit_cost.")
    parsed = []
    for row_number, row in enumerate(reader, start=2):
        try:
            quantity = _decimal(row["quantity"], "Quantity")
            if not quantity:
                raise ValueError("Quantity cannot be zero.")
            movement_type = "purchase" if quantity > 0 else "sale"
            unit_cost_cents = None
            if quantity > 0:
                if not (row["unit_cost"] or "").strip():
                    raise ValueError("Unit cost is required for positive quantities.")
                unit_cost_cents = _round_cents(
                    _decimal(row["unit_cost"], "Unit cost") * Decimal("100")
                )
            elif (row["unit_cost"] or "").strip():
                raise ValueError("Unit cost must be blank for negative quantities.")
            parsed.append((_movement_date(row["date"]), movement_type, quantity,
                           unit_cost_cents))
        except Exception as exc:
            raise ValueError(f"CSV row {row_number}: {exc}") from exc

    with get_cursor() as cursor:
        item = _item(cursor, item_id)
    closed_periods = {
        movement_date: FiscalPeriod.get_closed_period_for_date(
            item["client_id"], movement_date
        )
        for movement_date, _, _, _ in parsed
    }
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        imported = []
        for movement_date, movement_type, quantity, unit_cost_cents in parsed:
            imported.append(_record_movement(
                conn, item_id, movement_date, movement_type, quantity,
                closed_period=closed_periods[movement_date],
                unit_cost_cents=unit_cost_cents, post_journal_entry=False,
            ))
        conn.commit()
        return imported
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def inventory_rollforward(item_id, period_start, period_end):
    """Return a reviewable quantity/value rollforward for one period."""
    start = _movement_date(period_start)
    end = _movement_date(period_end)
    require_valid_range(start, end, "Inventory rollforward")
    opening = inventory_position(item_id, through_date=date.fromordinal(start.toordinal() - 1))
    closing = inventory_position(item_id, through_date=end)
    with get_cursor() as cursor:
        _item(cursor, item_id)
        cursor.execute(
            """
            SELECT movement_type, quantity, unit_cost_cents
            FROM inventory_movements
            WHERE inventory_item_id = ? AND movement_date BETWEEN ? AND ?
            ORDER BY movement_date, id
            """,
            (item_id, start.isoformat(), end.isoformat()),
        )
        rows = cursor.fetchall()

    additions = Decimal("0")
    reductions = Decimal("0")
    adjustments = Decimal("0")
    additions_value = Decimal("0")
    reductions_value = Decimal("0")
    adjustments_value = Decimal("0")
    running_quantity = Decimal(str(opening["quantity"]))
    running_value = Decimal(opening["value_cents"])
    for row in rows:
        quantity = Decimal(str(row["quantity"]))
        average_cost = running_value / running_quantity if running_quantity else Decimal("0")
        unit_cost = (
            Decimal(row["unit_cost_cents"])
            if row["unit_cost_cents"] is not None else average_cost
        )
        movement_value = quantity * unit_cost
        if row["movement_type"] == "purchase":
            additions += quantity
            additions_value += movement_value
        elif row["movement_type"] == "sale":
            reductions += abs(quantity)
            reductions_value += abs(movement_value)
        else:
            adjustments += quantity
            adjustments_value += movement_value
        running_quantity += quantity
        running_value += movement_value
        if not running_quantity:
            running_value = Decimal("0")
    opening_quantity = Decimal(str(opening["quantity"]))
    closing_quantity = Decimal(str(closing["quantity"]))
    return {
        "period_start": start, "period_end": end,
        "opening_quantity": float(opening_quantity),
        "opening_value_cents": opening["value_cents"],
        "additions_quantity": float(additions),
        "additions_value_cents": _round_cents(additions_value),
        "reductions_quantity": float(reductions),
        "reductions_value_cents": _round_cents(reductions_value),
        "adjustments_quantity": float(adjustments),
        "adjustments_value_cents": _round_cents(adjustments_value),
        "closing_quantity": float(closing_quantity),
        "closing_value_cents": closing["value_cents"],
        "quantity_check": float(
            opening_quantity + additions - reductions + adjustments - closing_quantity
        ),
    }
