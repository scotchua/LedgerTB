import sys
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import init_database
from models.account import Account
from models.payroll import Employee, PayRun, PayStub
from money import to_cents
from services.payroll_recording import add_pay_stub, create_pay_run, post_pay_run
from utils.client_selector import render_client_selector
from utils.unlock import require_unlock


st.set_page_config(page_title="Payroll Recording", page_icon="🧾", layout="wide")
require_unlock()
init_database()
client_id = render_client_selector()

st.title("Payroll Recording")
st.caption(
    "Record completed payroll figures from your payroll provider. "
    "LedgerTB does not calculate payroll, file forms, or send payments."
)

if not client_id:
    st.warning("Please create a client first in the Clients page.")
    st.page_link("pages/0_Clients.py", label="Go to Clients →")
    st.stop()

employees_tab, runs_tab = st.tabs(["Employees", "Pay Runs"])

with employees_tab:
    st.subheader("Employees")
    employees = Employee.get_all(client_id)
    if employees:
        for employee in employees:
            cols = st.columns([3, 2, 2, 1])
            cols[0].write(employee.name)
            cols[1].write(employee.start_date.isoformat())
            cols[2].write(employee.status.title())
            if employee.status == "active" and cols[3].button(
                "Deactivate", key=f"deactivate_employee_{employee.id}"
            ):
                employee.deactivate()
                st.rerun()
    else:
        st.info("No employees recorded yet.")

    with st.form("add_employee"):
        employee_name = st.text_input("Employee name")
        employee_start = st.date_input("Start date", value=date.today())
        if st.form_submit_button("Add employee", type="primary"):
            try:
                Employee(client_id=client_id, name=employee_name,
                         start_date=employee_start).save()
                st.success("Employee added.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not add employee: {exc}")

with runs_tab:
    st.subheader("Pay Runs")
    st.caption("Enter only figures already provided by your payroll source.")
    with st.form("create_pay_run"):
        col1, col2, col3 = st.columns(3)
        period_start = col1.date_input("Period start", value=date.today())
        period_end = col2.date_input("Period end", value=date.today())
        pay_date = col3.date_input("Pay date", value=date.today())
        if st.form_submit_button("Create draft pay run", type="primary"):
            try:
                run = create_pay_run(client_id, period_start, period_end, pay_date)
                st.session_state["payroll_run_id"] = run.id
                st.success("Draft pay run created.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not create pay run: {exc}")

    runs = PayRun.get_all(client_id)
    if not runs:
        st.info("No pay runs recorded yet.")
        st.stop()
    run_by_id = {run.id: run for run in runs}
    selected_id = st.selectbox(
        "Pay run", options=list(run_by_id),
        format_func=lambda run_id: (
            f"{run_by_id[run_id].pay_date.isoformat()} · "
            f"{run_by_id[run_id].status.title()} · Run {run_id}"
        ), index=(list(run_by_id).index(st.session_state["payroll_run_id"])
                  if st.session_state.get("payroll_run_id") in run_by_id else 0),
        key="payroll_run_selection",
    )
    selected_run = run_by_id[selected_id]
    stubs = PayStub.get_all(selected_id)
    st.write(f"Recorded pay stubs: {len(stubs)}")

    if selected_run.status == "draft":
        active_employees = Employee.get_all(client_id, active_only=True)
        if active_employees:
            employee_by_id = {employee.id: employee for employee in active_employees}
            with st.form(f"add_stub_{selected_id}"):
                employee_id = st.selectbox(
                    "Employee", options=list(employee_by_id),
                    format_func=lambda item: employee_by_id[item].name,
                )
                gross = st.number_input("Gross pay", min_value=0.0, step=0.01)
                deduction_text = st.text_area(
                    "Deductions (one per line: label, amount)",
                    placeholder="Federal withholding, 125.00\nRetirement, 50.00",
                )
                net = st.number_input("Net pay", min_value=0.0, step=0.01)
                if st.form_submit_button("Add pay stub"):
                    try:
                        deductions = []
                        for line in deduction_text.splitlines():
                            if not line.strip():
                                continue
                            label, amount = line.rsplit(",", 1)
                            deductions.append({"label": label.strip(),
                                               "amount_cents": to_cents(amount.strip())})
                        add_pay_stub(selected_id, employee_id, to_cents(gross),
                                     deductions, to_cents(net))
                        st.success("Pay stub recorded.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not add pay stub: {exc}")
        else:
            st.info("Add an active employee before recording a pay stub.")

        accounts = Account.get_all(client_id)
        account_by_id = {account.id: account for account in accounts}
        labels = sorted({item["label"] for stub in stubs for item in stub.deductions})
        if accounts:
            with st.form(f"post_run_{selected_id}"):
                st.markdown("**Posting accounts**")
                wages_account = st.selectbox(
                    "Wages or salary expense account", options=list(account_by_id),
                    format_func=lambda item: account_by_id[item].display_name(),
                )
                cash_account = st.selectbox(
                    "Cash or clearing account", options=list(account_by_id),
                    format_func=lambda item: account_by_id[item].display_name(),
                )
                deduction_accounts = {
                    label: st.selectbox(
                        f"{label} liability account", options=list(account_by_id),
                        format_func=lambda item: account_by_id[item].display_name(),
                        key=f"deduction_account_{selected_id}_{label}",
                    ) for label in labels
                }
                if st.form_submit_button("Post pay run", type="primary"):
                    try:
                        entry = post_pay_run(selected_id, wages_account,
                                             cash_account, deduction_accounts)
                        st.success(f"Pay run posted as journal entry {entry.id}.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not post pay run: {exc}")
    else:
        st.success(f"Posted as journal entry {selected_run.journal_entry_id}.")
