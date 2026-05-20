from __future__ import annotations

from datetime import date
from unittest.mock import Mock

from sales_kpi_dashboard.metrics import mop_effectiveness


def test_mop_effectiveness_computes_user_metrics() -> None:
    reader = Mock()
    reader.resolve_role_users.return_value = {2806: "Деговцова Елизавета"}
    reader.list_calls_in_period.return_value = [
        {"PORTAL_USER_ID": "2806", "CALL_DURATION": "61"},
        {"PORTAL_USER_ID": "2806", "CALL_DURATION": "59"},
        {"PORTAL_USER_ID": "2846", "CALL_DURATION": "120"},
    ]
    reader.list_meetings_in_period.return_value = [
        {"OWNER_TYPE_ID": "2", "OWNER_ID": "10", "CREATED_BY_ID": "2806", "CREATED": "2026-05-01T10:00:00+03:00"},
        {"OWNER_TYPE_ID": "2", "OWNER_ID": "10", "CREATED_BY_ID": "2806", "CREATED": "2026-05-02T10:00:00+03:00"},
    ]
    reader.count_tasks_closed.return_value = 7
    reader.count_sp_items.side_effect = [3, 1]

    rows = mop_effectiveness.compute(reader, date(2026, 5, 20))

    assert rows[0] == mop_effectiveness.HEADER
    row = rows[1]
    assert row[3] == 1
    assert row[4] == 7
    assert row[5] == 3
    assert row[6] == 1
    assert row[7] == 1
    assert row[8] == 1
