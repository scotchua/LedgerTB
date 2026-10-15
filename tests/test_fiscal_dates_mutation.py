from datetime import date

import pytest

from utils.fiscal_dates import (
    fiscal_year_bounds,
    prior_year_period,
    require_valid_range,
)


def test_fiscal_year_bounds_rejects_months_outside_calendar():
    for month in (0, 13):
        with pytest.raises(ValueError, match="Fiscal year-end month must be between 1 and 12"):
            fiscal_year_bounds(date(2026, 1, 15), month)
    assert fiscal_year_bounds(date(2026, 1, 15), 1) == (
        date(2025, 2, 1), date(2026, 1, 31)
    )


def test_fiscal_year_bounds_uses_next_year_for_leap_day():
    assert fiscal_year_bounds(date(2023, 3, 1), 2) == (
        date(2023, 3, 1), date(2024, 2, 29)
    )


def test_prior_year_period_rejects_inverted_dates():
    with pytest.raises(ValueError, match="Comparison period start date cannot be after"):
        prior_year_period(date(2026, 2, 1), date(2026, 1, 1))


def test_require_valid_range_rejects_inverted_dates_with_label():
    with pytest.raises(ValueError, match="Selected period start date cannot be after"):
        require_valid_range(date(2026, 2, 1), date(2026, 1, 1), "Selected period")


def test_require_valid_range_accepts_single_day():
    assert require_valid_range(date(2026, 1, 1), date(2026, 1, 1)) is None
