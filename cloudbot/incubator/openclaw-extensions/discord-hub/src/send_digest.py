import sys
from datetime import datetime, timezone

from common import (
    Config,
    api_get_json,
    edit_discord_webhook_message,
    ensure_db,
    get_sync,
    payload_hash,
    post_discord_webhook,
    upsert_sync,
)


def build_digest_text(data: dict) -> str:
    title = data.get("title") or Config.digest_title
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"**{title}** ({date} UTC)"]

    metrics = data.get("metrics", [])
    if isinstance(metrics, list):
        for item in metrics[: Config.digest_max_items]:
            name = item.get("name", "metric")
            value = item.get("value", "n/a")
            trend = item.get("trend", "")
            trend_part = f" ({trend})" if trend else ""
            lines.append(f"- {name}: {value}{trend_part}")

    notes = data.get("notes")
    if notes:
        lines.append("")
        lines.append(f"_Комментарий:_ {notes}")

    source_url = data.get("source_url")
    if source_url:
        lines.append(f"Источник: {source_url}")

    return "\n".join(lines)


def run() -> int:
    conn = ensure_db(Config.sync_db_path)

    digest_data = api_get_json("/kpi/digest")
    record_id = str(digest_data.get("id") or f"daily-digest-{datetime.now(timezone.utc).date()}")
    channel_id = Config.discord_default_channel_id or "default"
    content = build_digest_text(digest_data)
    current_hash = payload_hash({"content": content})

    existing = get_sync(conn, record_id, channel_id)
    if existing is not None:
        existing_message_id, existing_hash = existing
        if existing_hash == current_hash:
            print("Digest is unchanged; skipping post.")
            return 0

        if existing_message_id:
            message_id = edit_discord_webhook_message(existing_message_id, content)
            upsert_sync(conn, record_id, channel_id, message_id, current_hash)
            print(f"Digest updated, message_id={message_id}")
            return 0

    message_id = post_discord_webhook(content)
    upsert_sync(conn, record_id, channel_id, message_id, current_hash)
    print(f"Digest posted, message_id={message_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"send_digest failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
