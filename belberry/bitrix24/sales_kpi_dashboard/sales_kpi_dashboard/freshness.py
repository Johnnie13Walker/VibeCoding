"""Freshness-check для Cloudbot daily health-check."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .alerts import read_last_sync_rows
from .config import MOSCOW_TZ


@dataclass(frozen=True)
class FreshnessResult:
    ok: bool
    status: str
    ts: str
    message: str


def check_sales_kpi_freshness(max_age_hours: int = 6) -> FreshnessResult:
    rows = read_last_sync_rows(1)
    if not rows:
        return FreshnessResult(False, "", "", "sales_kpi: sync_log пустой")
    return evaluate_last_sync_row(rows[-1], now=datetime.now(MOSCOW_TZ), max_age_hours=max_age_hours)


def evaluate_last_sync_row(row: list[str], now: datetime, max_age_hours: int = 6) -> FreshnessResult:
    ts = str(row[0]) if row else ""
    status = str(row[1]) if len(row) > 1 else ""
    if status != "ok":
        return FreshnessResult(False, status, ts, f"sales_kpi: последний refresh status={status or 'n/a'}")

    parsed = _parse_ts(ts)
    if parsed is None:
        return FreshnessResult(False, status, ts, f"sales_kpi: некорректный ts={ts or 'n/a'}")
    if now - parsed > timedelta(hours=max_age_hours):
        return FreshnessResult(False, status, ts, f"sales_kpi: последний ok старше {max_age_hours}ч ({ts})")
    return FreshnessResult(True, status, ts, f"sales_kpi: OK, последний refresh {ts}")


def _parse_ts(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=MOSCOW_TZ)
    return parsed.astimezone(MOSCOW_TZ)
