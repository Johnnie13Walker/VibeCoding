from __future__ import annotations

from datetime import date
from unittest.mock import Mock

from sales_kpi_dashboard.metrics import telemarketing


class Plan:
    def __init__(self, values: dict[str, float]):
        self.values = values

    def get(self, key: str, default: float = 0.0) -> float:
        return self.values.get(key, default)


def test_telemarketing_computes_calls_and_meetings() -> None:
    reader = Mock()
    reader.resolve_role_users.return_value = {2772: "Исаева Дарья"}
    reader.list_calls_in_period.return_value = [
        {"PORTAL_USER_ID": "2772", "CALL_TYPE": "1", "CALL_DURATION": "130"}
        for _ in range(50)
    ] + [
        {"PORTAL_USER_ID": "2772", "CALL_TYPE": "1", "CALL_DURATION": "30"}
        for _ in range(50)
    ]
    reader.list_meetings_in_period.return_value = [
        {"ID": str(index), "OWNER_TYPE_ID": "2", "OWNER_ID": "100", "CREATED_BY_ID": "2772", "CREATED": f"2026-05-{index + 1:02d}T10:00:00+03:00"}
        for index in range(10)
    ]

    rows = telemarketing.compute(reader, Plan({"Встречи_всего": 20, "Встречи_2772": 10}), date(2026, 5, 20))

    reader.productrows_for_deals.assert_not_called()
    assert rows[0] == telemarketing.HEADER
    user_row = rows[2]
    assert user_row[2] == 2772
    assert user_row[6] == 10
    assert user_row[10] == 50.0
    assert user_row[11] == 20.0
