from __future__ import annotations

import datetime as dt
import json
import os
import statistics
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Optional

from .models import Baseline30d, DailyMetrics

DEFAULT_STATE_PATH = Path("/var/lib/cloudbot-larisa-whoop/whoop-state.json")


def state_path(explicit: Optional[str] = None) -> Path:
    if explicit:
        return Path(explicit)
    env_path = os.getenv("WHOOP_STATE_FILE", "").strip()
    if env_path:
        return Path(env_path)
    return DEFAULT_STATE_PATH


def load_state(path: Optional[str] = None) -> dict[str, Any]:
    target = state_path(path)
    if not target.exists():
        return {"daily_sent": {}, "weekly_sent": {}, "daily_metrics": []}
    try:
        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {"daily_sent": {}, "weekly_sent": {}, "daily_metrics": []}
    if not isinstance(data, dict):
        return {"daily_sent": {}, "weekly_sent": {}, "daily_metrics": []}
    data.setdefault("daily_sent", {})
    data.setdefault("weekly_sent", {})
    data.setdefault("daily_metrics", [])
    return data


def save_state(data: dict[str, Any], path: Optional[str] = None) -> None:
    target = state_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass


def _date_key(value: DailyMetrics | dict[str, Any]) -> str:
    if isinstance(value, DailyMetrics):
        return value.date
    return str(value.get("date", ""))


def update_daily_metrics(data: dict[str, Any], metrics: DailyMetrics, *, keep_days: int = 45) -> dict[str, Any]:
    rows = [row for row in data.get("daily_metrics", []) if isinstance(row, dict) and row.get("date") != metrics.date]
    rows.append(asdict(metrics))
    rows.sort(key=_date_key)
    data["daily_metrics"] = rows[-keep_days:]
    return data


def metrics_from_state(data: dict[str, Any]) -> list[DailyMetrics]:
    rows: list[DailyMetrics] = []
    for row in data.get("daily_metrics", []):
        if not isinstance(row, dict) or not row.get("date"):
            continue
        rows.append(
            DailyMetrics(
                date=str(row.get("date")),
                recovery=_to_float(row.get("recovery")),
                hrv_ms=_to_float(row.get("hrv_ms")),
                rhr_bpm=_to_float(row.get("rhr_bpm")),
                spo2_pct=_to_float(row.get("spo2_pct")),
                sleep_minutes=_to_int(row.get("sleep_minutes")),
                sleep_need_minutes=_to_int(row.get("sleep_need_minutes")),
                sleep_performance_pct=_to_float(row.get("sleep_performance_pct")),
                sleep_efficiency_pct=_to_float(row.get("sleep_efficiency_pct")),
                strain=_to_float(row.get("strain")),
            )
        )
    rows.sort(key=lambda item: item.date)
    return rows


def baseline_30d(history: Iterable[DailyMetrics], report_date: str) -> Baseline30d:
    cutoff = dt.date.fromisoformat(report_date)
    rows = [
        item
        for item in history
        if _safe_date(item.date) is not None and _safe_date(item.date) <= cutoff
    ][-30:]
    return Baseline30d(
        sample_count=len(rows),
        recovery=_median(item.recovery for item in rows),
        hrv_ms=_median(item.hrv_ms for item in rows),
        rhr_bpm=_median(item.rhr_bpm for item in rows),
        sleep_minutes=_to_int(_median(item.sleep_minutes for item in rows)),
        sleep_efficiency_pct=_median(item.sleep_efficiency_pct for item in rows),
    )


def backfill_state(history: Iterable[DailyMetrics], *, path: Optional[str] = None) -> dict[str, Any]:
    data = load_state(path)
    for metrics in history:
        update_daily_metrics(data, metrics)
    save_state(data, path)
    return data


def _median(values: Iterable[Optional[float]]) -> Optional[float]:
    nums = [float(value) for value in values if value is not None]
    if not nums:
        return None
    return float(statistics.median(nums))


def _safe_date(value: str) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None

