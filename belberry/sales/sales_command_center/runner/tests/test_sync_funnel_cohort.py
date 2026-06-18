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


def test_cohort_date_is_entry_not_create_and_reaches_middle_when_lost():
    """Вошла в [10] 03.06 (C10:NEW), дошла до «Подготовки КП», затем отвал."""
    history = {
        100: [
            {"stage": "C10:NEW", "ct": "2026-06-03T10:00:00+03:00"},
            {"stage": "C10:EXECUTING", "ct": "2026-06-05T10:00:00+03:00"},
            {"stage": "C10:LOSE", "ct": "2026-06-08T10:00:00+03:00"},
        ]
    }
    deals = {100: {"ID": "100", "STAGE_ID": "C10:LOSE", "ASSIGNED_BY_ID": "2806", "OPPORTUNITY": "150000"}}
    row = build_cohort_rows(deals, history)[0]
    assert row["deal_id"] == 100
    assert row["cohort_date"] == date(2026, 6, 3)   # дата входа, не создания
    assert row["furthest_order"] == 3
    assert row["furthest_stage"] == "C10:EXECUTING"
    assert row["is_won"] is False
    assert row["is_lost"] is True
    assert row["manager_id"] == 2806
    assert row["opportunity"] == 150000.0


def test_entry_date_is_earliest_new():
    history = {
        200: [
            {"stage": "C10:NEW", "ct": "2026-06-15T09:00:00+03:00"},
            {"stage": "C10:NEW", "ct": "2026-06-02T09:00:00+03:00"},  # более ранний вход
            {"stage": "C10:EXECUTING", "ct": "2026-06-20T09:00:00+03:00"},
        ]
    }
    deals = {200: {"ID": "200", "STAGE_ID": "C10:EXECUTING", "ASSIGNED_BY_ID": "2188"}}
    row = build_cohort_rows(deals, history)[0]
    assert row["cohort_date"] == date(2026, 6, 2)


def test_cohort_won():
    history = {
        101: [
            {"stage": "C10:NEW", "ct": "2026-06-10T09:00:00+03:00"},
            {"stage": "C10:WON", "ct": "2026-06-20T09:00:00+03:00"},
        ]
    }
    deals = {101: {"ID": "101", "STAGE_ID": "C10:WON", "ASSIGNED_BY_ID": "2812", "OPPORTUNITY": "500000"}}
    row = build_cohort_rows(deals, history)[0]
    assert row["furthest_order"] == 9
    assert row["is_won"] is True
    assert row["is_lost"] is False


def test_reason_id_spam_captured():
    history = {300: [{"stage": "C10:NEW", "ct": "2026-06-04T09:00:00+03:00"}, {"stage": "C10:LOSE", "ct": "2026-06-04T12:00:00+03:00"}]}
    deals = {300: {"ID": "300", "STAGE_ID": "C10:LOSE", "ASSIGNED_BY_ID": "1", "UF_CRM_1771495464": ["8588"]}}
    row = build_cohort_rows(deals, history)[0]
    assert row["reason_id"] == 8588   # СПАМ — веб исключит
    assert row["is_lost"] is True


def test_skips_deal_without_entry_in_window():
    """Переходы есть, но C10:NEW в окне нет → вошла раньше периода, не наша когорта."""
    history = {103: [{"stage": "C10:EXECUTING", "ct": "2026-06-02T09:00:00+03:00"}]}
    deals = {103: {"ID": "103", "STAGE_ID": "C10:EXECUTING", "ASSIGNED_BY_ID": "1"}}
    assert build_cohort_rows(deals, history) == []
