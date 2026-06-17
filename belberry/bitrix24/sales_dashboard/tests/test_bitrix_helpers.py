"""Smoke-тесты на чистые helpers — не дергают Bitrix/Sheets."""
from __future__ import annotations

from sales_dashboard.bitrix_client import _flatten


def test_flatten_simple():
    assert _flatten({"a": "b"}) == [("a", "b")]


def test_flatten_nested_dict():
    out = _flatten({"filter": {"ID": 7, "STAGE_ID": "C50:NEW"}})
    assert ("filter[ID]", "7") in out
    assert ("filter[STAGE_ID]", "C50:NEW") in out


def test_flatten_list_of_scalars():
    out = _flatten({"select": ["ID", "TITLE"]})
    assert ("select[0]", "ID") in out
    assert ("select[1]", "TITLE") in out


def test_flatten_bool_to_yn():
    out = dict(_flatten({"ADMIN_MODE": True, "DISABLED": False}))
    assert out["ADMIN_MODE"] == "Y"
    assert out["DISABLED"] == "N"


def test_flatten_none():
    out = dict(_flatten({"x": None}))
    assert out["x"] == ""


def test_deal_row_basics():
    from sales_dashboard.extractors.deals import HEADER, _to_row

    row = _to_row(
        {
            "ID": "42",
            "TITLE": "Тест",
            "CATEGORY_ID": "50",
            "STAGE_ID": "C50:NEW",
            "STAGE_SEMANTIC_ID": "P",
            "CLOSED": "N",
            "OPPORTUNITY": "1500.50",
            "ASSIGNED_BY_ID": "7",
            "CREATED_BY_ID": "7",
            "COMPANY_ID": "100",
            "CONTACT_ID": "200",
            "DATE_CREATE": "2026-05-14T10:00:00+03:00",
        },
        portal_domain="belberrycrm.bitrix24.ru",
        user_names={7: "Иванов Иван"},
        stage_names={"C50:NEW": "Новая"},
        category_names={50: "Телемаркетинг"},
    )
    assert len(row) == len(HEADER)
    assert row[HEADER.index("deal_id")] == 42
    assert row[HEADER.index("category_id")] == 50
    assert row[HEADER.index("category_name")] == "Телемаркетинг"
    assert row[HEADER.index("stage_id")] == "C50:NEW"
    assert row[HEADER.index("stage_name")] == "Новая"
    assert row[HEADER.index("manager")] == "Иванов Иван"
    assert row[HEADER.index("opportunity")] == 1500.5
    assert row[HEADER.index("is_closed")] == "N"
    assert row[HEADER.index("url")].endswith("/crm/deal/details/42/")


def test_call_row_msk_split():
    from sales_dashboard.extractors.calls import HEADER, _to_row

    row = _to_row(
        {
            "ID": "9001",
            "CALL_TYPE": "1",
            "CALL_START_DATE": "2026-05-14T14:30:00+03:00",
            "CALL_DURATION": "45",
            "CALL_FAILED_CODE": "200",
            "PORTAL_USER_ID": "7",
            "PHONE_NUMBER": "+79001234567",
        },
        user_names={7: "Иванов Иван"},
    )
    assert len(row) == len(HEADER)
    assert row[HEADER.index("call_type_label")] == "outgoing"
    assert row[HEADER.index("date")] == "2026-05-14"
    assert row[HEADER.index("hour")] == 14
    assert row[HEADER.index("call_duration")] == 45
    assert row[HEADER.index("manager")] == "Иванов Иван"
    assert row[HEADER.index("is_answered")] == "Y"
