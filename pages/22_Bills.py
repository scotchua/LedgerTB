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
from services.ar_ap import (apply_vendor_credit, create_bill, create_vendor, list_bills,
                            list_vendor_credits, post_bill, record_vendor_payment,
                            record_sales_tax_remittance, void_bill,
                            void_vendor_payment)
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
            tax_rate = st.text_input("Tax rate (optional decimal, e.g. 0.0650)")
            expense_id = st.selectbox("Expense account", [a.id for a in expenses],
                                      format_func=lambda aid: next(f"{a.account_number} — {a.name}" for a in expenses if a.id == aid))
            if st.form_submit_button("Create bill"):
                try:
                    create_bill(client_id, vendor_id, [{"description": description,
                        "quantity": int(quantity), "unit_price_cents": to_cents(unit_price),
                        "expense_account_id": expense_id}], bill_date, due_date,
                        tax_rate or None)
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.rerun()

rows = list_bills(client_id)
st.dataframe(pd.DataFrame([{"Bill": row["id"], "Vendor": row["party_name"],
    "Date": row["bill_date"], "Due": row["due_date"], "Status": row["status"],
    "Total": f"${to_dollars(row['total_cents']):,.2f}",
    "Open": f"${to_dollars(row['open_balance_cents']):,.2f}"} for row in rows]),
    hide_index=True, width="stretch")

if rows and liabilities and assets:
    selected = st.selectbox("Bill", [row["id"] for row in rows])
    liability_label = lambda aid: next(f"{a.account_number} — {a.name}" for a in liabilities if a.id == aid)
    asset_label = lambda aid: next(f"{a.account_number} — {a.name}" for a in assets if a.id == aid)
    control_id = st.selectbox("A/P control account", [a.id for a in liabilities], format_func=liability_label)
    tax_account_id = st.selectbox("Sales tax liability account (for taxed bills)",
                                  [None, *[a.id for a in liabilities]],
                                  format_func=lambda aid: "Not taxed" if aid is None else liability_label(aid))
    if st.button("Post bill"):
        try:
            post_bill(selected, control_id, tax_account_id)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()
    if st.button("Void bill"):
        try:
            void_bill(selected, date.today())
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()
    st.subheader("Record vendor payment")
    selected_row = next(row for row in rows if row["id"] == selected)
    amount = st.number_input("Payment amount", min_value=0.01, step=0.01)
    allocation = st.number_input("Allocate to selected bill", min_value=0.01,
                                 max_value=max(0.01, to_dollars(selected_row["open_balance_cents"])),
                                 step=0.01)
    payment_id = st.selectbox("Payment account", [a.id for a in assets], format_func=asset_label)
    payment_date = st.date_input("Payment date", date.today())
    if st.button("Record payment"):
        try:
            record_vendor_payment(client_id, selected_row["vendor_id"], payment_date,
                                  to_cents(amount), payment_id,
                                  [{"bill_id": selected, "amount_cents": to_cents(allocation)}])
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()

credits = list_vendor_credits(client_id)
if credits:
    st.subheader("Open vendor credits")
    st.dataframe(pd.DataFrame([{"Payment": row["payment_id"], "Vendor": row["party_name"],
        "Credit": f"${to_dollars(row['open_credit_cents']):,.2f}"} for row in credits]),
        hide_index=True, width="stretch")
    credit_payment = st.selectbox("Vendor credit", [row["payment_id"] for row in credits])
    selected_credit = next(row for row in credits if row["payment_id"] == credit_payment)
    credit_bills = [row for row in rows
                    if row["vendor_id"] == selected_credit["vendor_id"]
                    and row["status"] in ("posted", "partially_paid")
                    and row["open_balance_cents"] > 0]
    if credit_bills:
        credit_bill = st.selectbox(
            "Apply vendor credit to bill", [row["id"] for row in credit_bills]
        )
        selected_credit_bill = next(row for row in credit_bills if row["id"] == credit_bill)
        maximum_credit = min(
            selected_credit["open_credit_cents"], selected_credit_bill["open_balance_cents"]
        )
        credit_amount = st.number_input(
            "Vendor credit amount", min_value=0.01,
            max_value=float(to_dollars(maximum_credit)), step=0.01,
        )
        earliest_credit_date = max(
            date.fromisoformat(selected_credit["payment_date"]),
            date.fromisoformat(selected_credit_bill["bill_date"]),
        )
        credit_application_date = st.date_input(
            "Vendor credit application date", max(date.today(), earliest_credit_date),
            min_value=earliest_credit_date,
        )
        if st.button("Apply vendor credit"):
            try:
                apply_vendor_credit(
                    credit_payment, credit_bill, to_cents(credit_amount),
                    credit_application_date,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.rerun()
    if st.button("Void vendor payment"):
        try:
            void_vendor_payment(credit_payment, date.today())
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()

if liabilities and assets:
    with st.expander("Record sales tax remittance"):
        remittance_tax_id = st.selectbox("Tax liability account", [a.id for a in liabilities])
        remittance_bank_id = st.selectbox("Bank account", [a.id for a in assets])
        remittance_amount = st.number_input("Remittance amount", min_value=0.01, step=0.01)
        remittance_date = st.date_input("Remittance date", date.today())
        remittance_memo = st.text_input("Remittance memo")
        if st.button("Record sales tax remittance"):
            try:
                record_sales_tax_remittance(client_id, remittance_tax_id, remittance_bank_id,
                                            to_cents(remittance_amount), remittance_date,
                                            remittance_memo)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.rerun()
