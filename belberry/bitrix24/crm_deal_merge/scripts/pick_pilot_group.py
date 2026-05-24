from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crm_deal_merge.bitrix_client import BitrixClient
from crm_deal_merge.config import LOG_PATH, SERVICE_ACCOUNT_JSON, SHEET_ID, STATE_PATH
from crm_deal_merge.grouping import funnel_id
from crm_deal_merge.sheet_store import read_groups, read_inventory
from crm_deal_merge.sheets_client import SheetsClient
from crm_deal_merge.state import Status


def main() -> None:
    parser = argparse.ArgumentParser(description="Подобрать PLAN_READY группы для замера transfer.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--min-total", type=int, default=10)
    parser.add_argument("--max-total", type=int, default=30)
    parser.add_argument("--require-sp1048", action="store_true")
    parser.add_argument("--prefer-no-tasks", action="store_true")
    args = parser.parse_args()

    sheets = SheetsClient(sheet_id=SHEET_ID, service_account_path=SERVICE_ACCOUNT_JSON)
    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    _, inventory_rows = read_inventory(sheets)
    inventory = _inventory_by_company(inventory_rows)

    candidates = []
    for _, group in read_groups(sheets):
        if group.status != Status.PLAN_READY:
            continue
        if not group.inn or group.inn == "—":
            continue
        if len(group.loser_ids) != 1:
            continue
        counts, task_count = _counts_for_group(inventory, group.company_id, group.loser_ids)
        total = group.n_activities_planned + group.n_timeline_planned + group.n_contacts_planned + group.n_sp_planned
        if total < args.min_total or total > args.max_total:
            continue
        if args.require_sp1048 and counts.get("sp:1048", 0) < 1:
            continue
        if args.prefer_no_tasks and task_count:
            continue
        if not _all_losers_in_funnel_38(bx, group.loser_ids):
            continue
        candidates.append(
            {
                "company_id": group.company_id,
                "domain": group.domain,
                "winner_id": group.winner_id,
                "loser_ids": group.loser_ids,
                "total": total,
                "activities": group.n_activities_planned,
                "timeline": group.n_timeline_planned,
                "contacts": group.n_contacts_planned,
                "sp": group.n_sp_planned,
                "sp1048": counts.get("sp:1048", 0),
                "sp1056": counts.get("sp:1056", 0),
                "task_activities": task_count,
            }
        )

    candidates.sort(key=lambda item: (abs(item["total"] - 20), -item["sp1048"], item["task_activities"]))
    for item in candidates[: args.limit]:
        print(json.dumps(item, ensure_ascii=False, sort_keys=True))


def _inventory_by_company(rows: list[tuple[int, dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    for _, row in rows:
        out[row.get("company_id", "")].append(row)
    return out


def _counts_for_group(
    inventory: dict[str, list[dict[str, str]]],
    company_id: str,
    loser_ids: list[str],
) -> tuple[Counter[str], int]:
    losers = set(loser_ids)
    counts: Counter[str] = Counter()
    task_count = 0
    for row in inventory.get(company_id, []):
        if row.get("loser_id") not in losers:
            continue
        if row.get("transferred") == "1":
            continue
        entity_type = row.get("entity_type", "")
        counts[entity_type] += 1
        if entity_type == "activity":
            details = row.get("details", "")
            if '"PROVIDER_ID": "TASKS"' in details or '"PROVIDER_ID": "CRM_TASKS_TASK"' in details:
                task_count += 1
    return counts, task_count


def _all_losers_in_funnel_38(bx: BitrixClient, loser_ids: list[str]) -> bool:
    for loser_id in loser_ids:
        deal = bx.get_deal(loser_id)
        if not deal or funnel_id(deal) != "38":
            return False
    return True


if __name__ == "__main__":
    main()
