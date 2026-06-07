from src.sync_rejections import (
    REASON_FIELD_10,
    REASON_FIELD_50,
    build_rejection_rows,
    build_sales_rejection_rows,
    fetch_sales_lose_dates,
)


def test_build_rejection_rows_maps_fields():
    deals = [
        {
            "ID": "28",
            "CATEGORY_ID": "50",
            "STAGE_ID": "C50:APOLOGY",
            "UF_CRM_1771324790": "8550",
            "MODIFY_BY_ID": "2832",
            "ASSIGNED_BY_ID": "2832",
            "DATE_MODIFY": "2026-05-20T10:00:00+03:00",
            "TITLE": "example.ru",
            "OPPORTUNITY": "150000.00",
        },
        {"ID": "40", "STAGE_ID": "C50:LOSE", "UF_CRM_1771324790": None, "MODIFY_BY_ID": "1"},
        {"STAGE_ID": "C50:APOLOGY"},  # без ID — пропускаем
    ]
    rows = build_rejection_rows(deals, REASON_FIELD_50)
    assert len(rows) == 2
    assert rows[0]["deal_id"] == 28
    assert rows[0]["reason_id"] == 8550
    assert rows[0]["modified_by"] == 2832
    assert rows[0]["stage_id"] == "C50:APOLOGY"
    assert rows[0]["rejected_at"] is not None
    assert rows[0]["opportunity"] == 150000.0
    assert rows[1]["deal_id"] == 40
    assert rows[1]["reason_id"] is None  # причина не указана
    assert rows[1]["modified_by"] == 1
    assert rows[1]["opportunity"] is None


def test_build_sales_rejection_rows_cat10_event_sourced():
    # Сделка уже уехала в ТМ (CATEGORY_ID=50 сейчас), но отказ Продажи фиксируем:
    # стадию/категорию ставим как у отказа cat10, дату — из stagehistory.
    deals = [
        {
            "ID": "23946",
            "CATEGORY_ID": "50",  # сейчас в ТМ
            "STAGE_ID": "C50:UC_1S1KIU",
            "UF_CRM_1771495464": ["8584"],  # значение может прийти списком
            "MODIFY_BY_ID": "12",
            "ASSIGNED_BY_ID": "2806",
            "DATE_MODIFY": "2026-05-30T09:00:00+03:00",  # НЕ используется
            "TITLE": "panaceadoc.ru",
            "OPPORTUNITY": "320000",
        },
        {"STAGE_ID": "C10:LOSE"},  # без ID — пропускаем
    ]
    lose_dates = {23946: "2026-04-11T18:30:00+03:00"}
    rows = build_sales_rejection_rows(deals, lose_dates, REASON_FIELD_10)
    assert len(rows) == 1
    r = rows[0]
    assert r["deal_id"] == 23946
    assert r["category_id"] == 10  # фиксируем воронку отказа, не текущую
    assert r["stage_id"] == "C10:LOSE"
    assert r["reason_id"] == 8584  # первый код из списка
    assert r["assigned_by"] == 2806
    assert r["opportunity"] == 320000.0
    # дата отказа — из stagehistory, а не DATE_MODIFY
    assert r["rejected_at"] is not None
    assert r["rejected_at"].month == 4 and r["rejected_at"].day == 11


def test_fetch_sales_lose_dates_dedups_latest_transition():
    class FakeBx:
        pass

    calls = {}

    def fake_fetch_all(bx, method, params):
        calls["method"] = method
        calls["filter"] = params["filter"]
        return [
            {"ID": "1", "OWNER_ID": "100", "CREATED_TIME": "2026-02-01T10:00:00+03:00"},
            {"ID": "2", "OWNER_ID": "100", "CREATED_TIME": "2026-05-20T10:00:00+03:00"},
            {"ID": "3", "OWNER_ID": "200", "CREATED_TIME": "2026-03-15T10:00:00+03:00"},
            {"ID": "4", "OWNER_ID": None, "CREATED_TIME": "2026-03-15T10:00:00+03:00"},
        ]

    import src.sync_rejections as sr

    orig = sr._fetch_all
    sr._fetch_all = fake_fetch_all
    try:
        latest = fetch_sales_lose_dates(FakeBx(), "2026-01-01")
    finally:
        sr._fetch_all = orig

    assert calls["method"] == "crm.stagehistory.list"
    assert calls["filter"]["STAGE_ID"] == "C10:LOSE"
    assert calls["filter"]["CATEGORY_ID"] == 10
    # сделка 100 переходила дважды — берём ПОСЛЕДНИЙ переход (май)
    assert latest[100] == "2026-05-20T10:00:00+03:00"
    assert latest[200] == "2026-03-15T10:00:00+03:00"
    assert None not in latest and len(latest) == 2
