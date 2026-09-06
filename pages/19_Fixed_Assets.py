import calendar
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from constants import AccountSubtype, AccountType
from database import init_database
from models.account import Account
from models.fixed_asset import FixedAsset, FixedAssetType
from money import to_cents, to_dollars
from services.fixed_assets import (
    depreciation_gl_tie_out, depreciation_roll_forward, dispose_asset,
    fixed_asset_register, run_depreciation,
)
from utils import icons
from utils.client_selector import render_client_selector
from utils.unlock import require_unlock


st.set_page_config(page_title="Fixed Assets", page_icon=icons.FIXED_ASSETS,
                   layout="wide")
require_unlock()
init_database()
client_id = render_client_selector()
st.title("Fixed Assets")
if not client_id:
    st.warning("Please select or create a client first.")
    st.stop()

accounts = Account.get_all(client_id)
account_by_id = {account.id: account for account in accounts}
asset_accounts = [a.id for a in accounts if a.type == AccountType.ASSET]
expense_accounts = [a.id for a in accounts if a.type == AccountType.EXPENSE]
types = FixedAssetType.get_all(client_id)
type_by_id = {asset_type.id: asset_type for asset_type in types}
assets = FixedAsset.get_all(client_id)

as_of = st.date_input("Register as of", value=date.today())
st.dataframe(pd.DataFrame([{
    "Asset": row["description"],
    "Type": type_by_id[row["fixed_asset_type_id"]].name,
    "Cost": to_dollars(row["cost_cents"]),
    "Accumulated depreciation": to_dollars(row["accumulated_depreciation_cents"]),
    "Book value": to_dollars(row["book_value_cents"]),
    "Status": row["status"],
} for row in fixed_asset_register(client_id, as_of)]), hide_index=True, width="stretch")

with st.expander("Depreciation roll-forward and GL tie-out"):
    start_date = st.date_input("Roll-forward from", value=as_of.replace(month=1, day=1))
    if start_date <= as_of:
        st.dataframe(pd.DataFrame([{
            "Account": account_by_id[row["account_id"]].name,
            "Opening": to_dollars(row["opening_cents"]),
            "Depreciation": to_dollars(row["depreciation_cents"]),
            "Disposal removals": to_dollars(row["disposals_cents"]),
            "Closing": to_dollars(row["closing_cents"]),
        } for row in depreciation_roll_forward(client_id, start_date, as_of)]),
            hide_index=True, width="stretch")
    else:
        st.warning("The start date must be on or before the register date.")
    st.dataframe(pd.DataFrame([{
        "Account": account_by_id[row["account_id"]].name,
        "Register": to_dollars(row["subledger_cents"]),
        "GL": to_dollars(row["gl_cents"]),
        "Difference": to_dollars(row["difference_cents"]),
    } for row in depreciation_gl_tie_out(client_id, as_of)]),
        hide_index=True, width="stretch")

with st.expander("Add asset type"):
    with st.form("add_asset_type", clear_on_submit=True):
        name = st.text_input("Name")
        asset_account = st.selectbox("Asset account", asset_accounts,
                                     format_func=lambda aid: account_by_id[aid].name)
        accumulated_account = st.selectbox(
            "Accumulated depreciation account", asset_accounts,
            format_func=lambda aid: account_by_id[aid].name)
        expense_account = st.selectbox(
            "Depreciation expense account", expense_accounts,
            format_func=lambda aid: account_by_id[aid].name)
        method = st.selectbox(
            "Method", ["straight_line", "declining_balance", "units_of_production"])
        convention = st.selectbox("Convention", ["full_month", "mid_month", "half_year"])
        life = st.number_input("Useful life (months)", min_value=1, value=60)
        rate = st.number_input("Annual rate (%)", min_value=0.01,
                               max_value=100.0, value=20.0)
        total_units = st.number_input("Lifetime units (production method)", min_value=1, value=1000)
        if st.form_submit_button("Add type"):
            try:
                FixedAssetType(
                    client_id=client_id, name=name,
                    asset_account_id=asset_account,
                    accumulated_depreciation_account_id=accumulated_account,
                    depreciation_expense_account_id=expense_account,
                    method=method,
                    effective_life_months=int(life) if method == "straight_line" else None,
                    annual_rate=rate / 100 if method == "declining_balance" else None,
                    convention=convention,
                    total_units=int(total_units) if method == "units_of_production" else None,
                ).save()
            except Exception as exc:
                st.error(str(exc))
            else:
                st.rerun()

