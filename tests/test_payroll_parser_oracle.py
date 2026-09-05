import json
from pathlib import Path

import pytest

from database.connection import get_connection
from services.payroll_parsers import (
    ParserRefusal, detect_provider, parse_gusto_payroll_journal,
    parse_qbo_payroll_summary,
)
from services.payroll_recording import get_payroll_import_rows, stage_payroll_rows


FIXTURES = Path(__file__).parent / "fixtures" / "payroll"
PARSERS = {
    "gusto": parse_gusto_payroll_journal,
    "quickbooks": parse_qbo_payroll_summary,
}


def _fixture(name):
    return (FIXTURES / name).read_text()


def _batch_count():
    with get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM payroll_import_batches"
        ).fetchone()[0]


@pytest.mark.parametrize("provider", ["gusto", "quickbooks"])
def test_well_formed_fixture_matches_contract_and_stages_pending(client_id, provider):
    batch = PARSERS[provider](_fixture(f"{provider if provider == 'gusto' else 'qbo'}_likely.csv"))
    row = batch.rows[0]
    assert set(row) == {
        "employee_name_raw", "department_raw", "pay_period_start",
        "pay_period_end", "pay_date", "gross_pay_cents", "deductions",
        "employer_costs", "net_pay_cents", "raw_row", "status",
    }
    assert row["pay_date"] == ("2026-02-06" if provider == "gusto" else "2026-03-06")
    assert row["gross_pay_cents"] == 10000
    assert isinstance(row["employer_costs"], str)
    assert json.loads(row["employer_costs"])[0]["amount_cents"] == 765
    assert list(json.loads(row["raw_row"])) == sorted(json.loads(row["raw_row"]))
    batch_id = stage_payroll_rows(
        client_id, batch.provider, batch.source_report, "synthetic.csv", batch.rows,
    )
    staged = get_payroll_import_rows(client_id, batch_id)
    assert len(staged) == 1
    assert staged[0]["status"] == "pending"


@pytest.mark.parametrize("provider", ["gusto", "quickbooks"])
def test_unknown_column_refuses_atomically(client_id, provider):
    before = _batch_count()
    name = f"{provider if provider == 'gusto' else 'qbo'}_unknown.csv"
    with pytest.raises(ParserRefusal) as caught:
        PARSERS[provider](_fixture(name))
    assert caught.value.unknown_headers == ["Mystery Dollars"]
    assert "Mystery Dollars" in str(caught.value)
    assert provider in str(caught.value)
    after = _batch_count()
    assert after == before


@pytest.mark.parametrize("provider", ["gusto", "quickbooks"])
def test_malformed_amount_refuses_atomically(client_id, provider):
    before = _batch_count()
    name = f"{provider if provider == 'gusto' else 'qbo'}_malformed_amount.csv"
    with pytest.raises(ParserRefusal, match=r"INVALID_MONEY: row 1, field gross_pay") as caught:
        PARSERS[provider](_fixture(name))
    assert caught.value.malformed_rows == [1]
    after = _batch_count()
    assert after == before


@pytest.mark.parametrize("provider", ["gusto", "quickbooks"])
def test_bom_crlf_is_identical_to_plain(provider):
    name = f"{provider if provider == 'gusto' else 'qbo'}_likely.csv"
    plain = _fixture(name)
    transformed = "\ufeff" + plain.replace("\n", "\r\n")
    assert PARSERS[provider](transformed) == PARSERS[provider](plain)


def test_detect_provider_uses_header_only_and_canonical_is_none():
    assert detect_provider(_fixture("gusto_likely.csv")) == "gusto"
    assert detect_provider(_fixture("qbo_likely.csv")) == "quickbooks"
    canonical = (
        "employee_name,department,pay_period_start,pay_period_end,pay_date,"
        "gross_pay,deductions_json,net_pay\n"
    )
    assert detect_provider(canonical) is None


