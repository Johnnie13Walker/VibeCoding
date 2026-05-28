"""Общие business-day helpers для отчётов Cloudbot."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from shared.time.moscow import MOSCOW_TZ


def _as_moscow_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=MOSCOW_TZ)
        return value.astimezone(MOSCOW_TZ)
    return datetime.combine(value, time.min, tzinfo=MOSCOW_TZ)


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return _as_moscow_datetime(value).date()
    return value


def _anchor_business_day(day: date) -> date:
    weekday = day.weekday()
    if weekday >= 5:
        return day - timedelta(days=weekday - 4)
    return day


def previous_business_day(day: date | datetime) -> date:
    candidate = _as_date(day) - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def current_business_week(now: date | datetime | None = None) -> tuple[date, date]:
    current_day = _anchor_business_day(_as_date(now or datetime.now(MOSCOW_TZ)))
    monday = current_day - timedelta(days=current_day.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def current_business_week_window(now: date | datetime | None = None) -> tuple[datetime, datetime]:
    week_start, week_end = current_business_week(now)
    start = datetime.combine(week_start, time.min, tzinfo=MOSCOW_TZ)
    end = datetime.combine(week_end + timedelta(days=1), time.min, tzinfo=MOSCOW_TZ)
    return start, end


def previous_business_week_window(now: date | datetime | None = None) -> tuple[datetime, datetime]:
    start, end = current_business_week_window(now)
    delta = timedelta(days=7)
    return start - delta, end - delta


def report_day_flags(dt: datetime | None, now: datetime | None = None) -> tuple[bool, bool]:
    """Возвращает флаги (сегодня, предыдущий рабочий день отчёта).

    Для weekday-run предыдущим рабочим днём считается прошлый business day.
    Для weekend/manual-run отчётный день якорится на пятницу.
    """

    if dt is None:
        return False, False

    point = _as_moscow_datetime(dt)
    current = _as_moscow_datetime(now or datetime.now(MOSCOW_TZ))
    actual_today = current.date() if current.weekday() < 5 else None
    report_day = previous_business_day(current.date()) if current.weekday() < 5 else _anchor_business_day(current.date())
    return (actual_today is not None and point.date() == actual_today, point.date() == report_day)