if types:
    with st.expander("Add asset"):
        with st.form("add_asset", clear_on_submit=True):
            description = st.text_input("Description")
            type_id = st.selectbox("Asset type", list(type_by_id),
                                   format_func=lambda tid: type_by_id[tid].name)
            acquisition_date = st.date_input("Acquisition date", value=date.today())
            in_service_date = st.date_input("In-service date", value=date.today())
            cost = st.number_input("Cost", min_value=0.0, step=100.0)
            salvage = st.number_input("Salvage value", min_value=0.0, step=100.0)
            if st.form_submit_button("Add asset"):
                try:
                    FixedAsset(
                        client_id=client_id, fixed_asset_type_id=type_id,
                        description=description, acquisition_date=acquisition_date,
                        cost_cents=to_cents(cost),
                        salvage_value_cents=to_cents(salvage),
                        in_service_date=in_service_date,
                    ).save()
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.rerun()

registered = [asset for asset in assets if asset.status == "registered"]
if registered:
    st.subheader("Run depreciation")
    run_ids = st.multiselect(
        "Assets", [asset.id for asset in registered],
        format_func=lambda aid: next(a.description for a in registered if a.id == aid))
    today = date.today()
    default_period_end = today.replace(
        day=calendar.monthrange(today.year, today.month)[1]
    )
    period_end = st.date_input("Period end", value=default_period_end)
    run_seq = st.number_input("Correction number (0 for original)", min_value=0, value=0)
    st.caption("Each correction reverses the preceding run for the latest period, "
               "then posts its replacement.")
    units_produced = st.number_input("Units produced (production assets)", min_value=1, value=1)
    if st.button("Run selected"):
        errors = []
        for asset_id in run_ids:
            try:
                asset = next(a for a in registered if a.id == asset_id)
                production = type_by_id[asset.fixed_asset_type_id].method == "units_of_production"
                run_depreciation(asset_id, period_end, int(run_seq),
                                  int(units_produced) if production else None)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            st.error("; ".join(errors))
        else:
            st.rerun()

    st.subheader("Dispose asset")
    with st.form("dispose_asset"):
        disposal_id = st.selectbox(
            "Asset", [asset.id for asset in registered],
            format_func=lambda aid: next(a.description for a in registered if a.id == aid))
        disposal_date = st.date_input("Disposal date", value=date.today())
        proceeds = st.number_input("Proceeds", min_value=0.0, step=100.0)
        deposit_id = st.selectbox(
            "Deposit account", asset_accounts,
            format_func=lambda aid: account_by_id[aid].name)
        gain_loss_options = [a.id for a in accounts if a.subtype in (
            AccountSubtype.GAIN_ON_ASSET_DISPOSAL,
            AccountSubtype.LOSS_ON_ASSET_DISPOSAL,
        )]
        gain_loss_id = st.selectbox(
            "Gain/loss account", gain_loss_options or [None],
            format_func=lambda aid: account_by_id[aid].name if aid else "Add an account first")
        if not gain_loss_options:
            st.warning("Add a gain or loss on asset disposal account first.")
        if st.form_submit_button("Dispose", disabled=not gain_loss_options):
            try:
                dispose_asset(disposal_id, disposal_date, to_cents(proceeds),
                              deposit_id, gain_loss_id)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.rerun()
