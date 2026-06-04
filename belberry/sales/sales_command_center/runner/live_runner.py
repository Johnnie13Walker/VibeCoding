"""Entrypoint «Сегодня» (live): лёгкий частый сбор текущего дня → live_snapshot.
Отдельный lock (/tmp/scc-live.lock), не пересекается с daily_runner."""

import argparse
from datetime import date

from src import bx_client
from src.config import load_config
from src.db import connect
from src.lock import AlreadyRunning, single_instance
from src.live import build_live_payload, collect_live
from src.timeutil import now_msk
from src.writer import write_live

LIVE_LOCK = "/tmp/scc-live.lock"


def run_live(today: date | None = None, *, bx=None, connect_fn=connect, now_fn=now_msk) -> dict:
    load_config(["DATABASE_URL"])
    now = now_fn()
    target = today or now.date()
    conn = connect_fn()
    try:
        bx_client.ensure_token_fresh()
        raw = collect_live(target, bx=bx)
        payload = build_live_payload(target, raw, now)
        write_live(conn, payload, target.isoformat(), now)
        conn.commit()
        return {"status": "done", "report_date": target.isoformat(), "totals": payload["totals"]}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Дата YYYY-MM-DD (по умолчанию — сегодня МСК)")
    args = parser.parse_args()
    target = date.fromisoformat(args.date) if args.date else None
    try:
        with single_instance(LIVE_LOCK):
            print(run_live(target))
    except AlreadyRunning:
        print("live_runner уже выполняется, пропуск")


if __name__ == "__main__":
    main()
