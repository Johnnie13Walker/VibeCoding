from __future__ import annotations

from datetime import date
from typing import Protocol

from sales_kpi_dashboard import config
from sales_kpi_dashboard.periods import forecast, linear_trend
from sales_kpi_dashboard.reader import BitrixReader

from .common import (
    cumulative_by_day,
    days_passed,
    days_total,
    month_bounds,
    percent,
    safe_div,
    to_int,
)

HEADER = [
    "date_calc",
    "period",
    "employee_id",
    "employee_name",
    "naborov_per_day",
    "calls_120s_per_day",
    "meetings_fact",
    "meetings_plan",
    "meetings_trend",
    "meetings_forecast",
    "conv_nabor_to_call",
    "conv_call_to_meeting",
    "meetings_per_week_avg",
]


class PlanLike(Protocol):
    def get(self, key: str, default: float = 0.0) -> float: ...


def compute(reader: BitrixReader, plan: PlanLike, today: date) -> list[list[object]]:
    month_start, month_end = month_bounds(today)
    period = today.strftime("%Y-%m")
    date_calc = today.isoformat()
    total_days = days_total(today)
    passed_days = days_passed(today)
    tm_users = reader.resolve_role_users(config.TM_POSITION_REGEX)
    calls = reader.list_calls_in_period(month_start, month_end)
    meetings = reader.list_meetings_in_period(month_start, month_end)

    rows = [HEADER]
    all_calls = [call for call in calls if to_int(call.get("PORTAL_USER_ID")) in tm_users]
    all_meetings = _meetings_for_users(meetings, tm_users)
    rows.append(
        _build_row(
            date_calc,
            period,
            "ALL",
            "Все ТМ",
            all_calls,
            all_meetings,
            float(plan.get("Встречи_всего", 0.0)),
            passed_days,
            total_days,
        )
    )

    for user_id, user_name in sorted(tm_users.items(), key=lambda item: item[1]):
        user_calls = [call for call in calls if to_int(call.get("PORTAL_USER_ID")) == user_id]
        user_meetings = _meetings_for_users(meetings, {user_id: user_name})
        rows.append(
            _build_row(
                date_calc,
                period,
                user_id,
                user_name,
                user_calls,
                user_meetings,
                float(plan.get(f"Встречи_{user_id}", plan.get("Встречи_всего", 0.0))),
                passed_days,
                total_days,
            )
        )
    return rows


def _meetings_for_users(meetings: list[dict], users: dict[int, str]) -> list[dict]:
    user_ids = set(users)
    return [meeting for meeting in meetings if to_int(meeting.get("CREATED_BY_ID")) in user_ids]


def _build_row(
    date_calc: str,
    period: str,
    employee_id: int | str,
    employee_name: str,
    calls: list[dict],
    meetings: list[dict],
    meeting_plan: float,
    passed_days: int,
    total_days: int,
) -> list[object]:
    outgoing_calls = [call for call in calls if str(call.get("CALL_TYPE")) == "1"]
    calls_120 = [call for call in outgoing_calls if to_int(call.get("CALL_DURATION")) >= 120]
    meetings_fact = len(meetings)
    meetings_by_day = cumulative_by_day(meetings, "CREATED")
    return [
        date_calc,
        period,
        employee_id,
        employee_name,
        round(safe_div(len(outgoing_calls), passed_days), 2),
        round(safe_div(len(calls_120), passed_days), 2),
        meetings_fact,
        meeting_plan,
        round(linear_trend(meetings_by_day, total_days), 2),
        round(forecast(meeting_plan, meetings_fact, passed_days, total_days), 2),
        round(percent(len(calls_120), len(outgoing_calls)), 2),
        round(percent(meetings_fact, len(calls_120)), 2),
        round(safe_div(meetings_fact, weeks_passed_from_days(passed_days)), 2),
    ]


def weeks_passed_from_days(passed_days: int) -> float:
    return max(passed_days / 5, 1.0)
