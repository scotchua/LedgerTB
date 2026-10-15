from datetime import date, datetime

from utils.dates import display_date, long_date, long_datetime, short_date, slash_date


def test_long_date_uses_full_month_and_unpadded_day():
    assert long_date(date(2026, 3, 4)) == "March 4, 2026"


def test_short_date_uses_abbreviated_month_and_unpadded_day():
    assert short_date(date(2026, 3, 4)) == "Mar 4, 2026"


def test_slash_date_uses_unpadded_month_and_day():
    assert slash_date(date(2026, 3, 4)) == "3/4/2026"


def test_display_date_preserves_invalid_iso_text():
    assert display_date("2026-02-30", "DD/MM/YYYY") == "2026-02-30"


def test_display_date_pads_single_digits_and_early_years():
    value = date(42, 3, 4)
    assert display_date(value, "DD/MM/YYYY") == "04/03/0042"
    assert display_date(value, "YYYY/MM/DD") == "0042/03/04"
    assert display_date(value, "MM/DD/YYYY") == "03/04/0042"


def test_long_datetime_handles_midnight_noon_and_afternoon():
    assert long_datetime(datetime(2026, 3, 4, 0, 7)) == "March 4, 2026 at 12:07 AM"
    assert long_datetime(datetime(2026, 3, 4, 12, 7)) == "March 4, 2026 at 12:07 PM"
    assert long_datetime(datetime(2026, 3, 4, 15, 7)) == "March 4, 2026 at 3:07 PM"
