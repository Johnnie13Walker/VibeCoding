from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Protocol

from sales_kpi_dashboard import config
from sales_kpi_dashboard.periods import forecast, linear_trend
from sales_kpi_dashboard.reader import BitrixReader

from .common import (
    cumulative_by_day,
    days_passed,
    days_total,
    deal_id_from_activity,
    known_product_ids,
    month_bounds,
    percent,
    product_ids_by_deal,
    row_amount,
    safe_div,
    to_float,
    to_int,
)

HEADER = [
    "date_calc",
    "dimension_type",
    "dimension_value",
    "fact",
    "plan",
    "forecast",
    "trend",
    "percent_done",
]


class PlanLike(Protocol):
    def get(self, key: str, default: float = 0.0) -> float: ...


def compute(reader: BitrixReader, plan: PlanLike, today: date) -> list[list[object]]:
    month_start, month_end = month_bounds(today)
    date_calc = today.isoformat()
    passed = days_passed(today)
    total = days_total(today)
    mop_users = reader.resolve_role_users(config.MOP_POSITION_REGEX)
    deals_won = reader.list_deals_won_in_period(month_start, month_end)
    deal_ids = [to_int(deal.get("ID")) for deal in deals_won if to_int(deal.get("ID"))]
    productrows = reader.productrows_for_deals(deal_ids)
    meetings = reader.list_meetings_in_period(month_start, month_end)
    meeting_deal_ids = [
        deal_id for meeting in meetings if (deal_id := deal_id_from_activity(meeting))
    ]
    meeting_productrows = reader.productrows_for_deals(meeting_deal_ids)
    products_by_deal = product_ids_by_deal(meeting_productrows)
    open_deals = reader.list_deals_open_in_pre_final(10)

    rows = [HEADER]
    product_revenue = _product_revenue(deals_won, productrows)
    product_trend_source = _product_revenue_by_day(deals_won, productrows)
    for product_name in [*config.PRODUCTS.keys(), config.OTHER_PRODUCT]:
        fact = product_revenue[product_name]
        plan_value = float(plan.get(f"План_{product_name}", 0.0))
        rows.append(
            _metric_row(
                date_calc,
                "product",
                product_name,
                fact,
                plan_value,
                forecast(plan_value, fact, passed, total),
                linear_trend(product_trend_source.get(product_name, {}), total),
            )
        )

        meetings_fact = _meetings_for_product(meetings, products_by_deal, product_name)
        meetings_plan = float(plan.get(f"План_встреч_{product_name}", 0.0))
        rows.append(
            _metric_row(
                date_calc,
                "meetings_product",
                product_name,
                float(meetings_fact),
                meetings_plan,
                forecast(meetings_plan, meetings_fact, passed, total),
                float(meetings_fact),
            )
        )

    revenue_by_mop = _revenue_by_mop(deals_won, productrows)
    for user_id, user_name in sorted(mop_users.items(), key=lambda item: item[1]):
        fact = revenue_by_mop[user_id]
        plan_value = float(plan.get(f"План_МОП_{user_id}", 0.0))
        rows.append(
            _metric_row(
                date_calc,
                "mop",
                user_name,
                fact,
                plan_value,
                forecast(plan_value, fact, passed, total),
                fact,
            )
        )

    payments_received = sum(to_float(deal.get("OPPORTUNITY")) for deal in deals_won)
    expected_extra = sum(to_float(deal.get("OPPORTUNITY")) for deal in open_deals)
    plan_total = float(plan.get("План_общий", 0.0))
    rows.append(
        [
            date_calc,
            "integration_summary",
            "Оплаты получено",
            round(payments_received, 2),
            round(plan_total, 2),
            round(payments_received + expected_extra, 2),
            round(expected_extra, 2),
            round(percent(payments_received, plan_total), 2),
        ]
    )
    return rows


def _product_revenue(deals: list[dict], rows_by_deal: dict[int, list[dict]]) -> dict[str, float]:
    revenue: dict[str, float] = defaultdict(float)
    product_name_by_id = {product_id: name for name, product_id in config.PRODUCTS.items()}
    for deal in deals:
        deal_id = to_int(deal.get("ID"))
        for row in rows_by_deal.get(deal_id, []):
            product_id = to_int(row.get("PRODUCT_ID"))
            product_name = product_name_by_id.get(product_id, config.OTHER_PRODUCT)
            revenue[product_name] += row_amount(row)
    return revenue


def _product_revenue_by_day(
    deals: list[dict],
    rows_by_deal: dict[int, list[dict]],
) -> dict[str, dict[int, float]]:
    result: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    product_name_by_id = {product_id: name for name, product_id in config.PRODUCTS.items()}
    deal_by_id = {to_int(deal.get("ID")): deal for deal in deals}
    for deal_id, rows in rows_by_deal.items():
        day = cumulative_by_day([deal_by_id.get(deal_id, {})], "CLOSEDATE")
        day_number = next(iter(day.keys()), 0)
        if not day_number:
            continue
        for row in rows:
            product_id = to_int(row.get("PRODUCT_ID"))
            product_name = product_name_by_id.get(product_id, config.OTHER_PRODUCT)
            result[product_name][day_number] += row_amount(row)
    cumulative: dict[str, dict[int, float]] = {}
    for product_name, values in result.items():
        running = 0.0
        cumulative[product_name] = {}
        for day in sorted(values):
            running += values[day]
            cumulative[product_name][day] = running
    return cumulative


def _meetings_for_product(
    meetings: list[dict],
    products_by_deal: dict[int, set[int]],
    product_name: str,
) -> int:
    known_ids = known_product_ids()
    target_product_id = config.PRODUCTS.get(product_name)
    count = 0
    for meeting in meetings:
        product_ids = products_by_deal.get(deal_id_from_activity(meeting), set())
        if product_name == config.OTHER_PRODUCT:
            if product_ids and not (product_ids & known_ids):
                count += 1
        elif target_product_id in product_ids:
            count += 1
    return count


def _revenue_by_mop(deals: list[dict], rows_by_deal: dict[int, list[dict]]) -> dict[int, float]:
    revenue: dict[int, float] = defaultdict(float)
    for deal in deals:
        user_id = to_int(deal.get("ASSIGNED_BY_ID"))
        deal_id = to_int(deal.get("ID"))
        revenue[user_id] += sum(row_amount(row) for row in rows_by_deal.get(deal_id, []))
    return revenue


def _metric_row(
    date_calc: str,
    dimension_type: str,
    dimension_value: str,
    fact: float,
    plan: float,
    forecast_value: float,
    trend: float,
) -> list[object]:
    return [
        date_calc,
        dimension_type,
        dimension_value,
        round(fact, 2),
        round(plan, 2),
        round(forecast_value, 2),
        round(trend, 2),
        round(percent(fact, plan), 2),
    ]
