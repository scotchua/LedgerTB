import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import init_database
from models.account import Account
from models.client import Client
from services.bank_feed import (
    create_bank_connection,
    disconnect_bank_connection,
    discover_remote_accounts,
    list_bank_connections,
    map_remote_account,
    sync_bank_feed,
)
from utils import icons
from utils.client_selector import render_client_selector
from utils.unlock import require_unlock


st.set_page_config(page_title="Bank Feeds", page_icon=icons.IMPORT, layout="wide")
require_unlock()
init_database()

client_id = render_client_selector()
st.title("Bank Feeds")
st.caption("Link SimpleFIN and send bank activity to Import Transactions for review.")

if not client_id:
    st.warning("Please create a client first in the Clients page.")
    st.stop()

client = Client.get_by_id(client_id)
st.caption(f"Viewing: **{client.name}**")

accounts = [
    account for account in Account.get_all(client_id, active_only=False)
    if account.type in ("Asset", "Liability")
]
connections = list_bank_connections(client_id)
connected_account_ids = {row["bank_account_id"] for row in connections}
available = [account for account in accounts if account.id not in connected_account_ids]

st.subheader("Linked accounts")
if not connections:
    st.info("No SimpleFIN accounts are linked for this client.")
for connection in connections:
    label = (
        f"{connection['account_number']} · {connection['account_name']}"
    )
    status_col, action_col = st.columns([3, 2])
    with status_col:
        st.markdown(f"**{label}**")
        st.caption(
            f"Last synced: {connection['last_synced_at'] or 'Never'}"
        )
    with action_col:
        if st.button("Sync Now", key=f"sync_bank_feed_{connection['id']}"):
            try:
                result = sync_bank_feed(client_id, connection["bank_account_id"])
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success(
                    f"Staged {len(result['rows'])} transaction(s) for import review."
                )
                if result["unmapped_count"]:
                    st.warning(
                        "Not imported until mapped: "
                        + ", ".join(result["unmapped_accounts"])
                    )
                st.rerun()
        if st.button("Disconnect", key=f"disconnect_bank_feed_{connection['id']}"):
            try:
                disconnect_bank_connection(client_id, connection["id"])
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success("SimpleFIN connection disconnected.")
                st.rerun()

    with st.expander(f"Map remote accounts for {label}"):
        remote_accounts = []
        if st.button(
            "Discover remote accounts",
            key=f"discover_remote_{connection['id']}",
        ):
            try:
                remote_accounts = discover_remote_accounts(
                    client_id, connection["bank_account_id"],
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.session_state[f"remote_accounts_{connection['id']}"] = (
                    remote_accounts
                )
        remote_accounts = st.session_state.get(
            f"remote_accounts_{connection['id']}", remote_accounts,
        )
        for remote in remote_accounts:
            local_id = st.selectbox(
                f"Ledger account for {remote['name']}",
                options=[account.id for account in accounts],
                format_func=lambda account_id: next(
                    account.display_name() for account in accounts
                    if account.id == account_id
                ),
                key=f"remote_mapping_{connection['id']}_{remote['id']}",
            )
            if st.button(
                f"Map {remote['name']}",
                key=f"map_remote_{connection['id']}_{remote['id']}",
            ):
                try:
                    map_remote_account(
                        client_id, connection["id"], remote["id"],
                        remote["name"], local_id,
                    )
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Mapped {remote['name']}.")
                    st.rerun()

st.divider()
st.subheader("Link a SimpleFIN account")
st.caption(
    "Create a one-time setup token in SimpleFIN. LedgerTB exchanges it once "
    "and stores the permanent credential in this machine's credential vault."
)
if not available:
    st.info("Every eligible account is already linked.")
else:
    account_by_id = {account.id: account for account in available}
    with st.form("link_simplefin"):
        bank_account_id = st.selectbox(
            "Ledger account",
            options=list(account_by_id),
            format_func=lambda account_id: account_by_id[account_id].display_name(),
        )
        setup_token = st.text_area(
            "SimpleFIN setup token",
            height=100,
            help="The setup token is single-use and is not retained by LedgerTB.",
        )
        submitted = st.form_submit_button("Link account", type="primary")
    if submitted:
        try:
            create_bank_connection(client_id, bank_account_id, setup_token)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success("SimpleFIN account linked.")
            st.rerun()
