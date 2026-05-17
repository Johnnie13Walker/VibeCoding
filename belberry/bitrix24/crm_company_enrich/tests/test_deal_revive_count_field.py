from __future__ import annotations

from crm_company_enrich.stages import deal_revive_count_field as stage


class FakeBitrix:
    def __init__(self, fields: list[dict] | None = None):
        self.fields = fields or []
        self.add_calls: list[dict] = []
        self.update_calls: list[tuple[str, dict]] = []

    def get_deal_user_fields(self):
        return list(self.fields)

    def add_deal_user_field(self, fields: dict) -> str:
        self.add_calls.append(dict(fields))
        created = dict(fields)
        created["ID"] = "77"
        self.fields.append(created)
        return "77"

    def update_deal_user_field(self, field_id: str, fields: dict) -> bool:
        self.update_calls.append((str(field_id), dict(fields)))
        updated = dict(fields)
        updated["ID"] = str(field_id)
        self.fields = [updated if str(f.get("ID")) == str(field_id) else f for f in self.fields]
        return True


def _bitrix_integer_field(**overrides):
    field = {
        "ID": "77",
        "FIELD_NAME": "UF_CRM_REVIVE_COUNT",
        "USER_TYPE_ID": "integer",
        "XML_ID": "UF_CRM_REVIVE_COUNT",
        "SHOW_FILTER": "E",
        "SHOW_IN_LIST": "N",
        "EDIT_IN_LIST": "N",
        "SETTINGS": {
            "DEFAULT_VALUE": 0,
            "MIN_VALUE": 0,
            "MAX_VALUE": 0,
            "SIZE": 20,
        },
    }
    field.update(overrides)
    return field


def test_dry_run_creates_integer_payload():
    summary = stage.run(FakeBitrix())

    assert summary["dry_run"] is True
    assert summary["action"] == "create"
    assert summary["payload"]["FIELD_NAME"] == "UF_CRM_REVIVE_COUNT"
    assert summary["payload"]["USER_TYPE_ID"] == "integer"
    assert summary["payload"]["SETTINGS"]["DEFAULT_VALUE"] == "0"


def test_apply_creates_field_and_verifies():
    bx = FakeBitrix()

    summary = stage.run(bx, apply=True)

    assert summary["created"] is True
    assert bx.add_calls
    assert summary["verification"]["ok"] is True


def test_existing_correct_field_is_noop():
    bx = FakeBitrix([_bitrix_integer_field()])

    summary = stage.run(bx)

    assert summary["action"] == "noop"
    assert summary["payload"] is None


def test_existing_wrong_type_string_triggers_update():
    field = stage._field_payload() | {"ID": "77", "USER_TYPE_ID": "string"}
    bx = FakeBitrix([field])

    summary = stage.run(bx, apply=True)

    assert summary["updated"] is True
    assert bx.update_calls[0][0] == "77"
    assert bx.update_calls[0][1]["USER_TYPE_ID"] == "integer"


def test_verify_accepts_response_without_labels():
    result = stage.verify_field(_bitrix_integer_field())

    assert result["ok"] is True


def test_verify_accepts_bitrix_default_size_and_max_value():
    result = stage.verify_field(
        _bitrix_integer_field(
            SETTINGS={
                "DEFAULT_VALUE": 0,
                "MIN_VALUE": 0,
                "SIZE": 20,
                "MAX_VALUE": 0,
            }
        )
    )

    assert result["ok"] is True


def test_verify_rejects_when_labels_present_and_wrong():
    result = stage.verify_field(_bitrix_integer_field(EDIT_FORM_LABEL="Другое название"))

    assert result["ok"] is False
    assert result["checks"]["labels_ok"] is False


def test_verify_includes_checks_breakdown_when_failing():
    result = stage.verify_field(_bitrix_integer_field(USER_TYPE_ID="string"))

    assert result["ok"] is False
    assert result["checks"] == {
        "field_name_matches": True,
        "user_type_is_integer": False,
        "labels_ok": True,
        "settings_ok": True,
        "visibility_ok": True,
    }


def test_verify_rejects_wrong_default_value():
    result = stage.verify_field(
        _bitrix_integer_field(
            SETTINGS={
                "DEFAULT_VALUE": 5,
                "MIN_VALUE": 0,
                "SIZE": 20,
                "MAX_VALUE": 0,
            }
        )
    )

    assert result["ok"] is False
    assert result["checks"]["settings_ok"] is False
