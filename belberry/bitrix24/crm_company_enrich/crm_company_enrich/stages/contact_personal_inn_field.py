"""Проверка UF-поля контакта для ИНН физлица руководителя."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import CONTACT_PERSONAL_INN_FIELD

PERSONAL_INN_FIELD_NAME = CONTACT_PERSONAL_INN_FIELD
PERSONAL_INN_FIELD_LABEL = "ИНН физлица"


@dataclass(frozen=True)
class ContactPersonalInnFieldPlan:
    action: str
    field_name: str
    field_id: str = ""
    payload: dict[str, Any] | None = None


def run(bx, *, apply: bool = False, verify: bool = True) -> dict[str, Any]:
    """Idempotent verify/create stage.

    На belberrycrm поле уже существует (`UF_CRM_67BC250A96BEB`, title="инн"),
    поэтому без явного `--apply` команда только проверяет состояние.
    """
    fields = bx.get_contact_user_fields()
    existing = _find_field(fields)
    plan = build_plan(existing)
    result: dict[str, Any] = {
        "dry_run": not apply,
        "action": plan.action,
        "field_name": plan.field_name,
        "field_id": plan.field_id,
    }
    if not apply:
        result["payload"] = plan.payload
        result["verification"] = verify_field(existing)
        return result

    if plan.action == "create":
        result["field_id"] = bx.add_contact_user_field(plan.payload or {})
        result["created"] = True
    elif plan.action == "update":
        result["updated"] = bx.update_contact_user_field(plan.field_id, plan.payload or {})
    else:
        result["unchanged"] = True

    if verify:
        verified = _find_field(bx.get_contact_user_fields())
        result["verification"] = verify_field(verified)
    return result


def build_plan(existing: dict | None) -> ContactPersonalInnFieldPlan:
    if existing is None:
        return ContactPersonalInnFieldPlan(
            action="create",
            field_name=PERSONAL_INN_FIELD_NAME,
            payload=_field_payload(),
        )
    needs_update = (
        str(existing.get("USER_TYPE_ID") or "") != "string"
        or str(existing.get("FIELD_NAME") or "") != PERSONAL_INN_FIELD_NAME
        or not _labels_are_current(existing)
        or not _visibility_flags_are_current(existing)
    )
    return ContactPersonalInnFieldPlan(
        action="update" if needs_update else "noop",
        field_name=PERSONAL_INN_FIELD_NAME,
        field_id=str(existing.get("ID") or ""),
        payload=_field_payload() if needs_update else None,
    )


def verify_field(field: dict | None) -> dict[str, Any]:
    if not field:
        return {"ok": False, "reason": "field_not_found"}
    checks = {
        "field_name_matches": str(field.get("FIELD_NAME") or "") == PERSONAL_INN_FIELD_NAME,
        "user_type_is_string": str(field.get("USER_TYPE_ID") or "") == "string",
        "labels_ok": _labels_are_current(field),
        "visibility_ok": _visibility_flags_are_current(field),
    }
    ok = all(checks.values())
    result = {
        "ok": ok,
        "field_id": str(field.get("ID") or ""),
        "field_name": str(field.get("FIELD_NAME") or ""),
        "user_type_id": str(field.get("USER_TYPE_ID") or ""),
        "available_in_api": bool(field.get("FIELD_NAME")),
    }
    if not ok:
        result["checks"] = checks
    return result


def _find_field(fields: list[dict]) -> dict | None:
    for field in fields:
        if str(field.get("FIELD_NAME") or "") == PERSONAL_INN_FIELD_NAME:
            return field
    return None


def _field_payload() -> dict[str, Any]:
    return {
        "FIELD_NAME": PERSONAL_INN_FIELD_NAME,
        "USER_TYPE_ID": "string",
        "XML_ID": PERSONAL_INN_FIELD_NAME,
        "SORT": 600,
        "MULTIPLE": "N",
        "MANDATORY": "N",
        "SHOW_FILTER": "Y",
        "SHOW_IN_LIST": "N",
        "EDIT_IN_LIST": "Y",
        "EDIT_FORM_LABEL": PERSONAL_INN_FIELD_LABEL,
        "LIST_COLUMN_LABEL": PERSONAL_INN_FIELD_LABEL,
        "LIST_FILTER_LABEL": PERSONAL_INN_FIELD_LABEL,
        "SETTINGS": {
            "DEFAULT_VALUE": "",
        },
    }


def _labels_are_current(field: dict) -> bool:
    label_keys = ("EDIT_FORM_LABEL", "LIST_COLUMN_LABEL", "LIST_FILTER_LABEL")
    if not any(key in field for key in label_keys):
        return True
    labels = [str(field.get(key) or "").strip().lower() for key in label_keys if key in field]
    return all(label in {"инн", PERSONAL_INN_FIELD_LABEL.lower()} for label in labels)


def _visibility_flags_are_current(field: dict) -> bool:
    return (
        str(field.get("SHOW_FILTER") or "").upper() in {"E", "I", "Y"}
        and str(field.get("SHOW_IN_LIST") or "").upper() == "N"
        and str(field.get("EDIT_IN_LIST") or "").upper() in {"Y", "1"}
    )
