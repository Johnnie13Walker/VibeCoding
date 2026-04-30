"""Live Wazzup provider для Sales Copilot."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cloudbot.business_day import MOSCOW_TZ, previous_business_day

WAZZUP_FILE_RE = re.compile(r"^wazzup\.\d{8}T\d{6,}\d*\.json$")
DEFAULT_WAZZUP_API_BASE_URL = "https://api.wazzup24.com"
DEFAULT_TIMEOUT_SEC = 20


def _env_dict(env: Mapping[str, Any] | None = None) -> dict[str, str]:
    if env is None:
        return {str(key): str(value) for key, value in os.environ.items()}
    return {str(key): str(value) for key, value in env.items()}


def _parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOSCOW_TZ)
    return parsed.astimezone(MOSCOW_TZ)


def _safe_count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class WazzupArchiveMessage:
    message_id: str
    date_time: datetime
    channel_id: str
    chat_type: str
    chat_id: str
    message_type: str
    is_echo: bool
    author_id: str | None
    author_name: str
    status: str
    contact_name: str
    contact_phone: str
    raw: dict[str, Any]

    @property
    def chat_key(self) -> tuple[str, str, str]:
        return (self.channel_id, self.chat_type, self.chat_id)


@dataclass(frozen=True)
class WazzupArchiveStatus:
    ok: bool
    status: str
    message: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "message": self.message,
        }


@dataclass
class WazzupProvider:
    api_key: str = ""
    base_url: str = DEFAULT_WAZZUP_API_BASE_URL
    state_dir: Path = Path("/opt/openclaw/state/bitrix_app")
    timeout_sec: int = DEFAULT_TIMEOUT_SEC

    @classmethod
    def from_env(cls, env: Mapping[str, Any] | None = None) -> "WazzupProvider":
        env_data = _env_dict(env)
        state_dir_raw = str(env_data.get("BITRIX_APP_STATE_DIR") or "/opt/openclaw/state/bitrix_app").strip()
        return cls(
            api_key=str(env_data.get("WAZZUP_API_KEY") or "").strip(),
            base_url=str(env_data.get("WAZZUP_API_BASE_URL") or DEFAULT_WAZZUP_API_BASE_URL).strip(),
            state_dir=Path(state_dir_raw).expanduser(),
            timeout_sec=_safe_count(env_data.get("WAZZUP_TIMEOUT_SEC")) or DEFAULT_TIMEOUT_SEC,
        )

    def _configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _archive_files(self) -> list[Path]:
        if not self.state_dir.exists():
            return []
        return sorted(
            [
                path
                for path in self.state_dir.iterdir()
                if path.is_file() and WAZZUP_FILE_RE.match(path.name)
            ],
            key=lambda path: path.name,
        )

    def _load_archive_payload(self, path: Path) -> dict[str, Any] | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return raw if isinstance(raw, dict) else None

    def list_archive_messages(
        self,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> list[WazzupArchiveMessage]:
        messages_by_id: dict[str, WazzupArchiveMessage] = {}
        fallback_idx = 0
        for path in self._archive_files():
            payload = self._load_archive_payload(path)
            if payload is None:
                continue
            for raw_message in ((payload.get("payload") or {}).get("messages") or []):
                if not isinstance(raw_message, dict):
                    continue
                at = _parse_dt(raw_message.get("dateTime"))
                if at is None:
                    continue
                if period_start is not None and at < period_start:
                    continue
                if period_end is not None and at >= period_end:
                    continue
                message_id = str(raw_message.get("messageId") or "").strip()
                if not message_id:
                    fallback_idx += 1
                    message_id = f"{path.name}:{fallback_idx}"
                item = WazzupArchiveMessage(
                    message_id=message_id,
                    date_time=at,
                    channel_id=str(raw_message.get("channelId") or "").strip(),
                    chat_type=str(raw_message.get("chatType") or "").strip().lower(),
                    chat_id=str(raw_message.get("chatId") or "").strip(),
                    message_type=str(raw_message.get("type") or "").strip().lower(),
                    is_echo=bool(raw_message.get("isEcho")),
                    author_id=str(raw_message.get("authorId") or "").strip() or None,
                    author_name=str(raw_message.get("authorName") or "").strip(),
                    status=str(raw_message.get("status") or "").strip().lower(),
                    contact_name=str(((raw_message.get("contact") or {}).get("name")) or "").strip(),
                    contact_phone=str(((raw_message.get("contact") or {}).get("phone")) or "").strip(),
                    raw=raw_message,
                )
                current = messages_by_id.get(message_id)
                if current is None or item.date_time >= current.date_time:
                    messages_by_id[message_id] = item
        return sorted(messages_by_id.values(), key=lambda item: item.date_time)

    def _latest_archive_dt(self) -> datetime | None:
        latest: datetime | None = None
        for path in self._archive_files():
            payload = self._load_archive_payload(path)
            if payload is None:
                continue
            for candidate in (
                _parse_dt(payload.get("saved_at")),
                *[
                    _parse_dt(item.get("dateTime"))
                    for item in ((payload.get("payload") or {}).get("messages") or [])
                    if isinstance(item, dict)
                ],
                *[
                    _parse_dt(item.get("timestamp"))
                    for item in ((payload.get("payload") or {}).get("statuses") or [])
                    if isinstance(item, dict)
                ],
            ):
                if candidate is not None and (latest is None or candidate > latest):
                    latest = candidate
        return latest

    def get_history_source_status(self) -> dict[str, Any]:
        files = self._archive_files()
        if not files:
            return WazzupArchiveStatus(
                ok=False,
                status="not_configured",
                message="webhook archive Wazzup не найден в BITRIX_APP_STATE_DIR",
            ).to_payload()

        latest = self._latest_archive_dt()
        latest_label = latest.strftime("%d.%m %H:%M") if isinstance(latest, datetime) else "-"
        return WazzupArchiveStatus(
            ok=True,
            status="ok",
            message=f"История диалогов считается из webhook archive; payloads={len(files)}; latest={latest_label}",
        ).to_payload()

    def get_archive_status(self) -> dict[str, Any]:
        files = self._archive_files()
        if not files:
            return WazzupArchiveStatus(
                ok=False,
                status="not_configured",
                message="webhook archive Wazzup не найден в state",
            ).to_payload()

        now = datetime.now(MOSCOW_TZ)
        report_day = previous_business_day(now.date())
        period_start = datetime.combine(report_day, time.min, tzinfo=MOSCOW_TZ)
        period_end = period_start + timedelta(days=1)
        messages = [
            item
            for item in self.list_archive_messages(period_start=period_start, period_end=period_end)
            if item.chat_type != "telegroup"
        ]
        dialogs = len({item.chat_key for item in messages if all(item.chat_key)})
        latest = self._latest_archive_dt()
        latest_label = latest.strftime("%d.%m %H:%M") if isinstance(latest, datetime) else "-"
        return WazzupArchiveStatus(
            ok=True,
            status="ok",
            message=(
                f"OK ({len(files)} payloads; предыдущий рабочий день dialogs={dialogs}, "
                f"messages={len(messages)}; latest={latest_label})"
            ),
        ).to_payload()

    def get_api_status(self) -> dict[str, Any]:
        if not self._configured():
            return {
                "ok": False,
                "status": "not_configured",
                "message": "не настроен",
            }

        endpoint = f"{self.base_url.rstrip('/')}/v3/channels"
        request = Request(
            endpoint,
            method="GET",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:  # noqa: S310
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as error:
            return {
                "ok": False,
                "status": "error",
                "message": f"HTTP {error.code}",
            }
        except URLError as error:
            return {
                "ok": False,
                "status": "error",
                "message": str(error.reason or error),
            }
        except Exception as error:  # noqa: BLE001
            return {
                "ok": False,
                "status": "error",
                "message": str(error),
            }

        try:
            payload = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return {
                "ok": False,
                "status": "error",
                "message": "Wazzup API вернул невалидный JSON",
            }

        size = len(payload) if isinstance(payload, list) else 1
        return {
            "ok": True,
            "status": "ok",
            "message": f"OK ({size})",
        }
