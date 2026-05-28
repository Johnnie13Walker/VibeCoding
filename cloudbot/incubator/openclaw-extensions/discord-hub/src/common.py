import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()


class Config:
    source_api_base_url = os.getenv("SOURCE_API_BASE_URL", "").rstrip("/")
    source_api_token = os.getenv("SOURCE_API_TOKEN", "")
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    discord_bot_token = os.getenv("DISCORD_COMMAND_BOT_TOKEN", "")
    discord_public_key = os.getenv("DISCORD_PUBLIC_KEY", "")
    discord_application_id = os.getenv("DISCORD_APPLICATION_ID", "")
    discord_default_channel_id = os.getenv("DISCORD_DEFAULT_CHANNEL_ID", "")
    sync_db_path = os.getenv("SYNC_DB_PATH", "./discord-hub/data/sync.db")
    digest_title = os.getenv("DIGEST_TITLE", "Ежедневный KPI-дайджест")
    digest_max_items = int(os.getenv("DIGEST_MAX_ITEMS", "10"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def ensure_db(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_registry (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          external_record_id TEXT NOT NULL,
          discord_channel_id TEXT NOT NULL,
          discord_message_id TEXT,
          payload_hash TEXT NOT NULL,
          last_synced_at TEXT NOT NULL,
          UNIQUE(external_record_id, discord_channel_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_registry_last_synced_at
        ON sync_registry(last_synced_at)
        """
    )
    conn.commit()
    return conn


def api_get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not Config.source_api_base_url:
        raise RuntimeError("SOURCE_API_BASE_URL is not configured")

    headers = {}
    if Config.source_api_token:
        headers["Authorization"] = f"Bearer {Config.source_api_token}"

    url = f"{Config.source_api_base_url}{path}"
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("API response must be a JSON object")
    return data


def post_discord_webhook(content: str) -> str:
    if not Config.discord_webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not configured")
    response = requests.post(
        f"{Config.discord_webhook_url}?wait=true",
        json={"content": content},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return str(data.get("id", ""))


def edit_discord_webhook_message(message_id: str, content: str) -> str:
    if not Config.discord_webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not configured")
    if not message_id:
        raise RuntimeError("message_id is required")
    response = requests.patch(
        f"{Config.discord_webhook_url}/messages/{message_id}",
        json={"content": content},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return str(data.get("id", message_id))


def upsert_sync(
    conn: sqlite3.Connection,
    external_record_id: str,
    discord_channel_id: str,
    discord_message_id: str | None,
    hash_value: str,
) -> None:
    conn.execute(
        """
        INSERT INTO sync_registry (
            external_record_id,
            discord_channel_id,
            discord_message_id,
            payload_hash,
            last_synced_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(external_record_id, discord_channel_id)
        DO UPDATE SET
            discord_message_id = excluded.discord_message_id,
            payload_hash = excluded.payload_hash,
            last_synced_at = excluded.last_synced_at
        """,
        (
            external_record_id,
            discord_channel_id,
            discord_message_id,
            hash_value,
            utc_now_iso(),
        ),
    )
    conn.commit()


def get_sync(
    conn: sqlite3.Connection,
    external_record_id: str,
    discord_channel_id: str,
) -> tuple[str | None, str | None] | None:
    row = conn.execute(
        """
        SELECT discord_message_id, payload_hash
        FROM sync_registry
        WHERE external_record_id = ? AND discord_channel_id = ?
        """,
        (external_record_id, discord_channel_id),
    ).fetchone()
    if row is None:
        return None
    return row[0], row[1]
