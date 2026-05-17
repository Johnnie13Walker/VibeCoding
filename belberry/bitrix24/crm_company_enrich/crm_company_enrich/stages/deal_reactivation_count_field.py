"""Создание и синхронизация поля сделки UF_CRM_REACTIVATION_COUNT."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REACTIVATION_COUNT_FIELD_NAME = "UF_CRM_REACTIVATION_COUNT"
REACTIVATION_COUNT_FIELD_LABEL = "Реактиваций из ОТВАЛ"


@dataclass(frozen=True)
class ReactivationCountFieldPlan:
    action: str
    field_name: str
    field_id: str = ""
    payload: dict[str, Any] | None = None


def run(bx, *, apply: bool = False, verify: bool = True) -> dict[str, Any]:
    """Idempotent создание/верификация UF_CRM_REACTIVATION_COUNT integer."""
    fields = bx.get_deal_user_fields()
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
        return result

    if plan.action == "create":
        result["field_id"] = bx.add_deal_user_field(plan.payload or {})
        result["created"] = True
    elif plan.action == "update":
        result["updated"] = bx.update_deal_user_field(plan.field_id, plan.payload or {})
    else:
        result["unchanged"] = True

    if verify:
        verified = _find_field(bx.get_deal_user_fields())
        result["verification"] = verify_field(verified)
    return result


def build_plan(existing: dict | None) -> ReactivationCountFieldPlan:
    if existing is None:
        return ReactivationCountFieldPlan(
            action="create",
            field_name=REACTIVATION_COUNT_FIELD_NAME,
            payload=_field_payload(),
        )
    needs_update = (
        str(existing.get("USER_TYPE_ID") or "") != "integer"
        or str(existing.get("FIELD_NAME") or "") != REACTIVATION_COUNT_FIELD_NAME
        or str(existing.get("XML_ID") or "") != REACTIVATION_COUNT_FIELD_NAME
        or not _labels_are_current(existing)
        or not _settings_are_current(existing)
        or not _visibility_flags_are_current(existing)
    )
    return ReactivationCountFieldPlan(
        action="update" if needs_update else "noop",
        field_name=REACTIVATION_COUNT_FIELD_NAME,
        field_id=str(existing.get("ID") or ""),
        payload=_field_payload() if needs_update else None,
    )


def verify_field(field: dict | None) -> dict[str, Any]:
    if not field:
        return {"ok": False, "reason": "field_not_found"}
    checks = {
        "field_name_matches": str(field.get("FIELD_NAME") or "") == REACTIVATION_COUNT_FIELD_NAME,
        "user_type_is_integer": str(field.get("USER_TYPE_ID") or "") == "integer",
        "labels_ok": _labels_are_current(field),
        "settings_ok": _settings_are_current(field),
        "visibility_ok": _visibility_flags_are_current(field),
    }
    ok = all(checks.values())
    result = {
        "ok": ok,
        "field_id": str(field.get("ID") or ""),
        "field_name": str(field.get("FIELD_NAME") or ""),
        "user_type_id": str(field.get("USER_TYPE_ID") or ""),
        "filterable": str(field.get("SHOW_FILTER") or "").upper() in {"E", "I", "Y"},
        "visible_in_list": str(field.get("SHOW_IN_LIST") or "").upper() == "N",
        "editable_in_list": str(field.get("EDIT_IN_LIST") or "").upper() == "N",
        "available_in_api": bool(field.get("FIELD_NAME")),
    }
    if not ok:
        result["checks"] = checks
    return result


def _find_field(fields: list[dict]) -> dict | None:
    for field in fields:
        if str(field.get("FIELD_NAME") or "") == REACTIVATION_COUNT_FIELD_NAME:
            return field
    for field in fields:
        if str(field.get("XML_ID") or "") == REACTIVATION_COUNT_FIELD_NAME:
            return field
    return None


def _field_payload() -> dict[str, Any]:
    return {
        "FIELD_NAME": REACTIVATION_COUNT_FIELD_NAME,
        "USER_TYPE_ID": "integer",
        "XML_ID": REACTIVATION_COUNT_FIELD_NAME,
        "SORT": 610,
        "MULTIPLE": "N",
        "MANDATORY": "N",
        "SHOW_FILTER": "Y",
        "SHOW_IN_LIST": "N",
        "EDIT_IN_LIST": "N",
        "EDIT_FORM_LABEL": REACTIVATION_COUNT_FIELD_LABEL,
        "LIST_COLUMN_LABEL": REACTIVATION_COUNT_FIELD_LABEL,
        "LIST_FILTER_LABEL": REACTIVATION_COUNT_FIELD_LABEL,
        "ERROR_MESSAGE": "",
        "HELP_MESSAGE": "",
        "SETTINGS": {
            "DEFAULT_VALUE": "0",
            "MIN_VALUE": 0,
        },
    }


def _labels_are_current(field: dict) -> bool:
    label_keys = ("EDIT_FORM_LABEL", "LIST_COLUMN_LABEL", "LIST_FILTER_LABEL")
    if not any(key in field for key in label_keys):
        return True
    return all(
        str(field.get(key) or "") == REACTIVATION_COUNT_FIELD_LABEL
        for key in label_keys
    )


def _settings_are_current(field: dict) -> bool:
    settings = field.get("SETTINGS") or {}
    return (
        str(settings.get("DEFAULT_VALUE", "")) == "0"
        and str(settings.get("MIN_VALUE", "")) == "0"
    )


def _visibility_flags_are_current(field: dict) -> bool:
    return (
        str(field.get("SHOW_FILTER") or "").upper() in {"E", "I", "Y"}
        and str(field.get("SHOW_IN_LIST") or "").upper() == "N"
        and str(field.get("EDIT_IN_LIST") or "").upper() == "N"
    )
