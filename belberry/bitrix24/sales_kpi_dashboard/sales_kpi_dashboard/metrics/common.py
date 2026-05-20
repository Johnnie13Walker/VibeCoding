from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from sales_kpi_dashboard import config
from sales_kpi_dashboard.periods import working_days, working_days_passed


def month_bounds(today: date) -> tuple[date, date]:
    return date(today.year, today.month, 1), today


def days_total(today: date) -> int:
    return len(working_days(today.year, today.month))


def days_passed(today: date) -> int:
    return max(working_days_passed(today), 1)


def weeks_passed(today: date) -> float:
    return max(days_passed(today) / 5, 1.0)


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def percent(numerator: float, denominator: float) -> float:
    return safe_div(numerator, denominator) * 100


def to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_day(value: Any) -> int:
    if isinstance(value, datetime):
        return value.day
    if not value:
        return 0
    text = str(value)
    try:
        return datetime.fromisoformat(text).day
    except ValueError:
        return 0


def row_amount(row: dict) -> float:
    return to_float(row.get("PRICE")) * (to_float(row.get("QUANTITY")) or 1.0)


def known_product_ids() -> set[int]:
    return set(config.PRODUCTS.values())


def product_ids_by_deal(productrows: dict[int, list[dict]]) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    for deal_id, rows in productrows.items():
        result[deal_id] = {to_int(row.get("PRODUCT_ID")) for row in rows if to_int(row.get("PRODUCT_ID"))}
    return result


def deal_id_from_activity(activity: dict) -> int:
    deal_id = to_int(activity.get("DEAL_ID"))
    if deal_id:
        return deal_id
    owner_type = str(activity.get("OWNER_TYPE_ID") or "")
    if owner_type in {"1", "2"}:
        return to_int(activity.get("OWNER_ID"))
    return 0


def cumulative_by_day(rows: list[dict], date_field: str) -> dict[int, float]:
    counts: dict[int, int] = defaultdict(int)
    for row in rows:
        day = parse_day(row.get(date_field))
        if day:
            counts[day] += 1
    cumulative: dict[int, float] = {}
    running = 0
    for day in sorted(counts):
        running += counts[day]
        cumulative[day] = float(running)
    return cumulative
