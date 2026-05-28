"""Эвристики рисков и приоритизации для Sales Copilot."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any


def _sort_key(item: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(item.get("severity") or 0.0),
        float(item.get("amount") or 0.0),
        float(item.get("probability") or item.get("effective_probability") or 0.0),
    )


def _focus_sort_key(item: dict[str, Any]) -> tuple[float, int, int, int, int, int, float]:
    return (
        float(item.get("amount") or 0.0),
        int(bool(item.get("late_stage"))),
        int(item.get("inactive_days") or 0),
        int(bool(item.get("missing_next_step"))),
        int(bool(item.get("needs_leader"))),
        int(bool(item.get("meeting_today"))),
        float(item.get("effective_probability") or item.get("probability") or 0.0),
    )


def detect_risks(
    analysis: dict[str, Any],
    *,
    inactivity_days: int = 5,
    late_stage_days: int = 5,
    stale_communication_days: int = 14,
    stagnant_risk_days: int = 14,
) -> dict[str, Any]:
    deal_risks: list[dict[str, Any]] = []
    lead_risks: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    leader_attention: list[dict[str, Any]] = []

    manager_active_counts: dict[str, int] = defaultdict(int)
    manager_risky_counts: dict[str, int] = defaultdict(int)
    manager_names: dict[str, str] = {}
    overdue_tasks_by_deal_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in analysis.get("overdue_deal_tasks") or []:
        deal_id = str(item.get("deal_id") or "").strip()
        if deal_id:
            overdue_tasks_by_deal_id[deal_id].append(item)

    for deal in analysis.get("active_deals") or []:
        manager_id = str(deal.get("assigned_id") or "")
        manager_active_counts[manager_id] += 1
        manager_names[manager_id] = str(deal.get("assigned_name") or "Не назначен")

        reasons: list[str] = []
        actions: list[str] = []
        categories: list[str] = []
        severity = 0
        inactive = int(deal.get("inactive_days") or 0)
        deal_id = str(deal.get("id") or "").strip()
        moved_in_last_week = bool(deal.get("moved_in_last_week"))
        engaged_in_last_week = bool(deal.get("engaged_in_last_week"))
        upcoming_meeting_at = deal.get("upcoming_meeting_at")
        has_upcoming_meeting = isinstance(upcoming_meeting_at, datetime) and upcoming_meeting_at >= analysis["now"]
        overdue_tasks = overdue_tasks_by_deal_id.get(deal_id) or []
        deal_age_days = 0
        created_at = deal.get("created_at")
        if created_at is not None:
            try:
                deal_age_days = max(int((analysis["now"] - created_at).total_seconds() // 86400), 0)
            except Exception:  # noqa: BLE001
                deal_age_days = 0

        if inactive >= stagnant_risk_days and not engaged_in_last_week:
            reasons.append(f"без движения {stagnant_risk_days} дн.")
            actions.append("проверить, почему сделка без движения более 14 дней")
            categories.append("stagnant")
            severity += 2

        if deal.get("missing_next_step"):
            reasons.append("без следующего шага")
            actions.append("зафиксировать следующий шаг в CRM")
            categories.append("next_step")
            severity += 2

        if overdue_tasks:
            reasons.append("есть просроченные задачи")
            actions.append("закрыть или перепланировать просроченные задачи по сделке")
            categories.append("overdue_tasks")
            severity += 2

        if deal.get("late_stage") and inactive >= late_stage_days:
            reasons.append(f"поздняя стадия без движения {inactive} дн.")
            actions.append("эскалировать до конца дня")
            categories.append("late_stage")
            severity += 3

        communication_gap_days = int(deal.get("communication_gap_days") or 0)
        if communication_gap_days >= stale_communication_days and not has_upcoming_meeting:
            reasons.append(f"без коммуникации {communication_gap_days} дн.")
            actions.append("сделать прямой контакт с клиентом сегодня")
            categories.append("stale_communication")
            severity += 2

        if deal.get("large_deal") and reasons:
            actions.append("взять сделку на личный контроль")
            categories.append("large_deal")
            severity += 1

        if deal.get("meeting_today"):
            actions.append("подготовиться к сегодняшней встрече по сделке")
            categories.append("meeting_today")
            if not reasons:
                severity += 1

        if deal.get("today_created") and deal.get("large_deal"):
            alerts.append(
                {
                    "kind": "large_deal",
                    "title": deal["title"],
                    "card_url": deal.get("card_url"),
                    "assigned_name": deal["assigned_name"],
                    "amount": deal["amount"],
                    "message": f"Новая крупная сделка: {deal['title']} ({deal['amount']:.0f})",
                }
            )

        if deal.get("needs_leader") or (severity >= 4 and deal.get("large_deal")):
            leader_attention.append(deal)

        if reasons:
            manager_risky_counts[manager_id] += 1
            deal_risks.append(
                {
                    "entity_type": "deal",
                    "entity_id": deal["id"],
                    "title": deal["title"],
                    "card_url": deal.get("card_url"),
                    "assigned_name": deal["assigned_name"],
                    "amount": deal["amount"],
                    "probability": deal.get("effective_probability") or deal.get("probability"),
                    "stage_name": deal["stage_name"],
                    "inactive_days": inactive,
                    "reasons": reasons,
                    "actions": list(dict.fromkeys(actions)),
                    "categories": list(dict.fromkeys(categories)),
                    "severity": severity,
                    "needs_leader": deal.get("needs_leader", False),
                    "meeting_today": bool(deal.get("meeting_today")),
                }
            )

    for lead in analysis.get("active_leads") or []:
        manager_id = str(lead.get("assigned_id") or "")
        manager_active_counts[manager_id] += 1
        manager_names[manager_id] = str(lead.get("assigned_name") or "Не назначен")

        reasons: list[str] = []
        actions: list[str] = []
        categories: list[str] = []
        severity = 0
        inactive = int(lead.get("inactive_days") or 0)

        if not lead.get("qualified") and inactive >= 1 and not lead.get("today_created"):
            reasons.append("лид без обработки")
            actions.append("сделать первый контакт и зафиксировать статус")
            categories.append("lead_unprocessed")
            severity += 2

        if lead.get("missing_next_step") and inactive >= 1 and not lead.get("qualified"):
            reasons.append("нет следующего шага")
            actions.append("назначить следующий шаг")
            categories.append("next_step")
            severity += 1

        if reasons:
            manager_risky_counts[manager_id] += 1
            lead_risks.append(
                {
                    "entity_type": "lead",
                    "entity_id": lead["id"],
                    "title": lead["title"],
                    "card_url": lead.get("card_url"),
                    "assigned_name": lead["assigned_name"],
                    "status_name": lead["status_name"],
                    "inactive_days": inactive,
                    "reasons": reasons,
                    "actions": list(dict.fromkeys(actions)),
                    "categories": list(dict.fromkeys(categories)),
                    "severity": severity,
                }
            )

    manager_risks: list[dict[str, Any]] = []
    for manager_id, risky_count in manager_risky_counts.items():
        active_count = manager_active_counts.get(manager_id, 0)
        if active_count < 2:
            continue
        risk_ratio = risky_count / active_count if active_count else 0.0
        if risky_count >= 2 or risk_ratio >= 0.5:
            manager_risks.append(
                {
                    "manager_id": manager_id,
                    "manager_name": manager_names.get(manager_id, "Не назначен"),
                    "risky_items": risky_count,
                    "active_items": active_count,
                    "risk_ratio": risk_ratio,
                    "severity": 2 if risky_count >= 3 else 1,
                }
            )

    deal_risks.sort(key=_sort_key, reverse=True)
    lead_risks.sort(key=_sort_key, reverse=True)
    manager_risks.sort(key=lambda item: (item["severity"], item["risky_items"], item["risk_ratio"]), reverse=True)
    leader_attention = sorted(
        {item["id"]: item for item in leader_attention}.values(),
        key=lambda item: (float(item.get("amount") or 0.0), float(item.get("effective_probability") or 0.0)),
        reverse=True,
    )

    high_risk_deals = deal_risks[:5]
    press_to_close = sorted(
        [
            deal
            for deal in analysis.get("active_deals") or []
            if deal.get("high_probability")
            and not any(risk["entity_id"] == deal["id"] and risk["severity"] >= 4 for risk in deal_risks)
        ],
        key=lambda item: (
            float(item.get("amount") or 0.0),
            int(bool(item.get("meeting_today"))),
            -float(item.get("inactive_days") or 0.0),
            float(item.get("effective_probability") or 0.0),
        ),
        reverse=True,
    )[:5]
    focus_deals = sorted(
        analysis.get("active_deals") or [],
        key=_focus_sort_key,
        reverse=True,
    )[:5]

    all_risks = sorted(deal_risks + lead_risks, key=_sort_key, reverse=True)
    stagnant_deal_risks = [item for item in deal_risks if "stagnant" in (item.get("categories") or [])]
    next_step_deal_risks = [item for item in deal_risks if "next_step" in (item.get("categories") or [])]
    stale_communication_risks = [item for item in deal_risks if "stale_communication" in (item.get("categories") or [])]
    overdue_task_risks = [item for item in deal_risks if "overdue_tasks" in (item.get("categories") or [])]
    summary_risk_by_deal_id: dict[str, dict[str, Any]] = {}
    for item in [*stagnant_deal_risks, *next_step_deal_risks, *stale_communication_risks, *overdue_task_risks]:
        deal_id = str(item.get("entity_id") or "").strip()
        if deal_id:
            summary_risk_by_deal_id[deal_id] = item

    return {
        "deal_risks": deal_risks,
        "lead_risks": lead_risks,
        "manager_risks": manager_risks,
        "all_risks": all_risks,
        "high_risk_deals": high_risk_deals,
        "press_to_close": press_to_close,
        "focus_deals": focus_deals,
        "leader_attention": leader_attention[:5],
        "alerts": alerts,
        "category_totals": {
            "stagnant_deals": len(stagnant_deal_risks),
            "stagnant_amount": sum(float(item.get("amount") or 0.0) for item in stagnant_deal_risks),
            "deals_without_next_step": len(next_step_deal_risks),
            "deals_without_next_step_amount": sum(float(item.get("amount") or 0.0) for item in next_step_deal_risks),
            "stale_communication_deals": len(stale_communication_risks),
            "stale_communication_amount": sum(float(item.get("amount") or 0.0) for item in stale_communication_risks),
            "overdue_deal_task_deals": len(overdue_task_risks),
            "overdue_deal_task_amount": sum(float(item.get("amount") or 0.0) for item in overdue_task_risks),
        },
        "summary_totals": {
            "deal_risks": len(summary_risk_by_deal_id),
            "risk_amount": sum(float(item.get("amount") or 0.0) for item in summary_risk_by_deal_id.values()),
        },
        "totals": {
            "deal_risks": len(deal_risks),
            "lead_risks": len(lead_risks),
            "manager_risks": len(manager_risks),
            "risk_amount": sum(float(item.get("amount") or 0.0) for item in deal_risks),
        },
    }
