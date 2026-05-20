from __future__ import annotations

from datetime import date

from sales_kpi_dashboard import config
from sales_kpi_dashboard.reader import BitrixReader

from .common import month_bounds, to_int

HEADER = [
    "date_calc",
    "employee_id",
    "employee_name",
    "calls_60s",
    "tasks_closed",
    "kp_sent",
    "meetings_first",
    "meetings_repeat",
    "deals_signed",
]

def compute(reader: BitrixReader, today: date) -> list[list[object]]:
    month_start, month_end = month_bounds(today)
    date_calc = today.isoformat()
    mop_users = reader.resolve_role_users(config.MOP_POSITION_REGEX)
    calls = reader.list_calls_in_period(month_start, month_end)
    meetings = reader.list_meetings_in_period(month_start, month_end)
    first_repeat = _first_repeat_by_user(meetings)

    rows = [HEADER]
    for user_id, user_name in sorted(mop_users.items(), key=lambda item: item[1]):
        user_calls_60 = [
            call
            for call in calls
            if to_int(call.get("PORTAL_USER_ID")) == user_id
            and to_int(call.get("CALL_DURATION")) >= 60
        ]
        first_count, repeat_count = first_repeat.get(user_id, (0, 0))
        rows.append(
            [
                date_calc,
                user_id,
                user_name,
                len(user_calls_60),
                reader.count_tasks_closed(user_id, month_start),
                reader.count_sp_items(
                    config.SP_KP_ENTITY_TYPE_ID,
                    config.SP_KP_SENT_STAGE_ID,
                    month_start,
                    user_id,
                ),
                first_count,
                repeat_count,
                reader.count_sp_items(
                    config.SP_CONTRACT_ENTITY_TYPE_ID,
                    config.SP_CONTRACT_SIGNED_STAGE_ID,
                    month_start,
                    user_id,
                ),
            ]
        )
    return rows


def _first_repeat_by_user(meetings: list[dict]) -> dict[int, tuple[int, int]]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for meeting in meetings:
        owner_key = (str(meeting.get("OWNER_TYPE_ID") or ""), str(meeting.get("OWNER_ID") or ""))
        grouped.setdefault(owner_key, []).append(meeting)

    counts: dict[int, list[int]] = {}
    for group in grouped.values():
        for index, meeting in enumerate(sorted(group, key=lambda row: str(row.get("CREATED") or ""))):
            user_id = to_int(meeting.get("CREATED_BY_ID"))
            if not user_id:
                continue
            user_counts = counts.setdefault(user_id, [0, 0])
            if index == 0:
                user_counts[0] += 1
            else:
                user_counts[1] += 1
    return {user_id: (values[0], values[1]) for user_id, values in counts.items()}
