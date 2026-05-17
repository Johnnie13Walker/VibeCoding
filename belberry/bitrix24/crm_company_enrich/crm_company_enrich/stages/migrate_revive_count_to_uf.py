"""Миграция исторического auto-revive #N в UF_CRM_REVIVE_COUNT."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..config import LAST_AUTO_ACTION_DESC_FIELD, REVIVE_COUNT_FIELD


@dataclass
class ReviveCountMigrationOutcome:
    deal_id: str
    old_desc: str
    new_count: int
    status: str
    error: str = ""


def run(bx, *, dry_run: bool = True, limit: int | None = None) -> dict[str, Any]:
    """Перенести последний auto-revive #N из строкового поля в integer UF."""
    deals = list(
        bx.paginate(
            "crm.deal.list",
            {
                "filter": {"!" + LAST_AUTO_ACTION_DESC_FIELD: False},
                "select": ["ID", LAST_AUTO_ACTION_DESC_FIELD, REVIVE_COUNT_FIELD],
            },
        )
    )
    if limit:
        deals = deals[:limit]

    outcomes: list[ReviveCountMigrationOutcome] = []
    for deal in deals:
        deal_id = str(deal.get("ID") or "")
        desc = str(deal.get(LAST_AUTO_ACTION_DESC_FIELD) or "")
        count = _parse_revive_count(desc)
        if count <= 0:
            continue
        current = _int_or_zero(deal.get(REVIVE_COUNT_FIELD))
        if current == count:
            outcomes.append(ReviveCountMigrationOutcome(deal_id, desc, count, "SKIPPED"))
            continue
        if dry_run:
            outcomes.append(ReviveCountMigrationOutcome(deal_id, desc, count, "DRY_RUN"))
            continue
        try:
            bx.update_deal(deal_id, {REVIVE_COUNT_FIELD: count})
            outcomes.append(ReviveCountMigrationOutcome(deal_id, desc, count, "MIGRATED"))
        except Exception as exc:  # noqa: BLE001
            outcomes.append(ReviveCountMigrationOutcome(deal_id, desc, count, "FAILED", str(exc)[:200]))

    return {
        "dry_run": dry_run,
        "examined": len(deals),
        "dry_run_migrations": sum(1 for o in outcomes if o.status == "DRY_RUN"),
        "migrated": sum(1 for o in outcomes if o.status == "MIGRATED"),
        "skipped": sum(1 for o in outcomes if o.status == "SKIPPED"),
        "failed": sum(1 for o in outcomes if o.status == "FAILED"),
        "outcomes": [outcome.__dict__ for outcome in outcomes],
    }


def _parse_revive_count(desc: str) -> int:
    matches = re.findall(r"auto-revive\s+\S+\s+#(\d+)", str(desc or ""))
    return int(matches[-1]) if matches else 0


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
