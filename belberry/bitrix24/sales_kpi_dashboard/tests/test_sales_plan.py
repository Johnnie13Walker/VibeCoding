from __future__ import annotations

from datetime import date
from unittest.mock import Mock

from sales_kpi_dashboard.metrics import sales_plan


class Plan:
    def __init__(self, values: dict[str, float]):
        self.values = values

    def get(self, key: str, default: float = 0.0) -> float:
        return self.values.get(key, default)


def test_sales_plan_computes_products_and_mop_rows() -> None:
    reader = Mock()
    reader.resolve_role_users.return_value = {2806: "Деговцова Елизавета", 2846: "Семенихин Егор"}
    reader.list_deals_won_in_period.return_value = [
        {"ID": "1", "ASSIGNED_BY_ID": "2806", "OPPORTUNITY": "1000", "CLOSEDATE": "2026-05-10T10:00:00+03:00"},
        {"ID": "2", "ASSIGNED_BY_ID": "2846", "OPPORTUNITY": "2000", "CLOSEDATE": "2026-05-11T10:00:00+03:00"},
    ]
    reader.productrows_for_deals.side_effect = [
        {
            1: [{"PRODUCT_ID": "7658", "PRICE": "1000", "QUANTITY": "1"}],
            2: [{"PRODUCT_ID": "2", "PRICE": "2000", "QUANTITY": "1"}],
        },
        {
            1: [{"PRODUCT_ID": "7658", "PRICE": "1000", "QUANTITY": "1"}],
            2: [{"PRODUCT_ID": "2", "PRICE": "2000", "QUANTITY": "1"}],
        },
    ]
    reader.list_meetings_in_period.return_value = [
        {"OWNER_TYPE_ID": "2", "OWNER_ID": "1", "CREATED": "2026-05-10T10:00:00+03:00"},
        {"OWNER_TYPE_ID": "2", "OWNER_ID": "2", "CREATED": "2026-05-11T10:00:00+03:00"},
    ]
    reader.list_deals_open_in_pre_final.return_value = [{"OPPORTUNITY": "500"}]

    rows = sales_plan.compute(
        reader,
        Plan({"План_SEO": 2000, "План_PPC": 2000, "План_МОП_2806": 1000, "План_общий": 5000}),
        date(2026, 5, 20),
    )

    assert rows[0] == sales_plan.HEADER
    seo_row = next(row for row in rows if row[1] == "product" and row[2] == "SEO")
    ppc_row = next(row for row in rows if row[1] == "product" and row[2] == "PPC")
    mop_row = next(row for row in rows if row[1] == "mop" and row[2] == "Деговцова Елизавета")
    summary_row = next(row for row in rows if row[1] == "integration_summary")

    assert seo_row[3] == 1000
    assert ppc_row[3] == 2000
    assert mop_row[3] == 1000
    assert summary_row[3] == 3000
    assert summary_row[5] == 3500
