"""Close-oriented inventory register, movements, CSV import, and rollforward."""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import init_database
from models.account import Account
from models.client import Client
from money import to_dollars
from services.inventory import (
    create_item, inventory_rollforward, list_items, record_movement,
    record_movements_from_csv,
)
from utils.client_selector import render_client_selector
from utils.unlock import require_unlock


st.set_page_config(
    page_title="Inventory", page_icon=":material/inventory_2:", layout="wide"
)
require_unlock()
init_database()
client_id = render_client_selector()

st.title("Inventory")
st.caption(
    "A bounded period-end subledger for imported or manually entered movements, "
    "valuation adjustments, and reviewer-ready rollforwards."
)
if not client_id:
    st.warning("Please select or create a client first.")
    st.stop()

client = Client.get_by_id(client_id)
accounts = Account.get_all(client_id)
asset_accounts = [account for account in accounts if account.type == "Asset"]
expense_accounts = [account for account in accounts if account.type == "Expense"]
account_by_id = {account.id: account for account in accounts}

st.caption(f"Viewing: **{client.name}**")

with st.expander("Add inventory item"):
    if not asset_accounts or not expense_accounts:
        st.info("Add an inventory asset account and a COGS expense account first.")
    else:
        with st.form("add_inventory_item", clear_on_submit=True):
            sku = st.text_input("SKU")
            description = st.text_input("Description")
            inventory_account_id = st.selectbox(
                "Inventory asset account", [account.id for account in asset_accounts],
                format_func=lambda account_id: account_by_id[account_id].display_name(),
            )
            cogs_account_id = st.selectbox(
                "COGS account", [account.id for account in expense_accounts],
                format_func=lambda account_id: account_by_id[account_id].display_name(),
            )
            if st.form_submit_button("Add item", type="primary"):
                try:
                    create_item(
                        client_id, sku, description, inventory_account_id,
                        cogs_account_id,
                    )
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success("Inventory item added.")
                    st.rerun()

items = list_items(client_id)
if not items:
    st.info("Add an inventory item to begin tracking movements.")
    st.stop()

st.subheader("Item register")
st.dataframe(pd.DataFrame([{
    "SKU": item["sku"],
    "Description": item["description"],
    "Quantity on hand": item["quantity"],
    "Weighted-average unit cost": to_dollars(
        item["weighted_average_unit_cost_cents"]
    ),
    "Inventory value": to_dollars(item["value_cents"]),
} for item in items]), hide_index=True, width="stretch", column_config={
    "Weighted-average unit cost": st.column_config.NumberColumn(format="$%.2f"),
    "Inventory value": st.column_config.NumberColumn(format="$%.2f"),
})

item_by_id = {item["id"]: item for item in items}
item_id = st.selectbox(
    "Inventory item", list(item_by_id),
    format_func=lambda selected: (
        f"{item_by_id[selected]['sku']} — {item_by_id[selected]['description']}"
    ),
)

manual_tab, import_tab, report_tab = st.tabs([
    "Record movement", "Import CSV", "Rollforward",
])
with manual_tab:
    with st.form("record_inventory_movement"):
        movement_date = st.date_input("Movement date", value=date.today())
        movement_type = st.selectbox(
            "Movement type", ["purchase", "sale", "adjustment", "count"]
        )
        quantity = st.number_input(
            "Quantity", value=0.0,
            help="Use a negative quantity for a sale, shrinkage, or count reduction.",
        )
        unit_cost = st.number_input(
            "Unit cost ($; purchases or positive adjustments)", min_value=0.0,
            value=0.0,
            step=0.01, format="%.2f",
        )
        post_purchase = st.checkbox(
            "Post purchase journal entry",
            help="Leave off if the purchase was already posted manually elsewhere.",
        )
        default_offset = item_by_id[item_id]["cogs_account_id"]
        offset_account_id = st.selectbox(
            "Offset account",
            [account.id for account in accounts],
            index=[account.id for account in accounts].index(default_offset),
            format_func=lambda account_id: account_by_id[account_id].display_name(),
            help=(
                "Required for a posted purchase. Adjustments/counts default to COGS, "
                "but may use a shrinkage or adjustment account."
            ),
        )
        if st.form_submit_button("Record movement", type="primary"):
            try:
                result = record_movement(
                    item_id, movement_date, movement_type, quantity,
                    unit_cost_cents=(
                        round(unit_cost * 100)
                        if movement_type == "purchase"
                        or (movement_type in ("adjustment", "count") and quantity > 0)
                        else None
                    ),
                    post_journal_entry=(post_purchase if movement_type == "purchase" else False),
                    offset_account_id=(
                        offset_account_id
                        if movement_type in ("adjustment", "count") or post_purchase
                        else None
                    ),
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                message = "Movement recorded."
                if result["journal_entry_id"]:
                    message += f" Journal entry #{result['journal_entry_id']} posted."
                st.success(message)
                st.rerun()

with import_tab:
    st.markdown("**Expected CSV columns:** `date,quantity,unit_cost`")
    st.caption(
        "Use YYYY-MM-DD dates. Positive quantities are purchases and require a "
        "dollar unit cost; negative quantities are sales/reductions and leave unit_cost "
        "blank so the running weighted-average cost is used. Imports do not post journals."
    )
    upload = st.file_uploader("Movement CSV", type=["csv"])
    if st.button("Import movements", disabled=upload is None):
        try:
            imported = record_movements_from_csv(item_id, upload)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(f"Imported {len(imported)} movements.")
            st.rerun()

with report_tab:
    period_cols = st.columns(2)
    period_start = period_cols[0].date_input(
        "Period start", value=date(date.today().year, 1, 1)
    )
    period_end = period_cols[1].date_input("Period end", value=date.today())
    try:
        report = inventory_rollforward(item_id, period_start, period_end)
    except Exception as exc:
        st.error(str(exc))
    else:
        metrics = st.columns(4)
        metrics[0].metric("Opening quantity", report["opening_quantity"])
        metrics[1].metric("Additions", report["additions_quantity"])
        metrics[2].metric("Reductions", report["reductions_quantity"])
        metrics[3].metric("Adjustments", report["adjustments_quantity"])
        st.dataframe(pd.DataFrame([
            {
                "Movement": "Additions", "Quantity": report["additions_quantity"],
                "Value": to_dollars(report["additions_value_cents"]),
            },
            {
                "Movement": "Reductions", "Quantity": report["reductions_quantity"],
                "Value": to_dollars(report["reductions_value_cents"]),
            },
            {
                "Movement": "Adjustments", "Quantity": report["adjustments_quantity"],
                "Value": to_dollars(report["adjustments_value_cents"]),
            },
        ]), hide_index=True, width="stretch", column_config={
            "Value": st.column_config.NumberColumn(format="$%.2f"),
        })
        st.dataframe(pd.DataFrame([
            {
                "Point": "Opening", "Quantity": report["opening_quantity"],
                "Value": to_dollars(report["opening_value_cents"]),
            },
            {
                "Point": "Closing", "Quantity": report["closing_quantity"],
                "Value": to_dollars(report["closing_value_cents"]),
            },
        ]), hide_index=True, width="stretch", column_config={
            "Value": st.column_config.NumberColumn(format="$%.2f"),
        })
        if abs(report["quantity_check"]) < 0.000001:
            st.success("Quantity rollforward reconciles.")
        else:
            st.error(f"Quantity rollforward difference: {report['quantity_check']}")
