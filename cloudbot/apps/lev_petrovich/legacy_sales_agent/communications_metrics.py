"""Live-коммуникации для Sales Copilot: Bitrix calls + Wazzup webhook archive."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Mapping

from cloudbot.business_day import MOSCOW_TZ, previous_business_day
from cloudbot.providers.bitrix.bitrix_sales_adapter import BitrixSalesAdapter
from cloudbot.providers.bitrix_provider import BitrixAPIError
from cloudbot.providers.wazzup_provider import WazzupProvider

from .sales_team_scope import (
    infer_role as _infer_role,
    manager_name as _manager_name,
    normalize_name as _normalize_name,
    resolve_sales_team_filter,
    role_marker as _role_marker,
)
IGNORED_CHAT_TYPES = {"telegroup"}


def _thresholds(env: Mapping[str, Any]) -> dict[str, int]:
    def _env_int(key: str, default: int) -> int:
        try:
            return int(str(env.get(key) or "").strip() or default)
        except ValueError:
            return default

    return {
        "stale_communication_days": _env_int("SALES_STALE_COMMUNICATION_DAYS", 14),
        "overdue_tasks_limit": 1,
        "missing_next_step_limit": 3,
        "lost_deals_limit": 2,
        "late_stage_stuck_limit": 2,
        "telemarketing_min_dials": 40,
    }


def _daily_window(now: datetime) -> tuple[datetime, datetime]:
    report_day = previous_business_day(now.date())
    period_start = datetime.combine(report_day, time.min, tzinfo=MOSCOW_TZ)
    return period_start, period_start + timedelta(days=1)


def _as_moscow_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(MOSCOW_TZ)
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOSCOW_TZ)
    return parsed.astimezone(MOSCOW_TZ)


def _activity_time(item: Mapping[str, Any]) -> datetime | None:
    for key in ("start_time", "created_at", "last_updated_at"):
        resolved = _as_moscow_dt(item.get(key))
        if resolved is not None:
            return resolved
    return None


def _build_user_lookup(users_by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for user_id, user in users_by_id.items():
        normalized = _normalize_name(_manager_name(user))
        if normalized and normalized not in result:
            result[normalized] = str(user_id)
        for candidate in (
            user.get("full_name"),
            user.get("name"),
            " ".join(
                part
                for part in (
                    str(user.get("name") or "").strip(),
                    str(user.get("last_name") or "").strip(),
                )
                if part
            ),
            " ".join(
                part
                for part in (
                    str(user.get("last_name") or "").strip(),
                    str(user.get("name") or "").strip(),
                )
                if part
            ),
        ):
            normalized = _normalize_name(candidate)
            if normalized and normalized not in result:
                result[normalized] = str(user_id)
    return result


def _manager_rows_base(
    snapshot: Mapping[str, Any],
    *,
    department_filter: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Mapping[str, Any]], dict[str, str]]:
    users_by_id = {
        str(user_id): user
        for user_id, user in dict(snapshot.get("responsibles") or {}).items()
        if str(user_id).strip()
    }
    departments_by_id = {
        str(item.get("id") or "").strip(): item
        for item in (snapshot.get("departments") or [])
        if str(item.get("id") or "").strip()
    }
    rows: dict[str, dict[str, Any]] = {}
    for manager_id in department_filter.get("allowlist_users") or []:
        manager_key = str(manager_id).strip()
        if not manager_key:
            continue
        user = users_by_id.get(manager_key) or {"id": manager_key, "full_name": manager_key}
        rows[manager_key] = {
            "manager_id": manager_key,
            "manager_name": _manager_name(user),
            "employee_role": _infer_role(user, departments_by_id),
            "total_known": 0,
            "missing_next_step_count": 0,
            "stale_communication_count": 0,
            "late_stage_stuck_count": 0,
            "overdue_tasks_count": 0,
            "max_days_overdue": 0,
            "lost_deals_yesterday_count": 0,
            "dials": 0,
            "normal_calls": 0,
            "messenger_dialogs": 0,
            "messenger_messages": 0,
            "outgoing_messages": 0,
            "incoming_messages": 0,
            "connect_rate": None,
            "low_connect": False,
            "low_activity": False,
            "no_activity": False,
            "_dialog_keys": set(),
        }
    return rows, users_by_id, _build_user_lookup(users_by_id)


def _apply_analysis_signals(
    rows: dict[str, dict[str, Any]],
    analysis: Mapping[str, Any] | None,
    *,
    period_start: datetime | None,
    period_end: datetime | None,
    thresholds: Mapping[str, int],
) -> None:
    if analysis is None:
        return

    stale_days = int(thresholds.get("stale_communication_days") or 14)
    late_stage_limit = 5
    for deal in analysis.get("active_deals") or []:
        manager_id = str(deal.get("assigned_id") or "").strip()
        row = rows.get(manager_id)
        if row is None:
            continue
        if deal.get("missing_next_step"):
            row["missing_next_step_count"] += 1
        if int(deal.get("communication_gap_days") or 0) >= stale_days:
            row["stale_communication_count"] += 1
        if bool(deal.get("late_stage")) and int(deal.get("inactive_days") or 0) >= late_stage_limit:
            row["late_stage_stuck_count"] += 1

    lost_items: list[Mapping[str, Any]]
    if period_start is None or period_end is None:
        lost_items = list(analysis.get("lost_deals_yesterday") or [])
    else:
        lost_items = [
            item
            for item in (analysis.get("closed_deals") or [])
            if item.get("lost") and isinstance(item.get("moved_at"), datetime) and period_start <= item.get("moved_at") < period_end
        ]
    for item in lost_items:
        manager_id = str(item.get("assigned_id") or "").strip()
        row = rows.get(manager_id)
        if row is not None:
            row["lost_deals_yesterday_count"] += 1

    for item in analysis.get("overdue_deal_tasks_by_manager") or []:
        manager_id = str(item.get("manager_id") or "").strip()
        if not manager_id:
            manager_name = _normalize_name(item.get("manager_name"))
            manager_id = next(
                (
                    candidate_id
                    for candidate_id, row in rows.items()
                    if _normalize_name(row.get("manager_name")) == manager_name
                ),
                "",
            )
        row = rows.get(manager_id)
        if row is None:
            continue
        row["overdue_tasks_count"] = int(item.get("count") or 0)
        row["max_days_overdue"] = int(item.get("max_days_overdue") or 0)


def _fetch_call_stats(
    env: Mapping[str, Any],
    *,
    period_start: datetime,
    period_end: datetime,
    rows: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    period_days = max((period_end - period_start).days, 1)
    limit = max(500, period_days * 600)
    try:
        adapter = BitrixSalesAdapter.from_env(env)
        activities = adapter.get_call_activities(
            limit=limit,
            filter_params={
                ">=CREATED": period_start.isoformat(),
                "<CREATED": period_end.isoformat(),
            },
        )
    except BitrixAPIError as error:
        return (
            {"available": False, "source": "crm.activity.list", "error": error.message},
            [f"Звонки Bitrix недоступны: {error.message}"],
        )

    counted = 0
    for item in activities:
        at = _activity_time(item)
        if at is None or at < period_start or at >= period_end:
            continue
        manager_id = str(item.get("responsible_id") or item.get("author_id") or "").strip()
        row = rows.get(manager_id)
        if row is None:
            continue
        row["dials"] += 1
        if int(item.get("duration_sec") or 0) >= 60:
            row["normal_calls"] += 1
        counted += 1

    limitations: list[str] = []
    if len(activities) >= limit:
        limitations.append(f"Лимит call-activity выборки достигнут ({limit}); возможна недосчитанная часть хвоста.")

    return (
        {
            "available": True,
            "source": "crm.activity.list",
            "fetched": len(activities),
            "counted": counted,
        },
        limitations,
    )


def _resolve_direct_manager_id(
    author_id: str | None,
    author_name: str,
    *,
    allowlist: set[str],
    user_lookup: Mapping[str, str],
) -> str:
    candidate_id = str(author_id or "").strip()
    if candidate_id and candidate_id in allowlist:
        return candidate_id
    candidate_id = user_lookup.get(_normalize_name(author_name)) or ""
    return candidate_id if candidate_id in allowlist else ""


def _fetch_messenger_stats(
    env: Mapping[str, Any],
    *,
    period_start: datetime,
    period_end: datetime,
    rows: dict[str, dict[str, Any]],
    users_by_id: Mapping[str, Mapping[str, Any]],
    user_lookup: Mapping[str, str],
) -> tuple[dict[str, Any], list[str]]:
    provider = WazzupProvider.from_env(env)
    archive_files = provider._archive_files()
    if not archive_files:
        return (
            {"available": False, "source": "webhook_archive", "error": "archive_missing"},
            ["Wazzup webhook archive не найден в BITRIX_APP_STATE_DIR."],
        )

    allowlist = set(rows.keys())
    all_messages = provider.list_archive_messages()
    chat_owner_map: dict[tuple[str, str, str], str] = {}
    counted_messages = 0
    counted_dialogs: set[tuple[str, str, str]] = set()

    for message in all_messages:
        direct_manager_id = _resolve_direct_manager_id(
            message.author_id,
            message.author_name,
            allowlist=allowlist,
            user_lookup=user_lookup,
        )
        if message.is_echo and direct_manager_id:
            chat_owner_map[message.chat_key] = direct_manager_id

        if message.chat_type in IGNORED_CHAT_TYPES:
            continue
        if message.date_time < period_start or message.date_time >= period_end:
            continue

        manager_id = direct_manager_id or chat_owner_map.get(message.chat_key) or ""
        row = rows.get(manager_id)
        if row is None:
            continue

        row["messenger_messages"] += 1
        if message.is_echo:
            row["outgoing_messages"] += 1
        else:
            row["incoming_messages"] += 1
        row["_dialog_keys"].add(message.chat_key)
        counted_messages += 1
        counted_dialogs.add(message.chat_key)

    return (
        {
            "available": True,
            "source": "webhook_archive",
            "payloads": len(archive_files),
            "messages": counted_messages,
            "dialogs": len(counted_dialogs),
        },
        [],
    )


def _finalize_rows(
    rows: dict[str, dict[str, Any]],
    *,
    thresholds: Mapping[str, int],
) -> list[dict[str, Any]]:
    telemarketing_min_dials = int(thresholds.get("telemarketing_min_dials") or 40)
    result: list[dict[str, Any]] = []
    for row in rows.values():
        row["messenger_dialogs"] = len(row.pop("_dialog_keys", set()))
        dials = int(row.get("dials") or 0)
        normal_calls = int(row.get("normal_calls") or 0)
        messenger_messages = int(row.get("messenger_messages") or 0)
        messenger_dialogs = int(row.get("messenger_dialogs") or 0)
        role = str(row.get("employee_role") or "sales").strip().lower()
        row["total_known"] = dials + messenger_messages
        row["connect_rate"] = (float(normal_calls) / float(dials)) if dials > 0 else None
        row["no_activity"] = dials <= 0 and messenger_messages <= 0
        if role == "telemarketing":
            row["low_connect"] = dials >= 15 and (row["connect_rate"] or 0.0) < 0.12
            row["low_activity"] = not row["no_activity"] and dials < telemarketing_min_dials and messenger_dialogs < 2
        else:
            row["low_connect"] = dials >= 10 and normal_calls == 0
            row["low_activity"] = not row["no_activity"] and normal_calls < 2 and messenger_dialogs < 3
        result.append(row)

    return sorted(
        result,
        key=lambda item: (
            str(item.get("employee_role") or ""),
            int(item.get("total_known") or 0),
            int(item.get("messenger_dialogs") or 0),
            int(item.get("dials") or 0),
            str(item.get("manager_name") or ""),
        ),
        reverse=True,
    )


def _team_metrics(manager_stats: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "manager_count": len(manager_stats),
        "managers_with_overdue_tasks": sum(1 for item in manager_stats if int(item.get("overdue_tasks_count") or 0) > 0),
        "managers_with_low_communication": sum(
            1 for item in manager_stats if bool(item.get("low_connect")) or bool(item.get("low_activity"))
        ),
        "managers_with_no_activity": sum(1 for item in manager_stats if bool(item.get("no_activity"))),
    }


def _compose_summary(
    env: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any] | None,
    analysis: Mapping[str, Any] | None,
    period_start: datetime,
    period_end: datetime,
    department_filter: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot_data = dict(snapshot or {})
    thresholds = _thresholds(env)
    rows, users_by_id, user_lookup = _manager_rows_base(
        snapshot_data,
        department_filter=department_filter,
    )

    limitations = list(department_filter.get("warnings") or [])
    calls_status, call_limitations = _fetch_call_stats(
        env,
        period_start=period_start,
        period_end=period_end,
        rows=rows,
    )
    limitations.extend(call_limitations)

    messengers_status, messenger_limitations = _fetch_messenger_stats(
        env,
        period_start=period_start,
        period_end=period_end,
        rows=rows,
        users_by_id=users_by_id,
        user_lookup=user_lookup,
    )
    limitations.extend(messenger_limitations)

    _apply_analysis_signals(
        rows,
        analysis,
        period_start=period_start,
        period_end=period_end,
        thresholds=thresholds,
    )
    manager_stats = _finalize_rows(rows, thresholds=thresholds)

    system_limitations: list[str] = []
    if not calls_status.get("available"):
        system_limitations.append(str((calls_status.get("error") or "Звонки Bitrix недоступны")).strip())
    if not messengers_status.get("available"):
        system_limitations.append(str((messengers_status.get("error") or "Wazzup archive недоступен")).strip())

    return {
        "period_start": period_start.isoformat(timespec="seconds"),
        "period_end": period_end.isoformat(timespec="seconds"),
        "department_filter": dict(department_filter),
        "thresholds": thresholds,
        "manager_stats": manager_stats,
        "managers": manager_stats,
        "team_metrics": _team_metrics(manager_stats),
        "calls": calls_status,
        "messengers": messengers_status,
        "system_limitations": system_limitations,
        "limitations": list(dict.fromkeys([item for item in limitations if item])),
    }


def get_yesterday_communications_summary(
    env: Mapping[str, Any] | None,
    *,
    snapshot: Mapping[str, Any] | None = None,
    analysis: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    department_filter: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    env_data = dict(env or {})
    current_now = (now or datetime.now(MOSCOW_TZ)).astimezone(MOSCOW_TZ)
    resolved_filter = dict(department_filter or resolve_sales_team_filter(env_data, snapshot=snapshot))
    period_start, period_end = _daily_window(current_now)
    summary = _compose_summary(
        env_data,
        snapshot=snapshot,
        analysis=analysis,
        period_start=period_start,
        period_end=period_end,
        department_filter=resolved_filter,
    )
    summary["generated_at"] = current_now.isoformat(timespec="seconds")
    summary["period_mode"] = "previous_business_day"
    return summary


def get_communications_summary_for_window(
    env: Mapping[str, Any] | None,
    *,
    snapshot: Mapping[str, Any] | None = None,
    analysis: Mapping[str, Any] | None = None,
    period_start: datetime,
    period_end: datetime,
    department_filter: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    env_data = dict(env or {})
    resolved_filter = dict(department_filter or resolve_sales_team_filter(env_data, snapshot=snapshot))
    return _compose_summary(
        env_data,
        snapshot=snapshot,
        analysis=analysis,
        period_start=period_start,
        period_end=period_end,
        department_filter=resolved_filter,
    )
