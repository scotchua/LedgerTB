from utils.statement_format import statement_amount


def test_statement_amount_parenthesizes_fractional_negative_values():
    assert statement_amount(-0.5) == "(0.50)"
    assert statement_amount(-0.5, value_format="percent") == "(0.5%)"


def test_statement_amount_keeps_positive_fraction_unparenthesized():
    assert statement_amount(0.5) == "0.50"


def test_statement_amount_groups_large_percent_values():
    assert statement_amount(1234.5, value_format="percent") == "1,234.5%"
