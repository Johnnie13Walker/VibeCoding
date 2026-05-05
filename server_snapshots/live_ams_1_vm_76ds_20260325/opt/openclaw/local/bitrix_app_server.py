"""Минимальный HTTP-обработчик локального приложения Bitrix24."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def _env(name: str, default: str) -> str:
    return str(os.getenv(name) or default).strip()


def _int_env(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


APP_HOST = _env("BITRIX_APP_HOST", "127.0.0.1")
APP_PORT = int(_env("BITRIX_APP_PORT", "8787"))
STATE_DIR = Path(_env("BITRIX_APP_STATE_DIR", "/opt/openclaw/state/bitrix_app"))
WAZZUP_FORWARD_URL = _env("WAZZUP_WEBHOOK_FORWARD_URL", "")
BITRIX_TIMEOUT_SEC = _int_env("BITRIX_TIMEOUT_SEC", 10)


def _now_iso() -> str:
    return datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")


def _now_slug() -> str:
    return datetime.now(MOSCOW_TZ).strftime("%Y%m%dT%H%M%S%f")


def _flatten_query(data: dict[str, list[str]]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, values in data.items():
        if not values:
            flattened[key] = ""
        elif len(values) == 1:
            flattened[key] = values[0]
        else:
            flattened[key] = values
    return flattened


def _read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}

    raw = handler.rfile.read(length)
    content_type = str(handler.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if content_type == "application/json":
        try:
            payload = json.loads(raw.decode("utf-8"))
            return payload if isinstance(payload, dict) else {"payload": payload}
        except json.JSONDecodeError:
            return {"raw_body": raw.decode("utf-8", errors="replace")}

    return _flatten_query(parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True))


def _merge_payload(query_data: dict[str, Any], body_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(query_data)
    merged.update(body_data)
    return merged


def _pick(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
        if "[" in key and key.endswith("]"):
            parent, child = key.split("[", 1)
            child = child[:-1]
            nested = payload.get(parent)
            if isinstance(nested, dict):
                value = nested.get(child)
                if value not in (None, ""):
                    return str(value)
    return ""


def _pick_domain(payload: dict[str, Any]) -> str:
    return _pick(payload, "DOMAIN", "domain", "auth[domain]")


def _pick_member_id(payload: dict[str, Any]) -> str:
    return _pick(payload, "member_id", "MEMBER_ID", "auth[member_id]")


def _pick_status(payload: dict[str, Any]) -> str:
    return _pick(payload, "status", "STATUS", "auth[status]")


def _pick_access_token(payload: dict[str, Any]) -> str:
    return _pick(payload, "AUTH_ID", "auth_id", "access_token", "auth[access_token]")


def _pick_refresh_token(payload: dict[str, Any]) -> str:
    return _pick(payload, "REFRESH_ID", "refresh_id", "auth[refresh_token]")


def _pick_payload_event(payload: dict[str, Any]) -> str:
    return _pick(payload, "event", "EVENT")


def _is_wazzup_payload(payload: dict[str, Any]) -> bool:
    if str(payload.get("source") or "").strip().lower() == "wazzup":
        return True
    if payload.get("test") is True:
        return True
    return any(key in payload for key in ("messages", "statuses", "createContact", "createDeal"))


def _wazzup_summary(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages")
    statuses = payload.get("statuses")
    return {
        "wazzup_test": bool(payload.get("test") is True),
        "messages_count": len(messages) if isinstance(messages, list) else 0,
        "statuses_count": len(statuses) if isinstance(statuses, list) else 0,
        "has_create_contact": bool(payload.get("createContact")),
        "has_create_deal": bool(payload.get("createDeal")),
    }


def _forward_wazzup_payload(payload: dict[str, Any]) -> str:
    target = str(WAZZUP_FORWARD_URL or "").strip()
    if not target:
        return "skip"

    request = Request(
        target,
        method="POST",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:  # noqa: S310
        response.read()
    return "ok"


def _string_id(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    return raw


def _int_or(value: Any, default: int) -> int:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _is_yes(value: Any, *, default: bool = False) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "y", "yes", "да"}


def _extract_property(payload: dict[str, Any], name: str) -> str:
    variants = (
        name,
        name.upper(),
        name.lower(),
        f"properties[{name}]",
        f"properties[{name.upper()}]",
        f"properties[{name.lower()}]",
        f"Properties[{name}]",
        f"PROPERTY[{name}]",
    )
    value = _pick(payload, *variants)
    if value:
        return value
    properties = payload.get("properties") or payload.get("Properties") or payload.get("PROPERTY")
    if isinstance(properties, dict):
        for key in (name, name.upper(), name.lower()):
            value = properties.get(key)
            if value not in (None, ""):
                return str(value)
    return ""


def _extract_id_from_document(value: Any, prefix: str) -> str:
    if isinstance(value, list):
        values = [str(item) for item in value]
    else:
        raw = str(value or "")
        values = raw.replace("[", " ").replace("]", " ").replace(",", " ").split()
    marker = f"{prefix}_"
    for item in values:
        if marker in item:
            return _string_id(item.rsplit(marker, 1)[-1].strip("'\""))
    return ""


def _extract_sync_request(payload: dict[str, Any]) -> dict[str, Any]:
    company_id = _string_id(
        _extract_property(payload, "companyId")
        or _extract_property(payload, "company_id")
        or _extract_property(payload, "COMPANY_ID")
        or _extract_id_from_document(
            payload.get("document_id")
            or payload.get("DOCUMENT_ID")
            or payload.get("documentId")
            or payload.get("DocumentId")
            or payload.get("document_id[2]")
            or payload.get("DOCUMENT_ID[2]"),
            "COMPANY",
        )
    )
    deal_id = _string_id(
        _extract_property(payload, "dealId")
        or _extract_property(payload, "deal_id")
        or _extract_property(payload, "DEAL_ID")
    )
    include_closed = _is_yes(
        _extract_property(payload, "syncClosedDeals")
        or _extract_property(payload, "includeClosedDeals"),
        default=True,
    )
    max_deals = _int_or(_extract_property(payload, "maxDeals"), 50)
    if max_deals <= 0:
        max_deals = 50
    return {
        "company_id": company_id,
        "deal_id": deal_id,
        "include_closed": include_closed,
        "max_deals": min(max_deals, 200),
    }


def _load_latest_auth_payload() -> dict[str, Any]:
    for name in ("handler.latest.json", "install.latest.json"):
        path = STATE_DIR / name
        if not path.exists():
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payload = record.get("payload")
        if isinstance(payload, dict):
            return payload
    return {}


def _auth_payload(payload: dict[str, Any]) -> dict[str, Any]:
    merged = _load_latest_auth_payload()
    merged.update(payload)
    return merged


def _client_endpoint(payload: dict[str, Any]) -> str:
    endpoint = _pick(payload, "auth[client_endpoint]", "client_endpoint")
    if endpoint:
        return endpoint.rstrip("/")
    domain = _pick(payload, "auth[domain]", "DOMAIN", "domain")
    if domain and "." in domain:
        return f"https://{domain}/rest"
    return ""


def _access_token(payload: dict[str, Any]) -> str:
    return _pick(payload, "auth[access_token]", "AUTH_ID", "auth_id", "access_token")


def _flatten_rest_params(prefix: str, value: Any) -> list[tuple[str, str]]:
    if isinstance(value, dict):
        pairs: list[tuple[str, str]] = []
        for key, item in value.items():
            pairs.extend(_flatten_rest_params(f"{prefix}[{key}]", item))
        return pairs
    if isinstance(value, (list, tuple)):
        pairs = []
        for item in value:
            pairs.extend(_flatten_rest_params(f"{prefix}[]", item))
        return pairs
    if value is None:
        return [(prefix, "")]
    return [(prefix, str(value))]


def _bitrix_call_payload(auth_payload: dict[str, Any], method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    endpoint = _client_endpoint(auth_payload)
    token = _access_token(auth_payload)
    if not endpoint or not token:
        raise RuntimeError("В payload БП нет Bitrix auth/client_endpoint")

    body_pairs = [("auth", token)]
    for key, value in (params or {}).items():
        body_pairs.extend(_flatten_rest_params(str(key), value))
    request = Request(
        f"{endpoint}/{method}.json",
        method="POST",
        data=urlencode(body_pairs).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(request, timeout=BITRIX_TIMEOUT_SEC) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Bitrix HTTP {error.code}: {raw[:400]}") from None
    except URLError as error:
        raise RuntimeError(f"Bitrix URL error: {error.reason}") from None

    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Bitrix вернул невалидный JSON: {error}") from None
    if not isinstance(payload, dict):
        raise RuntimeError("Bitrix вернул неожиданный формат ответа")
    if payload.get("error"):
        raise RuntimeError(f"Bitrix error {payload.get('error')}: {payload.get('error_description')}")
    return payload


def _bitrix_call(auth_payload: dict[str, Any], method: str, params: dict[str, Any] | None = None, default: Any = None) -> Any:
    payload = _bitrix_call_payload(auth_payload, method, params)
    result = payload.get("result")
    return default if result is None else result


def _normalize_link(item: dict[str, Any], *, default_sort: int) -> dict[str, Any] | None:
    contact_id = _string_id(item.get("CONTACT_ID") or item.get("contactId") or item.get("contact_id"))
    if not contact_id:
        return None
    return {
        "CONTACT_ID": int(contact_id),
        "SORT": _int_or(item.get("SORT") or item.get("sort"), default_sort),
        "ROLE_ID": _int_or(item.get("ROLE_ID") or item.get("roleId") or item.get("role_id"), 0),
        "IS_PRIMARY": "Y" if _is_yes(item.get("IS_PRIMARY") or item.get("isPrimary") or item.get("is_primary")) else "N",
    }


def _normalize_links(items: list[dict[str, Any]], *, default_sort: int = 10) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        link = _normalize_link(item, default_sort=default_sort + (index * 10))
        if not link:
            continue
        contact_id = str(link["CONTACT_ID"])
        if contact_id in seen:
            continue
        seen.add(contact_id)
        links.append(link)
    return links


def _build_sync_plan(
    *,
    deal_id: str,
    company_id: str,
    company_contact_items: list[dict[str, Any]],
    deal_contact_items: list[dict[str, Any]],
) -> dict[str, Any]:
    company_links = _normalize_links(company_contact_items)
    deal_links = _normalize_links(deal_contact_items)
    existing_deal_ids = {str(item["CONTACT_ID"]) for item in deal_links}
    primary_assigned = any(item.get("IS_PRIMARY") == "Y" for item in deal_links)
    max_sort = max([_int_or(item.get("SORT"), 0) for item in deal_links] + [0])
    additions: list[dict[str, Any]] = []
    skipped_existing: list[str] = []

    for company_link in sorted(company_links, key=lambda item: (_int_or(item.get("SORT"), 0), str(item["CONTACT_ID"]))):
        contact_id = str(company_link["CONTACT_ID"])
        if contact_id in existing_deal_ids:
            skipped_existing.append(contact_id)
            continue
        max_sort = max(max_sort + 10, _int_or(company_link.get("SORT"), 0))
        addition = {
            "CONTACT_ID": company_link["CONTACT_ID"],
            "SORT": max_sort,
            "ROLE_ID": company_link["ROLE_ID"],
            "IS_PRIMARY": "N",
        }
        if not primary_assigned:
            addition["IS_PRIMARY"] = "Y"
            primary_assigned = True
        additions.append(addition)
        existing_deal_ids.add(contact_id)

    return {
        "deal_id": str(deal_id),
        "company_id": str(company_id),
        "existing_deal_contact_ids": [str(item["CONTACT_ID"]) for item in deal_links],
        "company_contact_ids": [str(item["CONTACT_ID"]) for item in company_links],
        "skipped_existing_contact_ids": skipped_existing,
        "additions": additions,
        "additions_count": len(additions),
    }


def _list_company_deals(
    auth_payload: dict[str, Any],
    *,
    company_id: str,
    include_closed: bool,
    max_deals: int,
) -> list[dict[str, Any]]:
    deals: list[dict[str, Any]] = []
    start = 0
    while len(deals) < max_deals:
        filters: dict[str, Any] = {"COMPANY_ID": company_id}
        if not include_closed:
            filters["CLOSED"] = "N"
        payload = _bitrix_call_payload(
            auth_payload,
            "crm.deal.list",
            {
                "filter": filters,
                "select": ["ID", "TITLE", "COMPANY_ID", "CLOSED"],
                "order": {"ID": "DESC"},
                "start": start,
            },
        )
        result = payload.get("result")
        if not isinstance(result, list):
            break
        deals.extend(item for item in result if isinstance(item, dict))
        next_start = payload.get("next")
        if next_start is None:
            break
        start = _int_or(next_start, 0)
        if start <= 0:
            break
    return deals[:max_deals]


def _sync_deal_contacts(
    auth_payload: dict[str, Any],
    *,
    deal_id: str,
    expected_company_id: str,
    company_contact_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    deal = _bitrix_call(auth_payload, "crm.deal.get", {"id": deal_id}, default={})
    if not isinstance(deal, dict):
        deal = {}
    company_id = _string_id(deal.get("COMPANY_ID") or expected_company_id)
    if expected_company_id and company_id and str(company_id) != str(expected_company_id):
        return {
            "ok": False,
            "status": "company_mismatch",
            "deal_id": str(deal_id),
            "company_id": company_id,
            "expected_company_id": expected_company_id,
        }

    if not company_id:
        return {"ok": False, "status": "no_company", "deal_id": str(deal_id)}

    if company_contact_items is None:
        company_items = _bitrix_call(auth_payload, "crm.company.contact.items.get", {"id": company_id}, default=[])
    else:
        company_items = company_contact_items
    deal_items = _bitrix_call(auth_payload, "crm.deal.contact.items.get", {"id": deal_id}, default=[])
    if not isinstance(company_items, list):
        company_items = []
    if not isinstance(deal_items, list):
        deal_items = []

    plan = _build_sync_plan(
        deal_id=str(deal_id),
        company_id=company_id,
        company_contact_items=[item for item in company_items if isinstance(item, dict)],
        deal_contact_items=[item for item in deal_items if isinstance(item, dict)],
    )
    applied: list[dict[str, Any]] = []
    for addition in plan["additions"]:
        fields = {
            "CONTACT_ID": addition["CONTACT_ID"],
            "SORT": addition["SORT"],
            "IS_PRIMARY": addition["IS_PRIMARY"],
        }
        result = _bitrix_call(auth_payload, "crm.deal.contact.add", {"id": deal_id, "fields": fields}, default=None)
        applied.append({"fields": fields, "result": result})

    return {
        "ok": True,
        "status": "applied",
        "deal_id": str(deal_id),
        "deal_title": str(deal.get("TITLE") or ""),
        "company_id": company_id,
        "plan": plan,
        "applied": applied,
    }


def _sync_deal_contacts_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    auth = _auth_payload(payload)
    request = _extract_sync_request(payload)
    company_id = request["company_id"]
    deal_id = request["deal_id"]

    if deal_id:
        result = _sync_deal_contacts(auth, deal_id=deal_id, expected_company_id=company_id)
        return {
            "ok": bool(result.get("ok")),
            "event": "sync_deal_contacts",
            "request": request,
            "deals_count": 1,
            "added_contacts_count": int(result.get("plan", {}).get("additions_count", 0)) if isinstance(result.get("plan"), dict) else 0,
            "results": [result],
            "saved_at": _now_iso(),
        }

    if not company_id:
        return {
            "ok": False,
            "event": "sync_deal_contacts",
            "status": "no_company",
            "message": "Не передан companyId и не найден COMPANY_ID в document_id",
            "request": request,
            "saved_at": _now_iso(),
        }

    company_items = _bitrix_call(auth, "crm.company.contact.items.get", {"id": company_id}, default=[])
    if not isinstance(company_items, list):
        company_items = []
    deals = _list_company_deals(
        auth,
        company_id=company_id,
        include_closed=bool(request["include_closed"]),
        max_deals=int(request["max_deals"]),
    )
    results = [
        _sync_deal_contacts(
            auth,
            deal_id=str(deal.get("ID")),
            expected_company_id=company_id,
            company_contact_items=[item for item in company_items if isinstance(item, dict)],
        )
        for deal in deals
        if _string_id(deal.get("ID"))
    ]
    return {
        "ok": all(bool(item.get("ok")) for item in results) if results else True,
        "event": "sync_deal_contacts",
        "request": request,
        "deals_count": len(results),
        "deal_ids": [str(item.get("deal_id")) for item in results],
        "added_contacts_count": sum(
            int(item.get("plan", {}).get("additions_count", 0))
            for item in results
            if isinstance(item.get("plan"), dict)
        ),
        "results": results,
        "saved_at": _now_iso(),
    }


def _slugify_event_name(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    cleaned = "".join(char if char.isalnum() else "_" for char in raw)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


def _mask_secret(value: str | None) -> str:
    raw = str(value or "").strip()
    if len(raw) <= 8:
        return "***" if raw else ""
    return f"{raw[:4]}***{raw[-4:]}"


def _has_payload(payload: dict[str, Any]) -> bool:
    for value in payload.values():
        if isinstance(value, list):
            if any(str(item).strip() for item in value):
                return True
            continue
        if isinstance(value, dict):
            if value:
                return True
            continue
        if str(value or "").strip():
            return True
    return False


def _safe_log(event: str, payload: dict[str, Any]) -> str:
    domain = _pick_domain(payload)
    member_id = _pick_member_id(payload)
    payload_event = _pick_payload_event(payload)
    auth_id = _pick_access_token(payload)
    refresh_id = _pick_refresh_token(payload)
    wazzup_info = ""
    if _is_wazzup_payload(payload):
        summary = _wazzup_summary(payload)
        wazzup_info = (
            f" messages={summary['messages_count']}"
            f" statuses={summary['statuses_count']}"
            f" test={'1' if summary['wazzup_test'] else '0'}"
        )
    return (
        f"[{_now_iso()}] bitrix_app_{event}"
        f" domain={domain or '-'}"
        f" member_id={member_id or '-'}"
        f" payload_event={payload_event or '-'}"
        f" auth={_mask_secret(auth_id) or '-'}"
        f" refresh={_mask_secret(refresh_id) or '-'}"
        f"{wazzup_info}"
    )


def _persist_payload(event: str, payload: dict[str, Any], headers: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "saved_at": _now_iso(),
        "event": event,
        "payload": payload,
        "headers": headers,
        "summary": {
            "domain": _pick_domain(payload),
            "member_id": _pick_member_id(payload),
            "status": _pick_status(payload),
            "payload_event": _pick_payload_event(payload),
            "auth_present": bool(_pick_access_token(payload)),
            "refresh_present": bool(_pick_refresh_token(payload)),
            **_wazzup_summary(payload),
        },
    }
    payload_json = json.dumps(record, ensure_ascii=False, indent=2)

    latest_target = STATE_DIR / f"{event}.latest.json"
    latest_temp = latest_target.with_suffix(".tmp")
    latest_temp.write_text(payload_json, encoding="utf-8")
    os.chmod(latest_temp, 0o600)
    latest_temp.replace(latest_target)

    archive_name = event
    payload_event_slug = _slugify_event_name(_pick_payload_event(payload))
    if payload_event_slug:
        archive_name = f"{archive_name}.{payload_event_slug}"
    archive_target = STATE_DIR / f"{archive_name}.{_now_slug()}.json"
    archive_temp = archive_target.with_suffix(".tmp")
    archive_temp.write_text(payload_json, encoding="utf-8")
    os.chmod(archive_temp, 0o600)
    archive_temp.replace(archive_target)


def _html_page(title: str, body: str) -> bytes:
    markup = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f5f7fb;
      color: #0f172a;
      margin: 0;
      padding: 32px 20px;
    }}
    .card {{
      max-width: 720px;
      margin: 0 auto;
      background: white;
      border-radius: 16px;
      padding: 28px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 28px;
    }}
    p {{
      margin: 0 0 12px;
      line-height: 1.5;
    }}
    code {{
      background: #eef2ff;
      padding: 2px 6px;
      border-radius: 6px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{escape(title)}</h1>
    {body}
  </div>
</body>
</html>
"""
    return markup.encode("utf-8")


