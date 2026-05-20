from __future__ import annotations

from datetime import date

from sales_kpi_dashboard.periods import forecast, linear_trend, working_days, working_days_passed


def test_working_days_excludes_weekends_and_holidays() -> None:
    days = working_days(2026, 1)
    assert date(2026, 1, 1) not in days
    assert date(2026, 1, 9) in days
    assert all(day.weekday() < 5 for day in days)


def test_working_days_passed_counts_current_day_if_working() -> None:
    assert working_days_passed(date(2026, 5, 12)) == 7


def test_linear_trend_extrapolates_cumulative_values() -> None:
    assert linear_trend({1: 2, 2: 4, 3: 6}, 10) == 20


def test_forecast_uses_plan_cumulative() -> None:
    assert forecast(plan=100, fact=30, days_passed=6, days_total=20) == 100
    assert forecast(plan=0, fact=30, days_passed=6, days_total=20) == 30
