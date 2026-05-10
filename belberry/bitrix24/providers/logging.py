"""Structured JSONL logger с маскированием секретов.

Контракт:
- каждая запись — одна строка JSON в МСК timezone;
- секреты (access_token, refresh_token, webhook URL, service account private_key)
  маскируются автоматически;
- логгер не бросает исключений на уровне записи (best-effort на write),
  но конструирование payload может падать на инвалидном вводе.

Маскирование портировано из legacy `cloudbot/providers/bitrix/bitrix_app_auth.py`
и адаптировано без зависимости от BitrixAPIError.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

SECRET_KEY_HINTS = (
    "access_token",
    "refresh_token",
    "auth_id",
    "refresh_id",
    "private_key",
    "client_secret",
    "auth[access_token]",
    "auth[refresh_token]",
    "AUTH_ID",
    "REFRESH_ID",
    "authorization",
    "api_key",
    "token",
)

URL_PATTERN = re.compile(r"https?://[^\s]+")


def now_msk() -> str:
    return datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")


def mask_secret(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return "***"
    return f"{raw[:4]}***{raw[-4:]}"


def mask_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return "***"
    return f"{parsed.scheme}://{parsed.netloc}/***"


def sanitize_bitrix_text(
    text: Any,
    *,
    webhook_url: Any = None,
    endpoint: Any = None,
) -> str:
    """Маскирует Bitrix endpoint/URL в человекочитаемых ошибках."""
    safe = str(text or "").strip()
    if not safe:
        return "unknown error"

    for candidate in (str(webhook_url or "").strip(), str(endpoint or "").strip()):
        if candidate:
            safe = safe.replace(candidate, mask_url(candidate))

    return URL_PATTERN.sub(lambda match: mask_url(match.group(0)), safe)


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(hint.lower() in lowered for hint in SECRET_KEY_HINTS)


def sanitize(payload: Any) -> Any:
    """Рекурсивно маскирует секреты и URL во вложенных структурах."""
    if isinstance(payload, Mapping):
        result: dict[str, Any] = {}
        for key, value in payload.items():
            key_str = str(key)
            if _is_secret_key(key_str):
                result[key_str] = mask_secret(value)
            else:
                result[key_str] = sanitize(value)
        return result
    if isinstance(payload, (list, tuple)):
        return [sanitize(item) for item in payload]
    if isinstance(payload, str):
        return URL_PATTERN.sub(lambda match: mask_url(match.group(0)), payload)
    return payload


@dataclass
class JsonlLogger:
    path: Path
    component: str
    run_id: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _emit(self, level: str, event: str, fields: Mapping[str, Any] | None = None) -> dict[str, Any]:
        record: dict[str, Any] = {
            "ts_msk": now_msk(),
            "level": level,
            "component": self.component,
            "event": event,
        }
        if self.run_id:
            record["run_id"] = self.run_id
        if self.extra:
            record.update(sanitize(self.extra))
        if fields:
            record.update(sanitize(fields))
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError as error:
            sys.stderr.write(f"jsonl_logger_write_failed: {error}\n")
        return record

    def info(self, event: str, **fields: Any) -> dict[str, Any]:
        return self._emit("info", event, fields)

    def warn(self, event: str, **fields: Any) -> dict[str, Any]:
        return self._emit("warn", event, fields)

    def error(self, event: str, **fields: Any) -> dict[str, Any]:
        return self._emit("error", event, fields)


def default_log_path(*, run_id: str = "", base_dir: Path | None = None) -> Path:
    base = Path(base_dir) if base_dir else Path("belberry/bitrix24/logs")
    if run_id:
        return base / f"{run_id}.jsonl"
    today = datetime.now(MOSCOW_TZ).strftime("%Y%m%d")
    return base / f"daily-{today}.jsonl"


def get_logger(
    *,
    component: str,
    run_id: str = "",
    path: Path | None = None,
    extra: Mapping[str, Any] | None = None,
) -> JsonlLogger:
    target = Path(path) if path else default_log_path(run_id=run_id)
    if os.environ.get("BELBERRY_BITRIX24_LOG_DIR"):
        target = Path(os.environ["BELBERRY_BITRIX24_LOG_DIR"]) / target.name
    return JsonlLogger(path=target, component=component, run_id=run_id, extra=dict(extra or {}))
