from src.sync_rejections import build_rejection_rows


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
        },
        {"ID": "40", "STAGE_ID": "C50:LOSE", "UF_CRM_1771324790": None, "MODIFY_BY_ID": "1"},
        {"STAGE_ID": "C50:APOLOGY"},  # без ID — пропускаем
    ]
    rows = build_rejection_rows(deals)
    assert len(rows) == 2
    assert rows[0]["deal_id"] == 28
    assert rows[0]["reason_id"] == 8550
    assert rows[0]["modified_by"] == 2832
    assert rows[0]["stage_id"] == "C50:APOLOGY"
    assert rows[0]["rejected_at"] is not None
    assert rows[1]["deal_id"] == 40
    assert rows[1]["reason_id"] is None  # причина не указана
    assert rows[1]["modified_by"] == 1
