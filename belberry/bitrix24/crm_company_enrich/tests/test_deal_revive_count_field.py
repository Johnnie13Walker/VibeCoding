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
    bx = FakeBitrix([stage._field_payload() | {"ID": "77"}])

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