def test_guess_alias_sets_are_explicitly_accepted():
    gusto = parse_gusto_payroll_journal(_fixture("gusto_guess.csv"))
    qbo = parse_qbo_payroll_summary(_fixture("qbo_guess.csv"))
    assert json.loads(gusto.rows[0]["deductions"]) == [
        {"amount_cents": 1000, "label": "Benefits"}
    ]
    assert json.loads(qbo.rows[0]["deductions"]) == [
        {"amount_cents": 1000, "label": "Employee Deductions"}
    ]


def test_money_rounding_quoted_fields_and_missing_optionals():
    content = (
        "Employee,Pay Period Start,Pay Period End,Pay Date,Gross Pay,Benefits,"
        "Employer Taxes,Net Pay,Row Type\r\n"
        '"Comma, Fiction",2026-01-13,2026-01-31,2026-02-06,"$1,001.005",'
        "0,(7.65),1001.005,employee\r\n"
        'Total,,,,"$1,001.005",0,(7.65),1001.005,grand total\r\n'
    )
    row = parse_gusto_payroll_journal(content).rows[0]
    assert row["gross_pay_cents"] == 100100
    assert row["department_raw"] is None
    assert row["deductions"] == '[{"amount_cents":0,"label":"Benefits"}]'
    assert row["employer_costs"] == '[{"amount_cents":-765,"label":"Employer Taxes"}]'


def test_subtotals_pii_and_totals_are_validation_only():
    content = (
        "Employee,Department,Pay Period Start,Pay Period End,Pay Date,Gross Pay,"
        "Benefits,Employer Taxes,Net Pay,Row Type,SSN\n"
        "Nova Fiction,Cloud Lab,2026-01-13,2026-01-31,2026-02-06,60,6,4,54,employee,DROP\n"
        "Orbit Fiction,Cloud Lab,2026-01-13,2026-01-31,2026-02-06,40,4,3.65,36,employee,DROP\n"
        ",Cloud Lab,,,,100,10,7.65,90,department total,\n"
        "Total,,,,,100,10,7.65,90,grand total,\n"
    )
    rows = parse_gusto_payroll_journal(content).rows
    assert [row["employee_name_raw"] for row in rows] == [
        "Nova Fiction", "Orbit Fiction",
    ]
    assert all("SSN" not in row["raw_row"] and "DROP" not in row["raw_row"]
               for row in rows)


def test_empty_header_only_missing_duplicate_dates_and_total_mismatch():
    with pytest.raises(ParserRefusal, match="^EMPTY_FILE$"):
        parse_gusto_payroll_journal("")
    headers = "Employee,Pay Period Start,Pay Period End,Pay Date,Gross Pay,Net Pay"
    with pytest.raises(ParserRefusal, match="^NO_DATA_ROWS$"):
        parse_gusto_payroll_journal(headers + "\n")
    with pytest.raises(ParserRefusal, match="MISSING_REQUIRED_HEADER: net_pay"):
        parse_gusto_payroll_journal(headers.replace(",Net Pay", "") + "\nrow\n")
    duplicate = headers.replace("Employee,", "Employee,Employee Name,")
    with pytest.raises(ParserRefusal, match="DUPLICATE_HEADER: employee_name"):
        parse_gusto_payroll_journal(duplicate + "\nrow\n")
    ambiguous = (
        headers + ",Row Type\n"
        "Nova Fiction,03/04/2026,2026-03-31,2026-04-03,100,90,employee\n"
        "Total,,,,100,90,grand total\n"
    )
    with pytest.raises(ParserRefusal, match="INVALID_DATE: row 1, field pay_period_start"):
        parse_gusto_payroll_journal(ambiguous)
    mismatch = (
        headers + ",Row Type\n"
        "Nova Fiction,2026-01-13,2026-01-31,2026-02-06,100,90,employee\n"
        "Total,,,,100.01,90,grand total\n"
    )
    with pytest.raises(ParserRefusal, match="TOTAL_MISMATCH: grand total, gross_pay"):
        parse_gusto_payroll_journal(mismatch)
