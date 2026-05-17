"""Создание и синхронизация поля компании «Область»."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from ..region_rf_config import (
    REGION_RF_FIELD_LABEL,
    REGION_RF_FIELD_NAME,
    REGION_RF_FIELD_XML_ID,
    REGION_RF_VALUES,
)


@dataclass(frozen=True)
class RegionFieldPlan:
    action: str
    field_name: str
    field_id: str = ""
    enum_count: int = 0
    missing_values: tuple[str, ...] = ()
    extra_values: tuple[str, ...] = ()
    payload: dict[str, Any] | None = None


def run(bx, *, apply: bool = False, verify: bool = True) -> dict[str, Any]:
    """Idempotent-синхронизация поля «Область» на компании.

    По умолчанию только строит план. Реальная запись в Bitrix выполняется
    только при apply=True.
    """
    fields = bx.get_company_user_fields()
    existing = _find_region_field(fields)
    plan = build_plan(existing)

    result: dict[str, Any] = {
        "dry_run": not apply,
        "action": plan.action,
        "field_name": plan.field_name,
        "field_id": plan.field_id,
        "enum_count": plan.enum_count,
        "missing_values": list(plan.missing_values),
        "extra_values": list(plan.extra_values),
    }
    if not apply:
        result["payload"] = plan.payload
        return result

    if plan.action == "create":
        result["field_id"] = bx.add_company_user_field(plan.payload or {})
        result["created"] = True
    elif plan.action == "update":
        result["updated"] = bx.update_company_user_field(plan.field_id, plan.payload or {})
    else:
        result["unchanged"] = True

    if verify:
        verified = _find_region_field(bx.get_company_user_fields())
        result["verification"] = verify_field(verified)
    return result


def build_plan(existing: dict | None) -> RegionFieldPlan:
    if existing is None:
        payload = _field_payload()
        return RegionFieldPlan(
            action="create",
            field_name=REGION_RF_FIELD_NAME,
            enum_count=len(REGION_RF_VALUES),
            missing_values=tuple(REGION_RF_VALUES),
            payload=payload,
        )

    existing_values = _enum_values(existing)
    desired_values = set(REGION_RF_VALUES)
    missing = tuple(value for value in REGION_RF_VALUES if value not in existing_values)
    extra = tuple(value for value in sorted(existing_values - desired_values, key=str.casefold))
    needs_update = (
        str(existing.get("USER_TYPE_ID") or "") != "enumeration"
        or str(existing.get("FIELD_NAME") or "") != REGION_RF_FIELD_NAME
        or str(existing.get("XML_ID") or "") != REGION_RF_FIELD_XML_ID
        or missing
        or extra
        or not _labels_are_current(existing)
        or not _visibility_flags_are_current(existing)
    )
    return RegionFieldPlan(
        action="update" if needs_update else "noop",
        field_name=REGION_RF_FIELD_NAME,
        field_id=str(existing.get("ID") or ""),
        enum_count=len(REGION_RF_VALUES),
        missing_values=missing,
        extra_values=extra,
        payload=_field_payload(existing) if needs_update else None,
    )


def verify_field(field: dict | None) -> dict[str, Any]:
    if not field:
        return {"ok": False, "reason": "field_not_found"}
    enum_values = _enum_values(field)
    desired_values = set(REGION_RF_VALUES)
    ok = (
        str(field.get("FIELD_NAME") or "") == REGION_RF_FIELD_NAME
        and str(field.get("USER_TYPE_ID") or "") == "enumeration"
        and enum_values == desired_values
        and _labels_are_current(field)
        and _visibility_flags_are_current(field)
    )
    return {
        "ok": ok,
        "field_id": str(field.get("ID") or ""),
        "field_name": str(field.get("FIELD_NAME") or ""),
        "user_type_id": str(field.get("USER_TYPE_ID") or ""),
        "enum_count": len(enum_values),
        "missing_values": [value for value in REGION_RF_VALUES if value not in enum_values],
        "extra_values": sorted(enum_values - desired_values, key=str.casefold),
        "arbitrary_text_blocked_by_type": str(field.get("USER_TYPE_ID") or "") == "enumeration",
        "filterable": str(field.get("SHOW_FILTER") or "").upper() in {"E", "I", "Y"},
        "visible_in_list": str(field.get("SHOW_IN_LIST") or "").upper() == "Y",
        "editable_in_list": str(field.get("EDIT_IN_LIST") or "").upper() == "Y",
        "available_in_api": bool(field.get("FIELD_NAME")),
    }


def _find_region_field(fields: list[dict]) -> dict | None:
    for field in fields:
        if str(field.get("FIELD_NAME") or "") == REGION_RF_FIELD_NAME:
            return field
    for field in fields:
        if str(field.get("XML_ID") or "") == REGION_RF_FIELD_XML_ID:
            return field
    return None


def _field_payload(existing: dict | None = None) -> dict[str, Any]:
    payload = {
        "FIELD_NAME": REGION_RF_FIELD_NAME,
        "USER_TYPE_ID": "enumeration",
        "XML_ID": REGION_RF_FIELD_XML_ID,
        "SORT": 500,
        "MULTIPLE": "N",
        "MANDATORY": "N",
        "SHOW_FILTER": "Y",
        "SHOW_IN_LIST": "Y",
        "EDIT_IN_LIST": "Y",
        "IS_SEARCHABLE": "Y",
        "EDIT_FORM_LABEL": REGION_RF_FIELD_LABEL,
        "LIST_COLUMN_LABEL": REGION_RF_FIELD_LABEL,
        "LIST_FILTER_LABEL": REGION_RF_FIELD_LABEL,
        "ERROR_MESSAGE": "",
        "HELP_MESSAGE": "",
        "LIST": _enum_payload(existing),
        "SETTINGS": {
            "DISPLAY": "LIST",
            "LIST_HEIGHT": 1,
            "CAPTION_NO_VALUE": "",
            "SHOW_NO_VALUE": "Y",
        },
    }
    return payload


def _enum_payload(existing: dict | None = None) -> list[dict[str, Any]]:
    existing_by_xml = _existing_enum_by_xml_id(existing)
    existing_by_value = _existing_enum_by_value(existing)
    existing_by_normalized_value = _existing_enum_by_normalized_value(existing)
    items: list[dict[str, Any]] = []
    for index, value in enumerate(REGION_RF_VALUES, start=1):
        xml_id = _enum_xml_id(value)
        existing_item = (
            existing_by_xml.get(xml_id)
            or existing_by_value.get(value)
            or existing_by_normalized_value.get(_normalize_region_key(value))
        )
        item = {
            "VALUE": value,
            "SORT": index * 10,
            "DEF": "N",
            "XML_ID": xml_id,
        }
        if existing_item and existing_item.get("ID"):
            item["ID"] = str(existing_item["ID"])
        items.append(item)
    return items


def _enum_xml_id(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12].upper()
    return f"REGION_RF_{digest}"


def _enum_values(field: dict | None) -> set[str]:
    values: set[str] = set()
    for item in _enum_items(field):
        value = str(item.get("VALUE") or "").strip()
        if value:
            values.add(value)
    return values


def _enum_items(field: dict | None) -> list[dict]:
    if not field:
        return []
    raw = field.get("LIST") or []
    return raw if isinstance(raw, list) else []


def _existing_enum_by_xml_id(field: dict | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in _enum_items(field):
        xml_id = str(item.get("XML_ID") or "").strip()
        if xml_id:
            out[xml_id] = item
    return out


def _existing_enum_by_value(field: dict | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in _enum_items(field):
        value = str(item.get("VALUE") or "").strip()
        if value:
            out[value] = item
    return out


def _existing_enum_by_normalized_value(field: dict | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in _enum_items(field):
        value = str(item.get("VALUE") or "").strip()
        if value:
            out[_normalize_region_key(value)] = item
    return out


def _normalize_region_key(raw_region: str) -> str:
    norm = str(raw_region or "").strip().lower()
    norm = re.sub(r"\([^)]*\)", "", norm)
    norm = re.split(r"\s+[—-]\s+", norm, maxsplit=1)[0]
    for token in (
        "автономный округ",
        "народная",
        "республика",
        "область",
        "край",
        "обл.",
        "обл ",
        "респ.",
        "респ ",
        "ао",
        "г.",
        "город ",
    ):
        norm = norm.replace(token, "")
    return re.sub(r"\s+", " ", norm).strip(" .,-")


def _labels_are_current(field: dict) -> bool:
    label_keys = ("EDIT_FORM_LABEL", "LIST_COLUMN_LABEL", "LIST_FILTER_LABEL")
    if not any(key in field for key in label_keys):
        return True
    return all(
        str(field.get(key) or "") == REGION_RF_FIELD_LABEL
        for key in label_keys
    )


def _visibility_flags_are_current(field: dict) -> bool:
    return (
        str(field.get("SHOW_FILTER") or "").upper() in {"E", "I", "Y"}
        and str(field.get("SHOW_IN_LIST") or "").upper() == "Y"
        and str(field.get("EDIT_IN_LIST") or "").upper() == "Y"
        and str(field.get("IS_SEARCHABLE") or "").upper() == "Y"
    )
