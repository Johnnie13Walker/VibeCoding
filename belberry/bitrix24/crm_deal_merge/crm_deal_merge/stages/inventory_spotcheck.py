"""Read-only spot-check smart-process связей перед полным merge."""
from __future__ import annotations

import random
from collections import Counter
from typing import Any

from ..bitrix_client import BitrixClient
from ..models import Group
from ..sheet_store import read_groups
from ..sheets_client import SheetsClient
from ..state import Status

TELEMETRY_SP_TYPES = {1040, 1044, 1052}


def run(
    bx: BitrixClient,
    sheets: SheetsClient,
    *,
    sample: int = 30,
    seed: int | None = None,
) -> dict[str, Any]:
    groups = [
        group
        for _, group in read_groups(sheets)
        if group.status == Status.PLAN_READY and group.domain
    ]
    summary = collect_spotcheck(bx, groups, sample=sample, seed=seed)
    _print_summary(summary)
    return summary


def collect_spotcheck(
    bx: BitrixClient,
    groups: list[Group],
    *,
    sample: int = 30,
    seed: int | None = None,
) -> dict[str, Any]:
    selected = _sample_groups(groups, sample=sample, seed=seed)
    type_names = _smart_type_names(bx)
    entity_counts: Counter[int] = Counter()
    losers_with_sp = 0
    total_losers = 0
    heavy_losers: list[dict[str, Any]] = []

    for group in selected:
        for loser_id in group.loser_ids:
            total_losers += 1
            found = bx.list_smart_items_for_deal(loser_id)
            item_count = 0
            breakdown: Counter[int] = Counter()
            for entity_type_id, items in found:
                count = len(items)
                item_count += count
                breakdown[int(entity_type_id)] += count
                entity_counts[int(entity_type_id)] += count
            if item_count:
                losers_with_sp += 1
                heavy_losers.append(
                    {
                        "company_id": group.company_id,
                        "domain": group.domain,
                        "loser_id": loser_id,
                        "items_count": item_count,
                        "entity_counts": {str(k): v for k, v in sorted(breakdown.items())},
                    }
                )

    business_types = sorted(entity_type_id for entity_type_id in entity_counts if entity_type_id not in TELEMETRY_SP_TYPES)
    return {
        "sampled_groups": len(selected),
        "sampled_losers": total_losers,
        "losers_with_sp": losers_with_sp,
        "entity_counts": {str(k): v for k, v in sorted(entity_counts.items())},
        "entity_names": {str(k): type_names.get(k, "") for k in sorted(entity_counts)},
        "top_heavy_losers": sorted(heavy_losers, key=lambda item: item["items_count"], reverse=True)[:5],
        "business_sp_found": bool(business_types),
        "business_entity_type_ids": [str(x) for x in business_types],
    }


def _sample_groups(groups: list[Group], *, sample: int, seed: int | None) -> list[Group]:
    if sample <= 0 or sample >= len(groups):
        return list(groups)
    rng = random.Random(seed)
    return rng.sample(groups, sample)


def _smart_type_names(bx: BitrixClient) -> dict[int, str]:
    names: dict[int, str] = {}
    for item in bx.smart_process_types():
        raw_id = item.get("entityTypeId")
        if raw_id is None:
            continue
        names[int(raw_id)] = str(
            item.get("title")
            or item.get("TITLE")
            or item.get("name")
            or item.get("NAME")
            or ""
        )
    return names


def _print_summary(summary: dict[str, Any]) -> None:
    print(
        "[inventory-spotcheck] "
        f"groups={summary['sampled_groups']} losers={summary['sampled_losers']} "
        f"losers_with_sp={summary['losers_with_sp']}"
    )
    print("[inventory-spotcheck] entity types:")
    if not summary["entity_counts"]:
        print("  нет smart-process связей")
    for entity_type_id, count in summary["entity_counts"].items():
        name = summary["entity_names"].get(entity_type_id) or "без названия"
        print(f"  {entity_type_id} {name}: {count}")

    print("[inventory-spotcheck] top-5 LOSER по SP:")
    if not summary["top_heavy_losers"]:
        print("  нет LOSER со smart-process связями")
    for item in summary["top_heavy_losers"]:
        print(
            "  "
            f"{item['company_id']}:{item['domain']} loser=#{item['loser_id']} "
            f"items={item['items_count']} types={item['entity_counts']}"
        )

    if summary["business_sp_found"]:
        ids = ", ".join(summary["business_entity_type_ids"])
        print(
            "\033[31mВНИМАНИЕ: возможна потеря бизнес-связей. "
            f"Найдены smart-process типы кроме 1040/1044/1052: {ids}. "
            "Перед полным transfer рекомендуется перезапустить полный inventory с --include-sp.\033[0m"
        )
