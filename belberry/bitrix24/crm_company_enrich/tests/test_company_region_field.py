from __future__ import annotations

from crm_company_enrich.region_rf_config import (
    REGION_RF_FIELD_LABEL,
    REGION_RF_FIELD_NAME,
    REGION_RF_VALUES,
)
from crm_company_enrich.stages import company_region_field as stage


class FakeBitrix:
    def __init__(self, fields: list[dict] | None = None):
        self.fields = fields or []
        self.add_calls: list[dict] = []
        self.update_calls: list[tuple[str, dict]] = []

    def get_company_user_fields(self):
        return list(self.fields)

    def add_company_user_field(self, fields):
        self.add_calls.append(fields)
        created = dict(fields)
        created["ID"] = "100"
        self.fields = [created]
        return "100"

    def update_company_user_field(self, field_id, fields):
        self.update_calls.append((str(field_id), fields))
        updated = dict(fields)
        updated["ID"] = str(field_id)
        self.fields = [updated]
        return True


def _existing_field(**overrides):
    field = {
        "ID": "42",
        "FIELD_NAME": REGION_RF_FIELD_NAME,
        "USER_TYPE_ID": "enumeration",
        "XML_ID": REGION_RF_FIELD_NAME,
        "SHOW_FILTER": "Y",
        "SHOW_IN_LIST": "Y",
        "EDIT_IN_LIST": "Y",
        "IS_SEARCHABLE": "Y",
        "EDIT_FORM_LABEL": REGION_RF_FIELD_LABEL,
        "LIST_COLUMN_LABEL": REGION_RF_FIELD_LABEL,
        "LIST_FILTER_LABEL": REGION_RF_FIELD_LABEL,
        "LIST": [
            {
                "ID": str(index),
                "VALUE": value,
                "SORT": index * 10,
                "DEF": "N",
                "XML_ID": stage._enum_xml_id(value),
            }
            for index, value in enumerate(REGION_RF_VALUES, start=1)
        ],
    }
    field.update(overrides)
    return field


def test_region_values_are_sorted_and_include_federal_cities():
    assert list(REGION_RF_VALUES) == sorted(REGION_RF_VALUES, key=str.casefold)
    assert "Москва" in REGION_RF_VALUES
    assert "Санкт-Петербург" in REGION_RF_VALUES
    assert "Севастополь" in REGION_RF_VALUES


def test_region_values_count_matches_business_list():
    assert len(REGION_RF_VALUES) == 89


def test_dry_run_creates_enumeration_payload_without_writes():
    bx = FakeBitrix()

    summary = stage.run(bx)

    assert summary["dry_run"] is True
    assert summary["action"] == "create"
    assert summary["field_name"] == REGION_RF_FIELD_NAME
    assert summary["enum_count"] == len(REGION_RF_VALUES)
    assert bx.add_calls == []
    payload = summary["payload"]
    assert payload["USER_TYPE_ID"] == "enumeration"
    assert payload["SHOW_FILTER"] == "Y"
    assert payload["SHOW_IN_LIST"] == "Y"
    assert payload["EDIT_IN_LIST"] == "Y"
    assert payload["LIST"][0]["VALUE"] == REGION_RF_VALUES[0]


def test_apply_creates_field_and_verifies_it():
    bx = FakeBitrix()

    summary = stage.run(bx, apply=True)

    assert summary["dry_run"] is False
    assert summary["created"] is True
    assert summary["field_id"] == "100"
    assert summary["verification"]["ok"] is True
    assert summary["verification"]["arbitrary_text_blocked_by_type"] is True
    assert len(bx.add_calls) == 1


def test_existing_current_field_is_noop():
    bx = FakeBitrix([_existing_field()])

    summary = stage.run(bx)

    assert summary["action"] == "noop"
    assert "payload" not in summary or summary["payload"] is None
    assert bx.update_calls == []


def test_existing_field_update_preserves_enum_ids_and_removes_extra_values():
    existing = _existing_field(
        LIST=[
            {"ID": "10", "VALUE": "Москва", "SORT": 10, "DEF": "N", "XML_ID": stage._enum_xml_id("Москва")},
            {"ID": "99", "VALUE": "Произвольный регион", "SORT": 20, "DEF": "N", "XML_ID": "CUSTOM"},
        ]
    )
    bx = FakeBitrix([existing])

    summary = stage.run(bx)

    assert summary["action"] == "update"
    assert summary["extra_values"] == ["Произвольный регион"]
    payload = summary["payload"]
    moscow = [item for item in payload["LIST"] if item["VALUE"] == "Москва"][0]
    assert moscow["ID"] == "10"
    assert "Произвольный регион" not in [item["VALUE"] for item in payload["LIST"]]


def test_verify_rejects_string_field_type():
    field = _existing_field(USER_TYPE_ID="string")

    verification = stage.verify_field(field)

    assert verification["ok"] is False
    assert verification["arbitrary_text_blocked_by_type"] is False


def test_verify_accepts_bitrix_response_without_label_fields():
    field = _existing_field()
    for key in ("EDIT_FORM_LABEL", "LIST_COLUMN_LABEL", "LIST_FILTER_LABEL"):
        field.pop(key)

    verification = stage.verify_field(field)

    assert verification["ok"] is True
