"""Entrypoint часового прохода Wazzup-чатов «Сегодня» → live_chats.
Тяжёлый per-deal скан, отдельный lock от light-live и daily."""

import argparse
from datetime import date

from src import bx_client
from src.config import load_config
from src.db import connect
from src.lock import AlreadyRunning, single_instance
from src.live_wazzup import collect_chat_payload
from src.timeutil import now_msk
from src.writer import write_live_chats

LOCK = "/tmp/scc-live-wazzup.lock"


def run_live_wazzup(today: date | None = None, *, bx=None, connect_fn=connect, now_fn=now_msk) -> dict:
    load_config(["DATABASE_URL"])
    now = now_fn()
    target = today or now.date()
    conn = connect_fn()
    try:
        bx_client.ensure_token_fresh()
        payload = collect_chat_payload(target, bx=bx, now=now)
        write_live_chats(conn, payload, target.isoformat(), now)
        conn.commit()
        return {"status": "done", "report_date": target.isoformat(), "total": payload["total"], "scanned": payload["scanned_deals"]}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    args = parser.parse_args()
    target = date.fromisoformat(args.date) if args.date else None
    try:
        with single_instance(LOCK):
            print(run_live_wazzup(target))
    except AlreadyRunning:
        print("live_wazzup уже выполняется, пропуск")


if __name__ == "__main__":
    main()
