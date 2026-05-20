"""Алёрты Sales KPI Dashboard: sync_log freshness и Telegram при сбоях."""
from __future__ import annotations

import os
import urllib.parse
import urllib.request
from datetime import datetime

from sales_dashboard.sheets_client import SheetsClient

from .config import GOOGLE_SA_KEY, MOSCOW_TZ, OUTPUT_SHEET_ID

SYNC_LOG_HEADER = ["ts", "status", "phase", "duration_ms", "rows_written", "error"]


def read_last_sync_rows(n: int = 5) -> list[list[str]]:
    sheets = SheetsClient(OUTPUT_SHEET_ID, GOOGLE_SA_KEY)
    response = sheets._execute(
        sheets.service.spreadsheets().values().get(
            spreadsheetId=OUTPUT_SHEET_ID,
            range="'sync_log'!A1:F",
        )
    ).get("values", [])
    if len(response) <= 1:
        return []
    return response[-n:]


def consecutive_failures(rows: list[list[str]]) -> int:
    count = 0
    for row in reversed(rows):
        status = row[1] if len(row) > 1 else ""
        if status == "ok":
            return count
        count += 1
    return count


def send_telegram_alert(message: str) -> None:
    token = os.environ.get("LARISA_TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("LARISA_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("LARISA_TELEGRAM_BOT_TOKEN / LARISA_TELEGRAM_CHAT_ID не заданы")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
    ).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as response:
        response.read()


def check_and_alert(threshold: int = 2) -> int:
    rows = read_last_sync_rows(threshold + 2)
    failures = consecutive_failures(rows)
    if failures >= threshold:
        last_row = rows[-1] if rows else []
        message = (
            "*Sales KPI Dashboard*\n"
            f"refresh упал {failures} раза подряд.\n"
            f"Последний ts: `{last_row[0] if last_row else 'n/a'}`\n"
            f"Phase: `{last_row[2] if len(last_row) > 2 else 'n/a'}`\n"
            f"Sheet: https://docs.google.com/spreadsheets/d/{OUTPUT_SHEET_ID}/edit"
        )
        send_telegram_alert(message)
    return failures


def append_sync_error(error: str, phase: str = "phase 4") -> None:
    sheets = SheetsClient(OUTPUT_SHEET_ID, GOOGLE_SA_KEY)
    row = [
        datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
        "error",
        phase,
        0,
        0,
        error[:500],
    ]
    sheets.append_log("sync_log", SYNC_LOG_HEADER, [row])
