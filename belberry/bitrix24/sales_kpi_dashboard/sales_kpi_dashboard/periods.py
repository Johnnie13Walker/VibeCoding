from __future__ import annotations

import calendar
from datetime import date

RU_HOLIDAYS_2026: set[date] = {
    date(2026, 1, 1),
    date(2026, 1, 2),
    date(2026, 1, 3),
    date(2026, 1, 4),
    date(2026, 1, 5),
    date(2026, 1, 6),
    date(2026, 1, 7),
    date(2026, 1, 8),
    date(2026, 2, 23),
    date(2026, 3, 8),
    date(2026, 5, 1),
    date(2026, 5, 9),
    date(2026, 6, 12),
    date(2026, 11, 4),
}


def working_days(year: int, month: int) -> list[date]:
    _, days_in_month = calendar.monthrange(year, month)
    days = [date(year, month, day) for day in range(1, days_in_month + 1)]
    return [day for day in days if day.weekday() < 5 and day not in RU_HOLIDAYS_2026]


def working_days_passed(today: date) -> int:
    return sum(1 for day in working_days(today.year, today.month) if day <= today)


def linear_trend(values_by_day: dict[int, float], days_total: int) -> float:
    points = sorted((day, value) for day, value in values_by_day.items())
    if not points:
        return 0.0
    if len(points) == 1:
        return float(points[0][1])

    n = len(points)
    sum_x = sum(day for day, _ in points)
    sum_y = sum(value for _, value in points)
    sum_xx = sum(day * day for day, _ in points)
    sum_xy = sum(day * value for day, value in points)
    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        return float(points[-1][1])

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    return float(intercept + slope * days_total)


def forecast(plan: float, fact: float, days_passed: int, days_total: int) -> float:
    if plan == 0 or days_passed == 0 or days_total == 0:
        return fact
    plan_cumulative = plan * (days_passed / days_total)
    if plan_cumulative == 0:
        return fact
    return plan * (fact / plan_cumulative)
