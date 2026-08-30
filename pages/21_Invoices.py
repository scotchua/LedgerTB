"""Create, post, and receive payment for invoices."""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import init_database
from database.connection import get_cursor
from models.account import Account
from money import to_cents, to_dollars
from services.ar_ap import (create_customer, create_invoice, list_customer_credits,
                            list_invoices, post_invoice, record_customer_payment,
                            void_invoice, void_payment)
from utils.client_selector import render_client_selector
from utils.unlock import require_unlock


st.set_page_config(page_title="Invoices", page_icon="🧾", layout="wide")
require_unlock()
init_database()
client_id = render_client_selector()
st.title("Invoices")
if not client_id:
    st.warning("Please select or create a client first.")
    st.stop()

with get_cursor() as cursor:
    cursor.execute("SELECT id, name FROM customers WHERE client_id = ? ORDER BY name", (client_id,))
    customers = {row["id"]: row["name"] for row in cursor.fetchall()}
    cursor.execute(
        """SELECT i.id, i.sku, COALESCE(SUM(m.quantity), 0) quantity
           FROM inventory_items i
           LEFT JOIN inventory_movements m ON m.inventory_item_id = i.id
           WHERE i.client_id = ? GROUP BY i.id, i.sku ORDER BY i.sku""",
        (client_id,),
    )
    inventory_items = {
        row["id"]: f"{row['sku']} ({row['quantity']:g} on hand)"
        for row in cursor.fetchall()
    }

with st.expander("Add customer"):
    with st.form("add_customer"):
        name = st.text_input("Customer name")
        email = st.text_input("Email")
        if st.form_submit_button("Add customer"):
            try:
                create_customer(client_id, name, email)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.rerun()

revenue = Account.get_by_type(client_id, "Revenue")
assets = Account.get_by_type(client_id, "Asset")
if customers and revenue:
    with st.expander("Create invoice"):
        with st.form("create_invoice"):
            customer_id = st.selectbox("Customer", list(customers), format_func=customers.get)
            invoice_date = st.date_input("Invoice date", date.today())
            due_date = st.date_input("Due date", date.today())
            description = st.text_input("Description")
            quantity = st.number_input("Quantity", min_value=1, step=1)
            unit_price = st.number_input("Unit price", min_value=0.01, step=0.01)
            revenue_id = st.selectbox("Revenue account", [a.id for a in revenue],
                                      format_func=lambda aid: next(f"{a.account_number} — {a.name}" for a in revenue if a.id == aid))
            inventory_item_id = st.selectbox(
                "Inventory item (optional)", [None, *inventory_items],
                format_func=lambda item_id: "Service / not tracked" if item_id is None
                else inventory_items[item_id],
            )
            if st.form_submit_button("Create invoice"):
                try:
                    create_invoice(client_id, customer_id, [{"description": description,
                        "quantity": int(quantity), "unit_price_cents": to_cents(unit_price),
                        "revenue_account_id": revenue_id,
                        "inventory_item_id": inventory_item_id}], invoice_date, due_date)
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.rerun()

rows = list_invoices(client_id)
st.dataframe(pd.DataFrame([{"Invoice": row["id"], "Customer": row["party_name"],
    "Date": row["invoice_date"], "Due": row["due_date"], "Status": row["status"],
    "Total": f"${to_dollars(row['total_cents']):,.2f}",
    "Open": f"${to_dollars(row['open_balance_cents']):,.2f}"} for row in rows]),
    hide_index=True, width="stretch")

if rows and assets:
    selected = st.selectbox("Invoice", [row["id"] for row in rows])
    asset_label = lambda aid: next(f"{a.account_number} — {a.name}" for a in assets if a.id == aid)
    control_id = st.selectbox("A/R control account", [a.id for a in assets], format_func=asset_label)
    if st.button("Post invoice"):
        try:
            post_invoice(selected, control_id)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()
    if st.button("Void invoice"):
        try:
            void_invoice(selected, date.today())
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()
    st.subheader("Record customer payment")
    selected_row = next(row for row in rows if row["id"] == selected)
    amount = st.number_input("Payment amount", min_value=0.01, step=0.01)
    allocation = st.number_input("Allocate to selected invoice", min_value=0.01,
                                 max_value=max(0.01, to_dollars(selected_row["open_balance_cents"])),
                                 step=0.01)
    deposit_id = st.selectbox("Deposit account", [a.id for a in assets], format_func=asset_label)
    payment_date = st.date_input("Payment date", date.today())
    if st.button("Record payment"):
        try:
            record_customer_payment(client_id, selected_row["customer_id"], payment_date,
                                    to_cents(amount), deposit_id,
                                    [{"invoice_id": selected, "amount_cents": to_cents(allocation)}])
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()

credits = list_customer_credits(client_id)
if credits:
    st.subheader("Open customer credits")
    st.dataframe(pd.DataFrame([{"Payment": row["payment_id"], "Customer": row["party_name"],
        "Credit": f"${to_dollars(row['open_credit_cents']):,.2f}"} for row in credits]),
        hide_index=True, width="stretch")
    credit_payment = st.selectbox("Payment to void", [row["payment_id"] for row in credits])
    if st.button("Void customer payment"):
        try:
            void_payment(credit_payment, date.today())
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()
