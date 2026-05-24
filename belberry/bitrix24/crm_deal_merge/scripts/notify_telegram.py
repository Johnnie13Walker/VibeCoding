#!/usr/bin/env python3
"""Telegram digest для weekly refresh таба «Пустые компании»."""
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SHEET_ID = "13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4"


def build_message(summary: dict[str, Any], *, sheet_id: str = SHEET_ID) -> str:
    total = int(summary.get("trash_companies") or 0)
    new_count = int(summary.get("new_vs_previous") or 0)
    gone_count = int(summary.get("gone_vs_previous") or 0)
    previous = summary.get("previous_snapshot_rows")
    updated_at = summary.get("updated_at_msk") or "n/a"
    return "\n".join(
        [
            "Пустые компании: снапшот обновлён",
            f"Пустых: {total}",
            f"Новых: +{new_count}",
            f"Обогащено/удалено: -{gone_count}",
            f"Было: {previous if previous is not None else 'n/a'}",
            f"Обновлено: {updated_at} МСК",
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
        ]
    )


def send_telegram(message: str) -> None:
    token = os.environ.get("LARISA_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("LARISA_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("LARISA_TELEGRAM_BOT_TOKEN/LARISA_TELEGRAM_CHAT_ID не заданы")
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
        response.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True, help="JSON summary от empty-companies-refresh")
    parser.add_argument("--sheet-id", default=SHEET_ID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    message = build_message(summary, sheet_id=args.sheet_id)
    if args.dry_run:
        print(message)
        return 0
    send_telegram(message)
    print("telegram notify: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
