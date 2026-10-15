from datetime import date

import pytest

from models.client import Client
from models.department import Department
from models.payroll import Employee


def test_employee_get_all_filters_active_status(client_id):
    Employee(client_id=client_id, name="Aster Studio Worker",
             start_date=date(2027, 1, 3)).save()
    Employee(client_id=client_id, name="Birch Studio Worker",
             start_date=date(2027, 1, 4), status="terminated").save()

    assert [employee.name for employee in Employee.get_all(client_id, active_only=True)] == [
        "Aster Studio Worker"
    ]


def test_employee_save_returns_persisted_id(client_id):
    employee = Employee(client_id=client_id, name="Copper Studio Worker",
                        start_date=date(2027, 2, 3))

    saved_id = employee.save()

    assert saved_id == employee.id
    assert saved_id is not None


def test_employee_save_rejects_blank_name(client_id):
    employee = Employee(client_id=client_id, name="   ",
                        start_date=date(2027, 2, 4))

    with pytest.raises(ValueError, match="Employee name is required"):
        employee.save()


def test_employee_save_rejects_other_company_department(db):
    northstar_id = Client(name="Northstar Mosaic Ltd", entity_type="S-Corp",
                          fiscal_year_end_month=12).save(seed_accounts=False)
    cypress_id = Client(name="Cypress Paperworks Ltd", entity_type="S-Corp",
                         fiscal_year_end_month=12).save(seed_accounts=False)
    department = Department(client_id=cypress_id, name="Pattern Design")
    department.save()
    employee = Employee(client_id=northstar_id, name="Elm Studio Worker",
                        start_date=date(2027, 3, 5), department_id=department.id)

    with pytest.raises(ValueError, match="Department not found"):
        employee.save()


def test_employee_deactivate_persists_terminated_status(client_id):
    employee = Employee(client_id=client_id, name="Dune Studio Worker",
                        start_date=date(2027, 3, 1))
    employee.save()

    employee.deactivate()

    assert employee.status == "terminated"
    assert Employee.get_all(client_id)[0].status == "terminated"