class BitrixAppHandler(BaseHTTPRequestHandler):
    server_version = "CloudbotBitrixApp/1.0"

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/healthz":
            self._send_bytes(HTTPStatus.OK, b"ok", content_type="text/plain; charset=utf-8")
            return
        if path not in {"/bitrix/app/install", "/bitrix/app/handler", "/bitrix/app/sync-deal-contacts"}:
            self._send_bytes(HTTPStatus.NOT_FOUND, b"not found", content_type="text/plain; charset=utf-8")
            return

        query_data = _flatten_query(parse_qs(parsed.query, keep_blank_values=True))
        body_data = _read_body(self)
        payload = _merge_payload(query_data, body_data)
        headers = {key: value for key, value in self.headers.items()}
        if path == "/bitrix/app/sync-deal-contacts":
            self._handle_sync_deal_contacts(payload, headers)
            return

        if path.endswith("/install"):
            event = "install"
        elif _is_wazzup_payload(payload):
            event = "wazzup"
        else:
            event = "handler"
        has_payload = _has_payload(payload)

        if has_payload:
            _persist_payload(event, payload, headers)
        log_event = event if has_payload else f"{event}_probe"
        print(_safe_log(log_event, payload), file=sys.stderr, flush=True)

        if event == "wazzup" and has_payload:
            try:
                forward_status = _forward_wazzup_payload(payload)
            except Exception as error:  # noqa: BLE001
                print(
                    f"[{_now_iso()}] bitrix_app_wazzup_forward status=error message={escape(str(error))}",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(
                    f"[{_now_iso()}] bitrix_app_wazzup_forward status={forward_status}",
                    file=sys.stderr,
                    flush=True,
                )

        accept = str(self.headers.get("Accept") or "").lower()
        if "application/json" in accept or self.command == "POST":
            self._send_json(HTTPStatus.OK, {"ok": True, "event": event, "saved_at": _now_iso()})
            return

        body = (
            "<p>Подключение локального приложения Bitrix24 зарегистрировано.</p>"
            "<p>Cloudbot сохранил служебные данные установки. Окно можно закрыть.</p>"
            f"<p><code>{escape(event)}</code></p>"
        )
        self._send_bytes(HTTPStatus.OK, _html_page("Cloudbot Bitrix App", body))

    def _handle_sync_deal_contacts(self, payload: dict[str, Any], headers: dict[str, Any]) -> None:
        event = "sync_deal_contacts"
        if _has_payload(payload):
            _persist_payload(event, payload, headers)
        try:
            result = _sync_deal_contacts_from_payload(payload)
        except Exception as error:  # noqa: BLE001
            result = {
                "ok": False,
                "event": event,
                "status": "error",
                "error": str(error),
                "saved_at": _now_iso(),
            }
        status_label = "ok" if result.get("ok") else "error"
        print(
            f"{_safe_log(event, payload)} status={status_label}"
            f" company_id={result.get('request', {}).get('company_id', '-') if isinstance(result.get('request'), dict) else '-'}"
            f" deals={result.get('deals_count', '-')}"
            f" added={result.get('added_contacts_count', '-')}",
            file=sys.stderr,
            flush=True,
        )
        self._send_json(HTTPStatus.OK, result)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, body, content_type="application/json; charset=utf-8")

    def _send_bytes(self, status: HTTPStatus, body: bytes, *, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((APP_HOST, APP_PORT), BitrixAppHandler)
    print(
        f"[{_now_iso()}] bitrix_app_server_start host={APP_HOST} port={APP_PORT} state_dir={STATE_DIR}",
        file=sys.stderr,
        flush=True,
    )
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
