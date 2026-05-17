from crm_company_enrich.stages import contact_personal_inn_field as stage


class FakeBitrix:
    def __init__(self, fields=None):
        self.fields = fields or []
        self.add_calls = []
        self.update_calls = []

    def get_contact_user_fields(self):
        return list(self.fields)

    def add_contact_user_field(self, fields):
        self.add_calls.append(dict(fields))
        created = dict(fields)
        created["ID"] = "99"
        self.fields.append(created)
        return "99"

    def update_contact_user_field(self, field_id, fields):
        self.update_calls.append((str(field_id), dict(fields)))
        updated = dict(fields)
        updated["ID"] = str(field_id)
        self.fields = [updated if str(f.get("ID")) == str(field_id) else f for f in self.fields]
        return True


def _field(**overrides):
    field = {
        "ID": "77",
        "FIELD_NAME": "UF_CRM_67BC250A96BEB",
        "USER_TYPE_ID": "string",
        "EDIT_FORM_LABEL": "инн",
        "LIST_COLUMN_LABEL": "инн",
        "LIST_FILTER_LABEL": "инн",
        "SHOW_FILTER": "Y",
        "SHOW_IN_LIST": "N",
        "EDIT_IN_LIST": "Y",
    }
    field.update(overrides)
    return field


def test_dry_run_create_payload():
    summary = stage.run(FakeBitrix())

    assert summary["dry_run"] is True
    assert summary["action"] == "create"
    assert summary["payload"]["FIELD_NAME"] == "UF_CRM_67BC250A96BEB"
    assert summary["payload"]["USER_TYPE_ID"] == "string"


def test_apply_creates_field():
    bx = FakeBitrix()

    summary = stage.run(bx, apply=True)

    assert summary["created"] is True
    assert bx.add_calls
    assert summary["verification"]["ok"] is True


def test_existing_field_noop():
    summary = stage.run(FakeBitrix([_field()]))

    assert summary["action"] == "noop"
    assert summary["verification"]["ok"] is True


def test_verify_tolerant_to_missing_labels():
    field = _field()
    field.pop("EDIT_FORM_LABEL")
    field.pop("LIST_COLUMN_LABEL")
    field.pop("LIST_FILTER_LABEL")

    result = stage.verify_field(field)

    assert result["ok"] is True
