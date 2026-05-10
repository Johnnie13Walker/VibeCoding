#!/usr/bin/env python3
"""Bootstrap helper для Bitrix OAuth install payload.

Модуль принимает install POST от Bitrix или ручной stdin payload и пишет
isolated `install.latest.json`. CRM и Google Sheets здесь не вызываются.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

from belberry.bitrix24.providers.bitrix_oauth import _payload_has_auth, _pick
from belberry.bitrix24.providers.logging import mask_secret

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
INSTALL_STATE_NAME = "install.latest.json"
SUCCESS_HTML = "Установка завершена. Можно закрыть это окно."


class OAuthInstallError(RuntimeError):
    """Безопасная ошибка OAuth install bootstrap без секретов."""


@dataclass(frozen=True)
class InstallPayload:
    raw: Mapping[str, Any]

    @classmethod
    def from_form_body(cls, body: bytes) -> "InstallPayload":
        parsed = dict(parse_qsl(body.decode("utf-8", errors="replace"), keep_blank_values=True))
        return cls(raw=parsed)

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "InstallPayload":
        nested = payload.get("payload")
        if isinstance(nested, Mapping):
            return cls(raw=dict(nested))
        return cls(raw=dict(payload))

    def to_state_record(self, *, now_msk: datetime) -> dict[str, Any]:
        payload = {
            "auth[access_token]": _pick(self.raw, "AUTH_ID", "auth_id", "access_token", "auth[access_token]"),
            "auth[refresh_token]": _pick(self.raw, "REFRESH_ID", "refresh_id", "refresh_token", "auth[refresh_token]"),
            "auth[client_endpoint]": _pick(
                self.raw,
                "client_endpoint",
                "CLIENT_ENDPOINT",
                "auth[client_endpoint]",
            ),
            "auth[server_endpoint]": _pick(
                self.raw,
                "server_endpoint",
                "SERVER_ENDPOINT",
                "auth[server_endpoint]",
            ),
            "auth[domain]": _pick(self.raw, "DOMAIN", "domain", "auth[domain]"),
            "auth[member_id]": _pick(self.raw, "member_id", "MEMBER_ID", "auth[member_id]"),
            "auth[status]": _pick(self.raw, "status", "STATUS", "auth[status]"),
        }
        return {
            "saved_at": _as_msk(now_msk).isoformat(timespec="seconds"),
            "summary": {
                "domain": payload["auth[domain]"],
                "member_id": payload["auth[member_id]"],
                "auth_present": bool(payload["auth[access_token]"]),
                "refresh_present": bool(payload["auth[refresh_token]"]),
            },
            "payload": payload,
        }

    def is_valid(self) -> bool:
        return _payload_has_auth(self.raw)


def _as_msk(value: datetime) -> datetime:
    return value.replace(tzinfo=MOSCOW_TZ) if value.tzinfo is None else value.astimezone(MOSCOW_TZ)


def _now_msk() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _default_state_dir() -> Path:
    raw = os.environ.get("BELBERRY_BITRIX24_APP_STATE_DIR", "").strip()
    if not raw:
        raise OAuthInstallError("BELBERRY_BITRIX24_APP_STATE_DIR не задан")
    return Path(raw)


def _validate_server_args(*, host: str, port: int) -> None:
    if host != "127.0.0.1":
        raise OAuthInstallError("host must be 127.0.0.1")
    if int(port) < 1024:
        raise OAuthInstallError("port must be >= 1024")
    if int(port) > 65535:
        raise OAuthInstallError("port must be <= 65535")


def write_install_state(
    *,
    state_dir: Path,
    payload: InstallPayload,
    now_msk: datetime,
) -> Path:
    if not payload.is_valid():
        raise OAuthInstallError("Invalid payload")

    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / INSTALL_STATE_NAME
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    record = payload.to_state_record(now_msk=now_msk)
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def serve_install_handler(
    *,
    port: int,
    state_dir: Path,
    now_msk_factory: Callable[[], datetime],
    host: str = "127.0.0.1",
    timeout_sec: int = 600,
) -> Path:
    _validate_server_args(host=host, port=port)
    saved_path: Path | None = None

    class InstallHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802
            self._send_text(404, "Not found")

        def do_POST(self) -> None:  # noqa: N802
            nonlocal saved_path
            if self.path != "/install":
                self._send_text(404, "Not found")
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length)
            payload = InstallPayload.from_form_body(body)
            try:
                saved_path = write_install_state(
                    state_dir=state_dir,
                    payload=payload,
                    now_msk=now_msk_factory(),
                )
            except OAuthInstallError:
                self._send_text(400, "Invalid payload")
                return
            self._send_text(200, SUCCESS_HTML, content_type="text/html; charset=utf-8")

        def _send_text(self, status: int, text: str, *, content_type: str = "text/plain; charset=utf-8") -> None:
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    deadline = time.monotonic() + int(timeout_sec)
    with HTTPServer((host, int(port)), InstallHandler) as server:
        server.timeout = 0.2
        while saved_path is None:
            if time.monotonic() >= deadline:
                raise OAuthInstallError("install payload timeout")
            server.handle_request()
    return saved_path


def import_install_state_from_stdin(
    *,
    state_dir: Path,
    now_msk_factory: Callable[[], datetime],
    stdin_text: str,
) -> Path:
    text = str(stdin_text or "").strip()
    if text.startswith("{"):
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as error:
            raise OAuthInstallError(f"Invalid JSON: {error}") from None
        payload = InstallPayload.from_json(raw)
    else:
        payload = InstallPayload.from_form_body(text.encode("utf-8"))
    return write_install_state(state_dir=state_dir, payload=payload, now_msk=now_msk_factory())


def _summary_for_stdout(path: Path) -> dict[str, str]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OAuthInstallError(f"Saved state unreadable: {error}") from None
    payload = record.get("payload") if isinstance(record, Mapping) else {}
    if not isinstance(payload, Mapping):
        raise OAuthInstallError("Saved state invalid")
    return {
        "domain": _pick(payload, "auth[domain]", "DOMAIN", "domain"),
        "member_id": _pick(payload, "auth[member_id]", "member_id", "MEMBER_ID"),
        "access_token": mask_secret(_pick(payload, "auth[access_token]", "AUTH_ID", "access_token")),
        "refresh_token": mask_secret(_pick(payload, "auth[refresh_token]", "REFRESH_ID", "refresh_token")),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve")
    serve.add_argument("--port", type=int, required=True)
    serve.add_argument("--state-dir", type=Path, default=None)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--timeout-sec", type=int, default=600)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--state-dir", type=Path, default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_dir = args.state_dir if args.state_dir is not None else _default_state_dir()
    if args.command == "serve":
        path = serve_install_handler(
            port=args.port,
            state_dir=state_dir,
            now_msk_factory=_now_msk,
            host=args.host,
            timeout_sec=args.timeout_sec,
        )
    else:
        path = import_install_state_from_stdin(
            state_dir=state_dir,
            now_msk_factory=_now_msk,
            stdin_text=sys.stdin.read(),
        )
    print(json.dumps(_summary_for_stdout(path), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
