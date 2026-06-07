from src.sync_rejections import (
    REASON_FIELD_10,
    REASON_FIELD_50,
    build_rejection_rows,
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


def test_build_rejection_rows_cat10_reason_field_and_list_value():
    deals = [
        {
            "ID": "23946",
            "CATEGORY_ID": "10",
            "STAGE_ID": "C10:LOSE",
            # cat10 использует своё поле причины; значение может прийти списком
            "UF_CRM_1771495464": ["8584"],
            "MODIFY_BY_ID": "12",
            "ASSIGNED_BY_ID": "2806",
            "DATE_MODIFY": "2026-04-11T18:30:00+03:00",
            "TITLE": "panaceadoc.ru",
            "OPPORTUNITY": "320000",
        },
    ]
    rows = build_rejection_rows(deals, REASON_FIELD_10)
    assert len(rows) == 1
    assert rows[0]["deal_id"] == 23946
    assert rows[0]["category_id"] == 10
    assert rows[0]["stage_id"] == "C10:LOSE"
    assert rows[0]["reason_id"] == 8584  # первый код из списка
    assert rows[0]["assigned_by"] == 2806
    assert rows[0]["opportunity"] == 320000.0
