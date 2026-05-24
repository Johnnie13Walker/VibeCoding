"""Анализ FAILED-групп и опциональный сброс для повторной обработки."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..sheet_store import read_groups, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(sheets: SheetsClient, *, reset: bool = False, pattern: str | None = None) -> dict:
    rows = [(row, group) for row, group in read_groups(sheets) if group.status == Status.FAILED]
    buckets: dict[str, list[str]] = defaultdict(list)
    for _, group in rows:
        bucket = classify_error(group.error_message or "")
        buckets[bucket].append(f"{group.company_id}:{group.domain or ''}")

    print("[reclassify-failed] FAILED summary:")
    for bucket, items in sorted(buckets.items(), key=lambda item: len(item[1]), reverse=True):
        print(f"  {bucket}: {len(items)}")

    reset_count = 0
    if reset:
        needle = (pattern or "").lower()
        now = datetime.now(MOSCOW_TZ)
        for row_number, group in rows:
            error = group.error_message or ""
            bucket = classify_error(error)
            if needle and needle not in error.lower() and needle not in bucket.lower():
                continue
            update_group(
                sheets,
                row_number,
                replace(group, status=Status.INVENTORIED, last_action_at=now, error_message=None),
            )
            reset_count += 1
        print(f"[reclassify-failed] reset to INVENTORIED: {reset_count}")

    return {
        "failed": len(rows),
        "buckets": {bucket: len(items) for bucket, items in buckets.items()},
        "reset": reset_count,
    }


def classify_error(message: str) -> str:
    text = message.lower()
    if "title safety" in text:
        return "TITLE safety"
    if "rate limit" in text or "query_limit" in text or "429" in text:
        return "Rate limit"
    if "not found" in text or "не найден" in text:
        return "Not found"
    if "timeout" in text or "503" in text or "502" in text or "504" in text:
        return "Temporary Bitrix/API"
    if not text.strip():
        return "Empty error"
    return "Other"
