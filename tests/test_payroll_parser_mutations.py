import pytest

from services.payroll_parsers import (
    ParsedBatch, ParserRefusal, parse_gusto_payroll_journal,
    parse_qbo_payroll_summary,
)


def _gusto_rows(start="2026-04-01", end="2026-04-15", pay="2026-04-16"):
    return (
        "Employee,Pay Period Start,Pay Period End,Pay Date,Gross Pay,Net Pay,Row Type\n"
        f"Aster Example,{start},{end},{pay},123.45,100.00,employee\n"
        "Total,,,,123.45,100.00,grand total\n"
    )


def _qbo_rows(start):
    return (
        "Employee,Pay Period Start,Pay Period End,Pay Date,Gross Pay,Net Pay,Type\n"
        f"Beryl Example,{start},2026-12-15,2026-12-16,80.00,75.00,employee\n"
        "Total,,,,80.00,75.00,total\n"
    )


def test_parsed_batch_getitem_returns_named_value():
    batch = ParsedBatch("gusto", "payroll_journal", [])
    assert batch["source_report"] == "payroll_journal"


def test_parser_refusal_preserves_unknown_headers():
    refusal = ParserRefusal("UNKNOWN_HEADER", unknown_headers=["Imaginary Column"])
    assert refusal.unknown_headers == ["Imaginary Column"]


def test_read_records_refuses_nul_byte():
    with pytest.raises(ParserRefusal, match="^INVALID_ENCODING: row 0, field file$"):
        parse_gusto_payroll_journal("\x00" + _gusto_rows())


@pytest.mark.parametrize("start", ["12/12/2026", "01/12/2026"])
def test_date_refuses_ambiguous_month_day(start):
    with pytest.raises(ParserRefusal, match="INVALID_DATE: row 1, field pay_period_start"):
        parse_qbo_payroll_summary(_qbo_rows(start))


def test_parse_ignores_trailing_empty_records():
    batch = parse_gusto_payroll_journal(_gusto_rows() + "\n\n")
    assert [row["employee_name_raw"] for row in batch.rows] == ["Aster Example"]


def test_parse_accepts_equal_period_end_and_pay_date():
    batch = parse_gusto_payroll_journal(_gusto_rows("2026-04-15", "2026-04-15", "2026-04-15"))
    assert batch.rows[0]["pay_period_start"] == batch.rows[0]["pay_date"]
