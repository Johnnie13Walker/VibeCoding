from datetime import date

from src.funnel_stages import furthest_order, stage_order
from src.sync_funnel_cohort import build_cohort_rows


def test_stage_order_helpers():
    assert stage_order("C10:NEW") == 1
    assert stage_order("C10:UC_4SJOE4") == 4  # Защита КП (новая)
    assert stage_order("C10:WON") == 9
    assert stage_order("C10:LOSE") == 0       # терминальная — вне пути
    assert stage_order(None) == 0
    assert furthest_order({"C10:NEW", "C10:EXECUTING", "C10:LOSE"}) == 3


def test_cohort_reached_middle_even_if_now_lost():
    """Сделка дошла до «Подготовки КП», затем отвалилась → furthest=3, is_lost."""
    deals = [{
        "ID": "100",
        "CATEGORY_ID": "10",
        "STAGE_ID": "C10:LOSE",
        "ASSIGNED_BY_ID": "2806",
        "DATE_CREATE": "2026-06-03T10:00:00+03:00",
        "OPPORTUNITY": "150000",
    }]
    history = {100: {"C10:NEW", "C10:PREPAYMENT_INVOIC", "C10:EXECUTING"}}
    row = build_cohort_rows(deals, history)[0]
    assert row["deal_id"] == 100
    assert row["furthest_order"] == 3
    assert row["furthest_stage"] == "C10:EXECUTING"
    assert row["is_won"] is False
    assert row["is_lost"] is True
    assert row["cohort_date"] == date(2026, 6, 3)
    assert row["manager_id"] == 2806
    assert row["opportunity"] == 150000.0


def test_cohort_won():
    deals = [{
        "ID": "101", "CATEGORY_ID": "10", "STAGE_ID": "C10:WON",
        "ASSIGNED_BY_ID": "2812", "DATE_CREATE": "2026-06-10T09:00:00+03:00", "OPPORTUNITY": "500000",
    }]
    history = {101: {"C10:NEW", "C10:EXECUTING", "C10:UC_4SJOE4", "C10:WON"}}
    row = build_cohort_rows(deals, history)[0]
    assert row["furthest_order"] == 9
    assert row["is_won"] is True
    assert row["is_lost"] is False


def test_cohort_new_only_uses_current_stage_without_history():
    deals = [{
        "ID": "102", "CATEGORY_ID": "10", "STAGE_ID": "C10:NEW",
        "ASSIGNED_BY_ID": "1", "DATE_CREATE": "2026-06-17T12:00:00+03:00", "OPPORTUNITY": None,
    }]
    row = build_cohort_rows(deals, {})[0]
    assert row["furthest_order"] == 1
    assert row["furthest_stage"] == "C10:NEW"
    assert row["is_won"] is False
    assert row["is_lost"] is False
    assert row["opportunity"] is None


def test_cohort_skips_rows_without_id():
    assert build_cohort_rows([{"STAGE_ID": "C10:NEW"}], {}) == []
