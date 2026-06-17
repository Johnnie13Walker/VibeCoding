"""Генерация Looker Studio Linking API URL.

Открытие этой ссылки = создать новый отчёт с уже подключёнными data sources
из нашего Sheet (deals, calls, users, stages, categories).
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sales_dashboard import config
from sales_dashboard.sheets_client import SheetsClient


def main() -> int:
    sh = SheetsClient(config.SHEET_ID, config.SERVICE_ACCOUNT_JSON)
    meta = sh._execute(
        sh.service.spreadsheets().get(spreadsheetId=config.SHEET_ID)
    )
    tabs = {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in meta.get("sheets", [])
    }

    targets = [
        ("deals", config.TAB_DEALS, "Сделки"),
        ("calls", config.TAB_CALLS, "Звонки"),
        ("users", config.TAB_USERS, "Менеджеры"),
        ("stages", config.TAB_STAGES, "Стадии"),
        ("categories", config.TAB_CATEGORIES, "Воронки"),
    ]

    params: list[tuple[str, str]] = []
    for alias, tab_name, display_name in targets:
        gid = tabs.get(tab_name)
        if gid is None:
            print(f"WARNING: tab '{tab_name}' not found, skipping")
            continue
        params.append((f"ds.{alias}.connector", "googleSheets"))
        params.append((f"ds.{alias}.datasourceName", display_name))
        params.append((f"ds.{alias}.spreadsheetId", config.SHEET_ID))
        params.append((f"ds.{alias}.worksheetId", str(gid)))
        params.append((f"ds.{alias}.hasHeader", "true"))
        params.append((f"ds.{alias}.refreshFields", "true"))

    url = "https://lookerstudio.google.com/reporting/create?" + urllib.parse.urlencode(
        params
    )
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
