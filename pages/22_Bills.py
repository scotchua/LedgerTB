"""Create, post, and pay bills."""

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
from services.ar_ap import (create_bill, create_vendor, list_bills, post_bill,
                            record_bill_payment)
from utils.client_selector import render_client_selector
from utils.unlock import require_unlock


st.set_page_config(page_title="Bills", page_icon="💳", layout="wide")
require_unlock()
init_database()
client_id = render_client_selector()
st.title("Bills")
if not client_id:
    st.warning("Please select or create a client first.")
    st.stop()

with get_cursor() as cursor:
    cursor.execute("SELECT id, name FROM vendors WHERE client_id = ? ORDER BY name", (client_id,))
    vendors = {row["id"]: row["name"] for row in cursor.fetchall()}

with st.expander("Add vendor"):
    with st.form("add_vendor"):
        name = st.text_input("Vendor name")
        email = st.text_input("Email")
        if st.form_submit_button("Add vendor"):
            try:
                create_vendor(client_id, name, email)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.rerun()

expenses = Account.get_by_type(client_id, "Expense")
liabilities = Account.get_by_type(client_id, "Liability")
assets = Account.get_by_type(client_id, "Asset")
if vendors and expenses:
    with st.expander("Create bill"):
        with st.form("create_bill"):
            vendor_id = st.selectbox("Vendor", list(vendors), format_func=vendors.get)
            bill_date = st.date_input("Bill date", date.today())
            due_date = st.date_input("Due date", date.today())
            description = st.text_input("Description")
            quantity = st.number_input("Quantity", min_value=1, step=1)
            unit_price = st.number_input("Unit price", min_value=0.01, step=0.01)
            expense_id = st.selectbox("Expense account", [a.id for a in expenses],
                                      format_func=lambda aid: next(f"{a.account_number} — {a.name}" for a in expenses if a.id == aid))
            if st.form_submit_button("Create bill"):
                try:
                    create_bill(client_id, vendor_id, [{"description": description,
                        "quantity": int(quantity), "unit_price_cents": to_cents(unit_price),
                        "expense_account_id": expense_id}], bill_date, due_date)
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.rerun()

rows = list_bills(client_id)
st.dataframe(pd.DataFrame([{"Bill": row["id"], "Vendor": row["party_name"],
    "Date": row["bill_date"], "Due": row["due_date"], "Status": row["status"],
    "Total": f"${to_dollars(row['total_cents']):,.2f}"} for row in rows]),
    hide_index=True, width="stretch")

if rows and liabilities and assets:
    selected = st.selectbox("Bill", [row["id"] for row in rows])
    liability_label = lambda aid: next(f"{a.account_number} — {a.name}" for a in liabilities if a.id == aid)
    asset_label = lambda aid: next(f"{a.account_number} — {a.name}" for a in assets if a.id == aid)
    control_id = st.selectbox("A/P control account", [a.id for a in liabilities], format_func=liability_label)
    if st.button("Post bill"):
        try:
            post_bill(selected, control_id)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()
    st.subheader("Record payment")
    amount = st.number_input("Payment amount", min_value=0.01, step=0.01)
    payment_id = st.selectbox("Payment account", [a.id for a in assets], format_func=asset_label)
    payment_date = st.date_input("Payment date", date.today())
    if st.button("Record payment"):
        try:
            record_bill_payment(selected, to_cents(amount), payment_id, payment_date, control_id)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()
