from datetime import date, datetime, timedelta, timezone

from src.timeutil import MSK, msk_day_utc_range, now_msk, prev_working_day
from src.timeutil import next_working_day


def test_now_msk_returns_aware_moscow_datetime():
    current = now_msk()

    assert current.tzinfo is not None
    assert current.tzinfo == MSK
    assert current.utcoffset() == timedelta(hours=3)


def test_msk_day_utc_range_covers_moscow_calendar_day():
    start, end = msk_day_utc_range(date(2026, 5, 29))

    assert start == datetime(2026, 5, 28, 21, 0, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 29, 20, 59, 59, tzinfo=timezone.utc)
    assert start < end
    assert end - start == timedelta(hours=23, minutes=59, seconds=59)


def test_prev_working_day_skips_weekend_from_monday():
    assert prev_working_day(date(2026, 6, 1)) == date(2026, 5, 29)


def test_prev_working_day_returns_previous_calendar_day_for_tuesday():
    assert prev_working_day(date(2026, 6, 2)) == date(2026, 6, 1)


def test_prev_working_day_handles_russian_new_year_holidays():
    assert prev_working_day(date(2026, 1, 12)) == date(2026, 1, 9)


def test_next_working_day_skips_weekend():
    assert next_working_day(date(2026, 5, 29)) == date(2026, 6, 1)
