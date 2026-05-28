"""Легковесное file-based состояние поисковых уточнений Ларисы."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from zoneinfo import ZoneInfo

MSK_TZ = ZoneInfo("Europe/Moscow")
DEFAULT_STATE_TTL_MINUTES = 30


def _state_path() -> Path:
    configured = str(os.getenv("CLOUDBOT_SEARCH_STATE_PATH") or "").strip()
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "cloudbot_larisa_search_state.json"


def _chat_key(chat_id: str | None, user_id: str | None) -> str:
    return f"{str(chat_id or '').strip()}::{str(user_id or '').strip()}"


def _load_all() -> dict[str, dict[str, Any]]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_all(payload: dict[str, dict[str, Any]]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _is_fresh(entry: dict[str, Any], *, now: datetime | None = None) -> bool:
    raw_updated_at = str(entry.get("updated_at") or "").strip()
    if not raw_updated_at:
        return False
    current = now or datetime.now(MSK_TZ)
    try:
        updated_at = datetime.fromisoformat(raw_updated_at)
    except ValueError:
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=MSK_TZ)
    ttl_minutes = int(entry.get("ttl_minutes") or DEFAULT_STATE_TTL_MINUTES)
    return updated_at >= current - timedelta(minutes=ttl_minutes)


def load_search_state(chat_id: str | None, user_id: str | None) -> dict[str, Any] | None:
    key = _chat_key(chat_id, user_id)
    if not key.strip(":"):
        return None
    payload = _load_all()
    entry = payload.get(key)
    if not isinstance(entry, dict):
        return None
    if not _is_fresh(entry):
        payload.pop(key, None)
        _save_all(payload)
        return None
    return entry


def save_search_state(chat_id: str | None, user_id: str | None, state: dict[str, Any]) -> None:
    key = _chat_key(chat_id, user_id)
    if not key.strip(":"):
        return
    payload = _load_all()
    current = datetime.now(MSK_TZ).isoformat()
    payload[key] = {
        **state,
        "updated_at": current,
        "ttl_minutes": int(state.get("ttl_minutes") or DEFAULT_STATE_TTL_MINUTES),
    }
    _save_all(payload)


def clear_search_state(chat_id: str | None, user_id: str | None) -> None:
    key = _chat_key(chat_id, user_id)
    if not key.strip(":"):
        return
    payload = _load_all()
    if key in payload:
        payload.pop(key, None)
        _save_all(payload)
