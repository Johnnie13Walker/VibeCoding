"""Preflight risk scoring перед apply.

Превышение любого порога останавливает run со статусом
manual_review_high_conflict_risk и не зовет crm.entity.mergeBatch.

Пороги приходят из config/loader.BatchLimits — env-driven, не hardcoded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from belberry.bitrix24.policies.merge_policy import unique_product_signatures


@dataclass(frozen=True)
class RiskThresholds:
    max_group_size: int = 2
    max_contact_additions: int = 0
    max_deal_updates: int = 2
    max_activities: int = 30
    max_timeline_comments: int = 20
    max_product_signatures: int = 0


def _count_items(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def preflight_metrics(backup: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    items = [item for item in backup.get("deals", []) if isinstance(item, Mapping)]
    return {
        "group_size": len(items),
        "contact_additions_count": _count_items(plan.get("contact_additions")),
        "deal_updates_count": _count_items(plan.get("deal_updates")),
        "activities_total": sum(_count_items(item.get("activities")) for item in items),
        "timeline_comments_total": sum(_count_items(item.get("timeline_comments")) for item in items),
        "product_signature_count": len(unique_product_signatures(backup)),
    }


def preflight_high_conflict_risk(
    backup: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    thresholds: RiskThresholds | None = None,
) -> dict[str, Any]:
    """Оценивает риск Bitrix CONFLICT до любых изменений CRM."""
    th = thresholds or RiskThresholds()
    metrics = preflight_metrics(backup, plan)
    reasons: list[str] = []

    if metrics["group_size"] > th.max_group_size:
        reasons.append("group_size_gt_max")
    if metrics["contact_additions_count"] > th.max_contact_additions:
        reasons.append("contact_additions_over_limit")
    if metrics["deal_updates_count"] >= th.max_deal_updates + 1:
        reasons.append("deal_updates_over_limit")
    if metrics["activities_total"] > th.max_activities:
        reasons.append("activities_total_over_limit")
    if metrics["timeline_comments_total"] > th.max_timeline_comments:
        reasons.append("timeline_comments_total_over_limit")
    if metrics["product_signature_count"] > th.max_product_signatures:
        reasons.append("product_signature_present")

    return {
        "ok": not reasons,
        "status": "low_risk" if not reasons else "high_conflict_risk",
        "metrics": metrics,
        "reasons": reasons,
        "thresholds": {
            "max_group_size": th.max_group_size,
            "max_contact_additions": th.max_contact_additions,
            "max_deal_updates": th.max_deal_updates,
            "max_activities": th.max_activities,
            "max_timeline_comments": th.max_timeline_comments,
            "max_product_signatures": th.max_product_signatures,
        },
    }
