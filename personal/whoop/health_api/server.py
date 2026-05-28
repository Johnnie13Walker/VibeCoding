#!/usr/bin/env python3
"""Минимальный HTTP endpoint для приёма Apple Health-данных от iOS Shortcuts.

Принимает POST /health/steps с JSON {"date": "YYYY-MM-DD", "steps": N}
и Authorization: Bearer <token>. Пишет в HEALTH_STATE_FILE.

Запуск:
  HEALTH_API_TOKEN=<token> HEALTH_STATE_FILE=/etc/openclaw/health-state.json \\
  HEALTH_API_PORT=8765 python3 server.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Lock

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_BODY = 4096
MAX_STEPS = 200_000

STATE_LOCK = Lock()


def state_path() -> Path:
    return Path(os.environ.get("HEALTH_STATE_FILE", "/etc/openclaw/health-state.json"))


def expected_token() -> str:
    token = os.environ.get("HEALTH_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("HEALTH_API_TOKEN env var is required")
    return token


def load_state() -> dict:
    path = state_path()
    if not path.exists():
        return {"steps": {}}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {"steps": {}}
    if not isinstance(data, dict):
        return {"steps": {}}
    data.setdefault("steps", {})
    return data


def save_state(data: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class HealthHandler(BaseHTTPRequestHandler):
    server_version = "CloudbotHealth/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"[health-api] {self.address_string()} - {fmt % args}\n")

    def _send_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _check_auth(self) -> bool:
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return False
        return header[len(prefix):].strip() == self._expected_token

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/health/steps":
            self._send_json(404, {"error": "not found"})
            return
        if not self._check_auth():
            self._send_json(401, {"error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > MAX_BODY:
            self._send_json(400, {"error": "bad body size"})
            return
        try:
            raw = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "invalid json"})
            return

        date_value = body.get("date") if isinstance(body, dict) else None
        steps_value = body.get("steps") if isinstance(body, dict) else None
        if not isinstance(date_value, str) or not DATE_RE.match(date_value):
            self._send_json(400, {"error": "date must be YYYY-MM-DD"})
            return
        try:
            dt.date.fromisoformat(date_value)
        except ValueError:
            self._send_json(400, {"error": "invalid date"})
            return
        if not isinstance(steps_value, int) or steps_value < 0 or steps_value > MAX_STEPS:
            self._send_json(400, {"error": f"steps must be int 0..{MAX_STEPS}"})
            return

        with STATE_LOCK:
            data = load_state()
            data["steps"][date_value] = steps_value
            data["updated_at"] = dt.datetime.now().astimezone().isoformat()
            save_state(data)

        self._send_json(200, {"ok": True, "date": date_value, "steps": steps_value})


def main() -> int:
    token = expected_token()
    port = int(os.environ.get("HEALTH_API_PORT", "8765"))
    HealthHandler._expected_token = token  # type: ignore[attr-defined]
    server = HTTPServer(("127.0.0.1", port), HealthHandler)
    sys.stderr.write(f"[health-api] listening on 127.0.0.1:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
