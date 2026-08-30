import sys
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import init_database
from models.account import Account
from models.department import Department
from models.payroll import Employee, PayRun, PayStub
from money import to_cents
from services.payroll_recording import (
    accept_payroll_batch, add_pay_stub, create_pay_run, dismiss_payroll_row,
    get_payroll_import_rows, parse_canonical_payroll_csv, post_pay_run,
    stage_payroll_rows, update_payroll_import_row,
)
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

employees_tab, runs_tab, import_tab = st.tabs(["Employees", "Pay Runs", "Import"])

with employees_tab:
    st.subheader("Departments")
    departments = Department.get_all(client_id)
    if departments:
        st.write(", ".join(department.name for department in departments))
    else:
        st.info("No departments recorded yet.")
    with st.form("add_department"):
        department_name = st.text_input("Department name")
        if st.form_submit_button("Add department"):
            try:
                Department(client_id=client_id, name=department_name).save()
                st.success("Department added.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not add department: {exc}")

    st.subheader("Employees")
    department_by_id = {department.id: department for department in departments}
    employees = Employee.get_all(client_id)
    if employees:
        for employee in employees:
            cols = st.columns([3, 2, 2, 2, 1])
            cols[0].write(employee.name)
            cols[1].write(employee.start_date.isoformat())
            cols[2].write(employee.status.title())
            department_options = [None, *department_by_id]
            selected_department = cols[3].selectbox(
                "Department", department_options,
                format_func=lambda item: department_by_id[item].name if item else "None",
                index=department_options.index(employee.department_id),
                key=f"employee_department_{employee.id}", label_visibility="collapsed",
            )
            if selected_department != employee.department_id:
                employee.department_id = selected_department
                employee.save()
                st.rerun()
            if employee.status == "active" and cols[4].button(
                "Deactivate", key=f"deactivate_employee_{employee.id}"
            ):
                employee.deactivate()
                st.rerun()
    else:
        st.info("No employees recorded yet.")

    with st.form("add_employee"):
        employee_name = st.text_input("Employee name")
        employee_start = st.date_input("Start date", value=date.today())
        employee_department = st.selectbox(
            "Department", [None, *department_by_id],
            format_func=lambda item: department_by_id[item].name if item else "None",
        )
        if st.form_submit_button("Add employee", type="primary"):
            try:
                Employee(client_id=client_id, name=employee_name,
                         start_date=employee_start,
                         department_id=employee_department).save()
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
        stub_employee_ids = {stub.employee_id for stub in stubs}
        employees_for_run = {
            employee.id: employee for employee in Employee.get_all(client_id)
            if employee.id in stub_employee_ids
        }
        used_department_names = sorted({
            department_by_id[employee.department_id].name
            for employee in employees_for_run.values()
            if employee.department_id in department_by_id
        })
        needs_fallback = any(
            employee.department_id not in department_by_id
            for employee in employees_for_run.values()
        )
        if accounts:
            with st.form(f"post_run_{selected_id}"):
                st.markdown("**Posting accounts**")
                wage_accounts = {
                    name: st.selectbox(
                        f"{name} wages account", options=list(account_by_id),
                        format_func=lambda item: account_by_id[item].display_name(),
                        key=f"wage_account_{selected_id}_{name}",
                    ) for name in used_department_names
                }
                default_wages_account = None
                if needs_fallback:
                    default_wages_account = st.selectbox(
                        "Default wages account (required)", options=list(account_by_id),
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
                        entry = post_pay_run(
                            selected_id, wage_accounts, default_wages_account,
                            cash_account, deduction_accounts,
                        )
                        st.success(f"Pay run posted as journal entry {entry.id}.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not post pay run: {exc}")
    else:
        st.success(f"Posted as journal entry {selected_run.journal_entry_id}.")

with import_tab:
    st.subheader("Import provider payroll")
    st.caption(
        "Gusto and QuickBooks parsers arrive next after real sample exports are "
        "available. For now, upload the canonical pre-parsed CSV."
    )
    st.code(
        "employee_name,department,pay_period_start,pay_period_end,pay_date,"
        "gross_pay,deductions_json,net_pay"
    )
    upload = st.file_uploader("Canonical payroll CSV", type=["csv"])
    provider = st.selectbox("Source provider", ["gusto", "quickbooks"])
    source_report = st.text_input("Source report", value="Canonical payroll export")
    if upload and st.button("Stage payroll rows", type="primary"):
        try:
            parsed_rows = parse_canonical_payroll_csv(upload.getvalue().decode("utf-8-sig"))
            batch_id = stage_payroll_rows(
                client_id, provider, source_report, upload.name, parsed_rows,
            )
            st.session_state["payroll_import_batch_id"] = batch_id
            st.success(f"Staged payroll batch {batch_id}.")
            st.rerun()
        except Exception as exc:
            st.error(f"Could not stage payroll import: {exc}")

    staged_rows = get_payroll_import_rows(client_id)
    if staged_rows:
        batch_ids = sorted({row["batch_id"] for row in staged_rows}, reverse=True)
        selected_batch = st.selectbox("Import batch", batch_ids)
        rows = [row for row in staged_rows if row["batch_id"] == selected_batch]
        employees = Employee.get_all(client_id)
        employee_by_id = {employee.id: employee for employee in employees}
        departments = Department.get_all(client_id)
        department_by_id = {department.id: department for department in departments}
        for row in rows:
            st.write(
                f"{row['employee_name_raw']} · {row['pay_date']} · "
                f"${row['gross_pay_cents'] / 100:,.2f} · {row['status'].title()}"
            )
            if row["status"] == "pending":
                cols = st.columns([3, 3, 2])
                employee_options = [None, *employee_by_id]
                employee_id = cols[0].selectbox(
                    "Matched employee", employee_options,
                    format_func=lambda item: employee_by_id[item].name if item else "Unmatched",
                    index=employee_options.index(row["matched_employee_id"]),
                    key=f"import_employee_{row['id']}",
                )
                department_options = [None, *department_by_id]
                department_id = cols[1].selectbox(
                    "Matched department", department_options,
                    format_func=lambda item: department_by_id[item].name if item else "None",
                    index=department_options.index(row["matched_department_id"]),
                    key=f"import_department_{row['id']}",
                )
                if (employee_id != row["matched_employee_id"] or
                        department_id != row["matched_department_id"]):
                    update_payroll_import_row(row["id"], employee_id, department_id)
                    st.rerun()
                reason = cols[2].text_input("Dismissal reason", key=f"reason_{row['id']}")
                if cols[2].button("Dismiss", key=f"dismiss_{row['id']}"):
                    try:
                        dismiss_payroll_row(row["id"], reason)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not dismiss row: {exc}")
        if all(row["status"] == "pending" for row in rows):
            if st.button("Accept batch as draft pay run", type="primary"):
                try:
                    run = accept_payroll_batch(selected_batch)
                    st.session_state["payroll_run_id"] = run.id
                    st.success(f"Created draft pay run {run.id}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not accept payroll import: {exc}")
    else:
        st.info("No payroll imports staged yet.")
