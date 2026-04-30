"""Data foundation для Sales Copilot поверх Bitrix adapter."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from cloudbot.providers.bitrix.bitrix_sales_adapter import (
    BRIEF_ACCEPTED_STAGE_NAME,
    BRIEF_CATEGORY_ID,
    BRIEF_ENTITY_TYPE_ID,
    BitrixSalesAdapter,
    MEETING_CATEGORY_ID,
    MEETING_DONE_STAGE_NAME,
    MEETING_ENTITY_TYPE_ID,
    SALES_DEAL_CATEGORY_ID,
)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def _sort_recent(items: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: str(item.get(field) or ""), reverse=True)


def _as_iso(value: datetime) -> str:
    return value.astimezone(MOSCOW_TZ).replace(microsecond=0).isoformat()


def get_sales_snapshot(
    env: Mapping[str, Any] | None = None,
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict[str, Any]:
    env_data = dict(env or {})
    adapter = BitrixSalesAdapter.from_env(env)
    skip_access_report = str(env_data.get("SALES_SKIP_ACCESS_REPORT") or "").strip().lower() in {"1", "true", "yes", "on"}
    if skip_access_report:
        assumed_ok = adapter.is_configured()
        access_report = [
            {
                "key": key,
                "label": label,
                "ok": assumed_ok,
                "status": "skipped",
                "message": "probe skipped",
                "code": None,
            }
            for key, label in (
                ("profile", "профиль"),
                ("users", "пользователи"),
                ("deals", "сделки category 10"),
                ("companies", "компании"),
                ("contacts", "контакты"),
                ("meetings", "встречи type 1048"),
                ("briefs", "брифы type 1056"),
                ("telephony", "телефония (crm.activity.list CALL)"),
                ("departments", "департаменты"),
                ("tasks", "задачи"),
            )
        ]
    else:
        access_report = adapter.check_access()
    available = [item["label"] for item in access_report if item.get("ok")]
    unavailable = [item for item in access_report if not item.get("ok")]
    unavailable_by_key = {str(item.get("key") or ""): item for item in unavailable}
    limitations: list[str] = []
    default_snapshot_limit = 500 if isinstance(period_start, datetime) and isinstance(period_end, datetime) else 200
    snapshot_limit = int(env_data.get("SALES_SNAPSHOT_LIMIT") or default_snapshot_limit)
    task_limit = int(env_data.get("SALES_TASK_LIMIT") or 200)
    users_limit = int(env_data.get("SALES_USERS_LIMIT") or 1000)

    recent_deals_filter: dict[str, Any] = {}
    closed_deals_filter: dict[str, Any] = {"CLOSED": "Y"}
    if isinstance(period_start, datetime) and isinstance(period_end, datetime):
        recent_deals_filter = {
            ">=DATE_CREATE": _as_iso(period_start),
            "<DATE_CREATE": _as_iso(period_end),
        }
        closed_deals_filter.update(
            {
                ">=MOVED_TIME": _as_iso(period_start),
                "<MOVED_TIME": _as_iso(period_end),
            }
        )

    recent_leads: list[dict[str, Any]] = []
    active_leads: list[dict[str, Any]] = []
    recent_deals = (
        adapter.get_deals(
            limit=snapshot_limit,
            category_id=SALES_DEAL_CATEGORY_ID,
            filter_params=recent_deals_filter or None,
            order={"DATE_CREATE": "DESC"},
        )
        if any(item["key"] == "deals" and item["ok"] for item in access_report)
        else []
    )
    active_deals = (
        adapter.get_active_deals(limit=snapshot_limit, category_id=SALES_DEAL_CATEGORY_ID)
        if any(item["key"] == "deals" and item["ok"] for item in access_report)
        else []
    )
    closed_deals = (
        adapter.get_deals(
            limit=snapshot_limit,
            category_id=SALES_DEAL_CATEGORY_ID,
            filter_params=closed_deals_filter,
            order={"MOVED_TIME": "DESC"},
        )
        if any(item["key"] == "deals" and item["ok"] for item in access_report)
        else []
    )
    deal_source_map = (
        adapter.get_deal_source_map()
        if any(item["key"] == "deals" and item["ok"] for item in access_report)
        else []
    )
    meeting_stage_map = (
        adapter.get_dynamic_stage_map(entity_type_id=MEETING_ENTITY_TYPE_ID, category_id=MEETING_CATEGORY_ID)
        if any(item["key"] == "meetings" and item["ok"] for item in access_report)
        else []
    )
    meetings = (
        adapter.get_meetings(limit=snapshot_limit)
        if any(item["key"] == "meetings" and item["ok"] for item in access_report)
        else []
    )
    conducted_meetings = (
        adapter.get_conducted_meetings(limit=snapshot_limit)
        if any(item["key"] == "meetings" and item["ok"] for item in access_report)
        else []
    )
    brief_stage_map = (
        adapter.get_dynamic_stage_map(entity_type_id=BRIEF_ENTITY_TYPE_ID, category_id=BRIEF_CATEGORY_ID)
        if any(item["key"] == "briefs" and item["ok"] for item in access_report)
        else []
    )
    briefs = (
        adapter.get_briefs(limit=snapshot_limit)
        if any(item["key"] == "briefs" and item["ok"] for item in access_report)
        else []
    )
    accepted_briefs = (
        adapter.get_accepted_briefs(limit=snapshot_limit)
        if any(item["key"] == "briefs" and item["ok"] for item in access_report)
        else []
    )
    deal_stage_map = (
        adapter.get_deal_stage_map(category_id=SALES_DEAL_CATEGORY_ID)
        if any(item["key"] == "deals" and item["ok"] for item in access_report)
        else []
    )
    deal_fields_meta = (
        adapter.get_deal_fields_meta()
        if any(item["key"] == "deals" and item["ok"] for item in access_report)
        else {}
    )
    next_step_map = adapter.get_deal_next_steps(
        [item.get("id") for item in active_deals + recent_deals if str(item.get("id") or "").strip()],
        limit_per_deal=10,
    )
    for item in recent_deals + active_deals:
        deal_id = str(item.get("id") or "").strip()
        if deal_id and deal_id in next_step_map:
            item.update(next_step_map[deal_id])
    timeline_comment_map: dict[str, list[dict[str, Any]]] = {}
    deal_ids_for_timeline = [
        item.get("id")
        for item in active_deals + recent_deals
        if str(item.get("id") or "").strip()
    ]
    if deal_ids_for_timeline:
        try:
            timeline_comment_map = adapter.get_deal_timeline_comments(
                deal_ids_for_timeline,
                since=datetime.now(MOSCOW_TZ) - timedelta(days=14),
                limit_per_deal=20,
            )
        except Exception as error:  # noqa: BLE001
            limitations.append(f"Комментарии timeline по сделкам недоступны: {error}.")

    tasks_bundle = adapter.get_tasks_bundle(limit=task_limit)
    tasks = list(tasks_bundle.get("items") or [])
    task_status_map = adapter.get_task_status_map() if tasks_bundle.get("available") else {}
    relevant_user_ids = {
        str(item.get("assigned_id") or "").strip()
        for item in recent_deals + active_deals + meetings + briefs
        if str(item.get("assigned_id") or "").strip()
    }
    profile = adapter.get_profile() if any(item["key"] == "profile" and item["ok"] for item in access_report) else {}
    if str(profile.get("id") or "").strip():
        relevant_user_ids.add(str(profile.get("id") or "").strip())
    users = (
        adapter.get_users(limit=max(len(relevant_user_ids), 1) + 20, user_ids=sorted(relevant_user_ids))
        if any(item["key"] == "users" and item["ok"] for item in access_report)
        else []
    )
    resolved_user_ids = {
        str(user.get("id") or "").strip()
        for user in users
        if str(user.get("id") or "").strip()
    }
    missing_user_ids = [user_id for user_id in sorted(relevant_user_ids) if user_id not in resolved_user_ids]
    if missing_user_ids:
        retry_users = adapter.get_users(limit=max(len(missing_user_ids), 1) + 5, user_ids=missing_user_ids)
        for user in retry_users:
            user_id = str(user.get("id") or "").strip()
            if user_id and user_id not in resolved_user_ids:
                users.append(user)
                resolved_user_ids.add(user_id)
    if any(item["key"] == "users" and item["ok"] for item in access_report):
        all_users = adapter.get_users(limit=users_limit)
        for user in all_users:
            user_id = str(user.get("id") or "").strip()
            if user_id and user_id not in resolved_user_ids:
                users.append(user)
                resolved_user_ids.add(user_id)
    departments = (
        adapter.get_departments() if any(item["key"] == "departments" and item["ok"] for item in access_report) else []
    )
    related_company_ids = {
        str(item.get("company_id") or "").strip()
        for item in recent_leads + active_leads + recent_deals + active_deals
        if str(item.get("company_id") or "").strip()
    }
    related_contact_ids = {
        str(item.get("contact_id") or "").strip()
        for item in recent_leads + active_leads + recent_deals + active_deals
        if str(item.get("contact_id") or "").strip()
    }
    companies = (
        adapter.get_companies(limit=50, company_ids=sorted(related_company_ids))
        if any(item["key"] == "companies" and item["ok"] for item in access_report)
        else []
    )
    contacts = (
        adapter.get_contacts(limit=50, contact_ids=sorted(related_contact_ids))
        if any(item["key"] == "contacts" and item["ok"] for item in access_report)
        else []
    )

    users_by_id = {str(user.get("id") or ""): user for user in users}
    departments_by_head = {
        str(item.get("head_user_id") or ""): item
        for item in departments
        if str(item.get("head_user_id") or "").strip()
    }

    if "tasks" in unavailable_by_key:
        webhook_error = ((tasks_bundle.get("error") or {}).get("webhook") or {})
        app_error = ((tasks_bundle.get("error") or {}).get("app_oauth") or {})
        limitations.append(
            "Прямое чтение задач Bitrix недоступно: "
            f"webhook={webhook_error.get('code') or webhook_error.get('status') or '-'}; "
            f"app_oauth={app_error.get('code') or app_error.get('status') or '-'}."
        )
    if not next_step_map:
        limitations.append("Не найдено ни одной незавершённой CRM activity для определения следующего шага.")

    return {
        "ok": adapter.is_configured(),
        "checked_at_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
        "source": adapter.sales_read_mode(),
        "portal_base_url": adapter.portal_base_url(),
        "scope": {
            "deal_category_id": SALES_DEAL_CATEGORY_ID,
            "meeting_entity_type_id": MEETING_ENTITY_TYPE_ID,
            "meeting_category_id": MEETING_CATEGORY_ID,
            "brief_entity_type_id": BRIEF_ENTITY_TYPE_ID,
            "brief_category_id": BRIEF_CATEGORY_ID,
        },
        "profile": profile,
        "counts": {
            "leads": len(recent_leads),
            "active_leads": len(active_leads),
            "deals": len(recent_deals),
            "active_deals": len(active_deals),
            "closed_deals": len(closed_deals),
            "meetings": len(meetings),
            "conducted_meetings": len(conducted_meetings),
            "briefs": len(briefs),
            "accepted_briefs": len(accepted_briefs),
            "tasks": len(tasks),
            "companies": len(companies),
            "contacts": len(contacts),
        },
        "latest_leads": _sort_recent(recent_leads, "created_at")[:5],
        "latest_deals": _sort_recent(recent_deals, "created_at")[:5],
        "recent_leads": _sort_recent(recent_leads, "created_at"),
        "active_leads": _sort_recent(active_leads, "updated_at"),
        "recent_deals": _sort_recent(recent_deals, "created_at"),
        "active_deals": _sort_recent(active_deals, "updated_at"),
        "closed_deals": _sort_recent(closed_deals, "moved_at"),
        "companies": companies,
        "contacts": contacts,
        "departments": departments,
        "responsibles": users_by_id,
        "departments_by_head": departments_by_head,
        "deal_stage_map": deal_stage_map,
        "deal_fields_meta": deal_fields_meta,
        "deal_source_map": deal_source_map,
        "meeting_stage_map": meeting_stage_map,
        "brief_stage_map": brief_stage_map,
        "meetings": meetings[:50],
        "conducted_meetings": conducted_meetings[:50],
        "briefs": briefs[:50],
        "accepted_briefs": accepted_briefs[:50],
        "tasks": tasks[:200],
        "tasks_status": tasks_bundle,
        "task_status_map": task_status_map,
        "report_period": {
            "start": _as_iso(period_start) if isinstance(period_start, datetime) else None,
            "end": _as_iso(period_end) if isinstance(period_end, datetime) else None,
        },
        "deal_timeline_comments": timeline_comment_map,
        "next_step_source": "crm.activity.list",
        "meeting_done_stage_name": MEETING_DONE_STAGE_NAME,
        "brief_accepted_stage_name": BRIEF_ACCEPTED_STAGE_NAME,
        "access_report": access_report,
        "available": available,
        "unavailable": unavailable,
        "limitations": limitations,
    }
