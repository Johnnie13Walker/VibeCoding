#!/usr/bin/env python3
"""Регистрация действия БП Bitrix для синхронизации контактов компании в сделки."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAPIError, BitrixAppAuth
from scripts.run_sales_copilot import (
    DEFAULT_REMOTE_ENV_FILE,
    DEFAULT_REMOTE_STATE_DIR,
    _build_agent_env,
    _fetch_remote_env,
    _load_runtime_env,
    _resolve_remote_host,
    _sync_remote_state,
)

ACTIVITY_CODE = "cloudbot_sync_deal_company_contacts"
DEFAULT_HANDLER_URL = "https://api.larisabot.ru/bitrix/app/sync-deal-contacts"
DEFAULT_TEMPLATE_ID = "5938"


def _load_auth_env(*, use_remote_bridge: bool) -> tuple[BitrixAppAuth, tempfile.TemporaryDirectory[str] | None]:
    env = _load_runtime_env()
    if not use_remote_bridge:
        return BitrixAppAuth.from_env(env), None

    remote_host = _resolve_remote_host(env)
    remote_env_file = str(env.get("SALES_REMOTE_ENV_FILE") or DEFAULT_REMOTE_ENV_FILE).strip() or DEFAULT_REMOTE_ENV_FILE
    remote_state_dir = str(env.get("SALES_REMOTE_STATE_DIR") or DEFAULT_REMOTE_STATE_DIR).strip() or DEFAULT_REMOTE_STATE_DIR
    remote_env = _fetch_remote_env(env, remote_host, remote_env_file)
    tmp_root = ROOT_DIR / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp_dir = tempfile.TemporaryDirectory(prefix="bitrix-bizproc-sync-contacts-state-", dir=str(tmp_root))
    state_root = _sync_remote_state(env, remote_host, remote_state_dir, Path(tmp_dir.name))
    agent_env = _build_agent_env(env, remote_env, state_root, ROOT_DIR)
    return BitrixAppAuth.from_env(agent_env), tmp_dir


def _int_or(value: Any, default: int) -> int:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _auth_user_id(auth: BitrixAppAuth, explicit: str) -> int:
    if explicit:
        return _int_or(explicit, 0)
    profile = auth.call_method("profile", {}, default={})
    if isinstance(profile, Mapping):
        return _int_or(profile.get("ID"), 0)
    return 0


def activity_fields(*, handler_url: str, auth_user_id: int) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "HANDLER": handler_url,
        "USE_SUBSCRIPTION": "N",
        "NAME": {
            "ru": "Cloudbot: синхронизировать контакты компании в сделки",
            "en": "Cloudbot: sync company contacts to deals",
        },
        "DESCRIPTION": {
            "ru": "Add-only добавляет контакты компании во все связанные сделки. Существующие контакты сделки не удаляются.",
            "en": "Adds missing company contacts to related deals without removing existing deal contacts.",
        },
        "PROPERTIES": {
            "companyId": {
                "Name": {"ru": "ID компании", "en": "Company ID"},
                "Description": {"ru": "Обычно {=Document:ID}", "en": "Usually {=Document:ID}"},
                "Type": "string",
                "Required": "Y",
                "Multiple": "N",
                "Default": "{=Document:ID}",
            },
            "dealId": {
                "Name": {"ru": "ID сделки", "en": "Deal ID"},
                "Description": {
                    "ru": "Необязательно. Если пусто, обработаются все сделки компании.",
                    "en": "Optional. If empty, all company deals will be processed.",
                },
                "Type": "string",
                "Required": "N",
                "Multiple": "N",
                "Default": "",
            },
            "syncClosedDeals": {
                "Name": {"ru": "Синхронизировать закрытые сделки", "en": "Sync closed deals"},
                "Type": "bool",
                "Required": "N",
                "Multiple": "N",
                "Default": "Y",
            },
            "maxDeals": {
                "Name": {"ru": "Максимум сделок", "en": "Max deals"},
                "Type": "int",
                "Required": "N",
                "Multiple": "N",
                "Default": "50",
            },
        },
        "DOCUMENT_TYPE": ["crm", "CCrmDocumentCompany", "COMPANY"],
        "FILTER": {"INCLUDE": [["crm", "CCrmDocumentCompany"]]},
    }
    if auth_user_id > 0:
        fields["AUTH_USER_ID"] = auth_user_id
    return fields


def register_activity(
    auth: BitrixAppAuth,
    *,
    handler_url: str,
    auth_user_id: int,
    apply_changes: bool,
) -> dict[str, Any]:
    fields = activity_fields(handler_url=handler_url, auth_user_id=auth_user_id)
    installed = auth.call_method("bizproc.activity.list", {}, default=[])
    installed_codes = [str(item) for item in installed] if isinstance(installed, list) else []
    exists = ACTIVITY_CODE in installed_codes
    operation = "update" if exists else "add"
    payload: dict[str, Any] = {
        "ok": True,
        "status": "dry_run",
        "activity_code": ACTIVITY_CODE,
        "handler_url": handler_url,
        "auth_user_id": auth_user_id,
        "operation": operation,
        "installed_before": exists,
        "fields": fields,
    }
    if not apply_changes:
        return payload

    if exists:
        result = auth.call_method("bizproc.activity.update", {"CODE": ACTIVITY_CODE, "FIELDS": fields}, default=None)
    else:
        try:
            result = auth.call_method("bizproc.activity.add", {"CODE": ACTIVITY_CODE, **fields}, default=None)
        except BitrixAPIError as error:
            if error.code != "ERROR_ACTIVITY_ALREADY_INSTALLED":
                raise
            result = auth.call_method("bizproc.activity.update", {"CODE": ACTIVITY_CODE, "FIELDS": fields}, default=None)
            operation = "update_after_already_installed"

    payload.update(
        {
            "status": "applied",
            "operation": operation,
            "result": result,
            "installed_after": ACTIVITY_CODE in [str(item) for item in auth.call_method("bizproc.activity.list", {}, default=[])],
        }
    )
    return payload


def inspect_template(auth: BitrixAppAuth, *, template_id: str) -> dict[str, Any]:
    payload = auth.call_payload(
        "bizproc.workflow.template.list",
        {
            "select": [
                "ID",
                "MODULE_ID",
                "ENTITY",
                "DOCUMENT_TYPE",
                "AUTO_EXECUTE",
                "NAME",
                "PARAMETERS",
                "VARIABLES",
                "CONSTANTS",
                "MODIFIED",
                "IS_MODIFIED",
                "USER_ID",
                "SYSTEM_CODE",
            ],
            "filter": {"ID": template_id},
        },
        default={},
    )
    result = payload.get("result") if isinstance(payload, Mapping) else None
    template = result[0] if isinstance(result, list) and result else None
    return {
        "ok": bool(template),
        "template_id": str(template_id),
        "template": template,
        "raw_total": payload.get("total") if isinstance(payload, Mapping) else None,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Регистрация действия БП для sync deal-company contacts.")
    parser.add_argument(
        "mode",
        choices=("register-activity", "inspect-template"),
        nargs="?",
        default=os.environ.get("BITRIX_BIZPROC_SYNC_CONTACTS_MODE", "register-activity"),
    )
    parser.add_argument("--handler-url", default=os.environ.get("BITRIX_BIZPROC_SYNC_CONTACTS_HANDLER_URL", DEFAULT_HANDLER_URL))
    parser.add_argument("--auth-user-id", default=os.environ.get("BITRIX_BIZPROC_SYNC_CONTACTS_AUTH_USER_ID", ""))
    parser.add_argument("--template-id", default=os.environ.get("BITRIX_BIZPROC_SYNC_CONTACTS_TEMPLATE_ID", DEFAULT_TEMPLATE_ID))
    parser.add_argument("--apply", action="store_true", default=os.environ.get("BITRIX_BIZPROC_SYNC_CONTACTS_APPLY") == "1")
    parser.add_argument("--json", action="store_true", default=os.environ.get("BITRIX_BIZPROC_SYNC_CONTACTS_JSON") == "1")
    parser.add_argument("--no-remote-bridge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    auth, tmp_dir = _load_auth_env(use_remote_bridge=not args.no_remote_bridge)
    try:
        if args.mode == "register-activity":
            auth_user_id = _auth_user_id(auth, str(args.auth_user_id or ""))
            payload = register_activity(
                auth,
                handler_url=str(args.handler_url),
                auth_user_id=auth_user_id,
                apply_changes=bool(args.apply),
            )
        else:
            payload = inspect_template(auth, template_id=str(args.template_id))
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
