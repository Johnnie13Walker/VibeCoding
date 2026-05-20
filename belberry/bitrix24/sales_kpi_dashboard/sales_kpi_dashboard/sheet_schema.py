"""Идемпотентный bootstrap Output Sheet «Дашборд Отдел продаж 2026»."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from googleapiclient.errors import HttpError
from sales_dashboard.sheets_client import SheetsClient

from . import config


PLAN_HEADER = ["Period", "Metric", "Dimension", "Value", "Comment"]
SYNC_LOG_HEADER = ["ts", "status", "phase", "duration_ms", "rows_written", "error"]


def _plan_seed_rows() -> list[list[object]]:
    period = datetime.now(config.MOSCOW_TZ).strftime("%Y-%m")
    rows: list[list[object]] = [
        [period, "Встречи_всего", "ALL", 0, "ТМ: план встреч за месяц"],
        [period, "Наборы_всем", "ALL", 0, "ТМ: план наборов/день на каждого"],
        [period, "Звонки_120_всем", "ALL", 0, "ТМ: план звонков 120с+/день"],
        [period, "Встречи_2772", "Исаева Дарья", 0, "ТМ план встреч"],
        [period, "Встречи_2832", "Вострецов Аркадий", 0, "ТМ план встреч"],
    ]
    for product in config.PRODUCTS:
        rows.append([period, f"План_{product}", product, 0, f"Выручка {product} план ₽"])
        rows.append([period, f"План_встреч_{product}", product, 0, f"Встреч с продуктом {product}"])
    rows.extend(
        [
            [period, "План_Прочее", config.OTHER_PRODUCT, 0, "Выручка по прочим продуктам"],
            [period, "План_общий", "TOTAL", 0, "Сумма плана по всем продуктам"],
            [period, "План_МОП_2806", "Деговцова Елизавета", 0, "МОП личный план"],
            [period, "План_МОП_2846", "Семенихин Егор", 0, "МОП личный план"],
        ]
    )
    return rows


def _tab_definitions() -> dict[str, dict[str, Any]]:
    return {
        config.SHEET_TAB_TITLES["Plan"]: {
            "header": PLAN_HEADER,
            "seed": _plan_seed_rows(),
        },
        config.SHEET_TAB_TITLES["tm_metrics"]: {"header": [], "seed": []},
        config.SHEET_TAB_TITLES["sales_plan"]: {"header": [], "seed": []},
        config.SHEET_TAB_TITLES["mop_metrics"]: {"header": [], "seed": []},
        config.SHEET_TAB_TITLES["sync_log"]: {"header": SYNC_LOG_HEADER, "seed": []},
    }


def bootstrap_schema(sheets: SheetsClient | None = None, dry_run: bool = False) -> dict[str, list[str]]:
    """Создаёт недостающие вкладки, пишет header+seed только в пустые вкладки."""
    sheets = sheets or SheetsClient(config.OUTPUT_SHEET_ID, config.GOOGLE_SA_KEY)
    existing = sheets.get_tabs()
    report: dict[str, list[str]] = {
        "created": [],
        "kept": [],
        "seeded": [],
        "archived": [],
        "dry_run": [str(dry_run).lower()],
    }

    for tab_name, spec in _tab_definitions().items():
        if tab_name in existing:
            report["kept"].append(tab_name)
        else:
            report["created"].append(tab_name)
            if not dry_run:
                _add_sheet(sheets, tab_name)

        if spec["header"] and _tab_header_empty(sheets, tab_name, exists=tab_name in existing, dry_run=dry_run):
            report["seeded"].append(tab_name)
            if not dry_run:
                _write_rows(sheets, tab_name, [spec["header"], *spec["seed"]])

    if "Лист1" in existing:
        archive_title = _archive_title(existing)
        report["archived"].append(f"Лист1 → {archive_title} (hidden)")
        if not dry_run:
            _rename_and_hide_sheet(sheets, existing["Лист1"], archive_title)

    return report


def _tab_header_empty(sheets: SheetsClient, tab_name: str, *, exists: bool, dry_run: bool) -> bool:
    if dry_run and not exists:
        return True
    try:
        values = sheets._execute(
            sheets.service.spreadsheets().values().get(
                spreadsheetId=config.OUTPUT_SHEET_ID,
                range=f"'{tab_name}'!A1:Z1",
            )
        ).get("values", [])
    except HttpError as exc:
        status = getattr(exc, "status_code", None) or getattr(getattr(exc, "resp", None), "status", None)
        if status == 400 and dry_run:
            return True
        raise
    return not values


def _add_sheet(sheets: SheetsClient, tab_name: str) -> None:
    sheets._execute(
        sheets.service.spreadsheets().batchUpdate(
            spreadsheetId=config.OUTPUT_SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        )
    )


def _write_rows(sheets: SheetsClient, tab_name: str, rows: list[list[object]]) -> None:
    sheets._execute(
        sheets.service.spreadsheets().values().update(
            spreadsheetId=config.OUTPUT_SHEET_ID,
            range=f"'{tab_name}'!A1",
            valueInputOption="RAW",
            body={"values": rows},
        )
    )


def _rename_and_hide_sheet(sheets: SheetsClient, sheet_id: int, title: str) -> None:
    sheets._execute(
        sheets.service.spreadsheets().batchUpdate(
            spreadsheetId=config.OUTPUT_SHEET_ID,
            body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": sheet_id, "title": title, "hidden": True},
                            "fields": "title,hidden",
                        }
                    }
                ]
            },
        )
    )


def _archive_title(existing: dict[str, int]) -> str:
    title = "_archive_лист1"
    if title not in existing:
        return title
    index = 2
    while f"{title}_{index}" in existing:
        index += 1
    return f"{title}_{index}"
