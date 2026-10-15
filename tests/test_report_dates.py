from datetime import date

from utils.report_dates import as_of_for_preset, period_for_preset


def test_period_for_preset_this_calendar_year_starts_on_january_first():
    today = date(2026, 2, 1)
    assert period_for_preset("This Calendar Year", today, 6) == (
        date(2026, 1, 1), today,
    )


def test_period_for_preset_rolling_windows_span_leap_day():
    today = date(2024, 3, 1)
    assert period_for_preset("Last 30 Days", today, 6) == (
        date(2024, 1, 31), today,
    )
    assert period_for_preset("Last 90 Days", today, 6) == (
        date(2023, 12, 2), today,
    )


def test_period_for_preset_custom_has_no_calculated_range():
    assert period_for_preset("Custom", date(2026, 2, 1), 6) is None


def test_as_of_for_preset_today_uses_supplied_date():
    today = date(2026, 2, 1)
    assert as_of_for_preset("Today", today, 6) == today


def test_as_of_for_preset_last_calendar_year_ends_on_december_thirty_first():
    assert as_of_for_preset("End of Last Calendar Year", date(2026, 2, 1), 6) == date(
        2025, 12, 31
    )


def test_as_of_for_preset_custom_has_no_calculated_date():
    assert as_of_for_preset("Custom", date(2026, 2, 1), 6) is None
