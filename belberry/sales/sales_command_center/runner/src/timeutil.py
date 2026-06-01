from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from workalendar.europe import Russia

MSK = ZoneInfo("Europe/Moscow")


def now_msk() -> datetime:
    return datetime.now(MSK)


def msk_day_utc_range(d: date) -> tuple[datetime, datetime]:
    start_msk = datetime.combine(d, time(0, 0, 0), tzinfo=MSK)
    end_msk = datetime.combine(d, time(23, 59, 59), tzinfo=MSK)
    return start_msk.astimezone(timezone.utc), end_msk.astimezone(timezone.utc)


def prev_working_day(d: date | None = None) -> date:
    calendar = Russia()
    current = (d or now_msk().date()) - timedelta(days=1)

    while not calendar.is_working_day(current):
        current -= timedelta(days=1)

    return current


def next_working_day(d: date | None = None) -> date:
    calendar = Russia()
    current = (d or now_msk().date()) + timedelta(days=1)

    while not calendar.is_working_day(current):
        current += timedelta(days=1)

    return current
