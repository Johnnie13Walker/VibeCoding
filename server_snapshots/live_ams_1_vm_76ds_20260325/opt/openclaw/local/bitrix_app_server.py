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
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def _env(name: str, default: str) -> str:
    return str(os.getenv(name) or default).strip()


APP_HOST = _env("BITRIX_APP_HOST", "127.0.0.1")
APP_PORT = int(_env("BITRIX_APP_PORT", "8787"))
STATE_DIR = Path(_env("BITRIX_APP_STATE_DIR", "/opt/openclaw/state/bitrix_app"))
WAZZUP_FORWARD_URL = _env("WAZZUP_WEBHOOK_FORWARD_URL", "")


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
        if path not in {"/bitrix/app/install", "/bitrix/app/handler"}:
            self._send_bytes(HTTPStatus.NOT_FOUND, b"not found", content_type="text/plain; charset=utf-8")
            return

        query_data = _flatten_query(parse_qs(parsed.query, keep_blank_values=True))
        body_data = _read_body(self)
        payload = _merge_payload(query_data, body_data)
        headers = {key: value for key, value in self.headers.items()}
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
