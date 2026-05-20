from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from googleapiclient.errors import HttpError

from sales_dashboard.sheets_client import SheetsClient

from .config import GOOGLE_SA_KEY, MOSCOW_TZ, OUTPUT_SHEET_ID
from .metrics import mop_effectiveness, sales_plan, telemarketing
from .reader import BitrixReader


@dataclass
class PlanData:
    by_key: dict[str, float]

    def get(self, key: str, default: float = 0.0) -> float:
        return self.by_key.get(key, default)


def read_plan(sheets_client: SheetsClient, today: datetime | None = None) -> PlanData:
    now = today or datetime.now(MOSCOW_TZ)
    period = now.strftime("%Y-%m")
    try:
        response = sheets_client._execute(
            sheets_client.service.spreadsheets().values().get(
                spreadsheetId=OUTPUT_SHEET_ID,
                range="'Plan'!A1:D",
                valueRenderOption="UNFORMATTED_VALUE",
            )
        )
    except Exception:
        return PlanData({})

    values = response.get("values") or []
    if len(values) <= 1:
        return PlanData({})
    plan: dict[str, float] = {}
    for row in values[1:]:
        row_period = str(_cell(row, 0)).strip()
        if row_period and row_period != period:
            continue
        metric = str(_cell(row, 1)).strip()
        dimension = str(_cell(row, 2)).strip()
        if not metric:
            continue
        value = _float(_cell(row, 3))
        plan[metric] = value
        if dimension:
            plan[f"{metric}_{dimension}"] = value
    return PlanData(plan)


def aggregate() -> dict[str, list[list[object]]]:
    today = datetime.now(MOSCOW_TZ).date()
    sheets = SheetsClient(OUTPUT_SHEET_ID, GOOGLE_SA_KEY)
    plan = read_plan(sheets)
    reader = BitrixReader()
    return {
        "tm_metrics": telemarketing.compute(reader, plan, today),
        "sales_plan": sales_plan.compute(reader, plan, today),
        "mop_metrics": mop_effectiveness.compute(reader, today),
        "sync_log": [
            ["ts", "status", "phase"],
            [datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"), "ok", "phase 2"],
        ],
    }


def _cell(row: list[Any], index: int) -> Any:
    return row[index] if index < len(row) else ""


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
