from __future__ import annotations

import datetime as dt
from html import escape as _esc
from pathlib import Path
from string import Template
from typing import Iterable, Optional

from .models import Baseline30d, DailyMetrics, Verdict
from .verdict import format_minutes


def _bold(value: str) -> str:
    """Жирное выделение для сегодняшних значений (Telegram HTML)."""
    return f"<b>{_esc(value)}</b>"


def _bold_top_flag(verdict: Verdict) -> str:
    """top_flag.text + замена value на <b>value</b> один раз, если value известно."""
    if not verdict.flags:
        return verdict.top_flag
    top = verdict.flags[0]
    if top.value and top.value in top.text:
        return top.text.replace(top.value, _bold(top.value), 1)
    return top.text

WEEKDAY_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTH_RU = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

TEMPLATES_DIR = Path(__file__).with_name("templates")


def render_morning_brief(
    report_date: dt.date,
    today: DailyMetrics,
    baseline: Baseline30d,
    verdict: Verdict,
    history: Iterable[DailyMetrics],
    *,
    header_note: Optional[str] = None,  # игнорируется в новом формате
) -> str:
    trend = trend_summary(list(history), report_date)
    baseline_note = " (baseline неполный)" if baseline.incomplete else ""
    sleep_need = format_minutes(today.sleep_need_minutes)
    sleep_last = _bold(format_minutes(today.sleep_minutes)) if today.sleep_minutes is not None else "н/д"
    metrics = _metrics_block(today, baseline, verdict)
    top_flag = _bold_top_flag(verdict)

    template = _load_template("morning_brief.txt")
    return template.safe_substitute(
        date_header=_date_header(report_date),
        emoji=verdict.emoji,
        headline=verdict.headline,
        top_flag=top_flag,
        training_duration=verdict.plan.duration,
        hr_zone=verdict.plan.hr_zone,
        modality=verdict.plan.modality,
        steps_target=verdict.plan.steps_target,
        sleep_action=verdict.plan.sleep_action,
        sleep_last=sleep_last,
        sleep_need=sleep_need,
        baseline_note=baseline_note,
        metrics=metrics,
        trend_recovery=trend["recovery"],
        trend_summary=trend["summary"],
    ).strip()


def render_weekly_brief(
    week_start: dt.date,
    week_end: dt.date,
    history: Iterable[DailyMetrics],
    *,
    workouts_count: int = 0,
) -> str:
    rows = [item for item in history if week_start.isoformat() <= item.date <= week_end.isoformat()]
    rows.sort(key=lambda item: item.date)
    recovery_avg = _avg(item.recovery for item in rows)
    hrv_avg = _avg(item.hrv_ms for item in rows)
    rhr_avg = _avg(item.rhr_bpm for item in rows)
    sleep_avg = _avg(item.sleep_minutes for item in rows)
    strain_avg = _avg(item.strain for item in rows)
    best = _best_recovery(rows)
    worst = _worst_recovery(rows)

    template = _load_template("weekly_brief.txt")
    return template.safe_substitute(
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        recovery_avg=_percent(recovery_avg),
        hrv_avg=_number(hrv_avg, "ms"),
        rhr_avg=_number(rhr_avg),
        sleep_avg=format_minutes(int(round(sleep_avg))) if sleep_avg is not None else "н/д",
        strain_avg=f"{strain_avg:.1f}" if strain_avg is not None else "н/д",
        workouts_count=str(workouts_count),
        recovery_spark=_spark(item.recovery for item in rows),
        sleep_spark=_spark(item.sleep_minutes for item in rows),
        strain_spark=_spark(item.strain for item in rows),
        best_recovery=best,
        worst_recovery=worst,
    ).strip()


def trend_summary(history: list[DailyMetrics], report_date: dt.date) -> dict[str, str]:
    by_date = {item.date: item for item in history}
    start = report_date - dt.timedelta(days=6)
    rec_parts: list[str] = []
    hrv_vals: list[Optional[float]] = []
    rhr_vals: list[Optional[float]] = []
    sleep_vals: list[Optional[float]] = []
    strain_vals: list[Optional[float]] = []
    for offset in range(7):
        day = start + dt.timedelta(days=offset)
        item = by_date.get(day.isoformat())
        weekday = WEEKDAY_SHORT[day.weekday()]
        is_today = day == report_date
        if item and item.recovery is not None:
            value_str = f"{int(item.recovery)}"
            if is_today:
                rec_parts.append(f"{weekday} {_bold(value_str)}")
            else:
                rec_parts.append(f"{weekday} {value_str}")
        else:
            rec_parts.append(f"{weekday} —")
        hrv_vals.append(item.hrv_ms if item else None)
        rhr_vals.append(item.rhr_bpm if item else None)
        sleep_vals.append(item.sleep_minutes if item else None)
        strain_vals.append(item.strain if item else None)

    hrv_avg = _avg(hrv_vals)
    rhr_avg = _avg(rhr_vals)
    sleep_avg = _avg(sleep_vals)
    strain_avg = _avg(strain_vals)
    sleep_str = format_minutes(int(round(sleep_avg))) if sleep_avg is not None else "н/д"
    strain_str = f"{strain_avg:.1f}" if strain_avg is not None else "н/д"
    summary = (
        f"HRV {_number(hrv_avg, 'ms')} · "
        f"RHR {_number(rhr_avg)} · "
        f"Сон {sleep_str} · "
        f"Strain {strain_str}"
    )
    return {
        "recovery": " · ".join(rec_parts),
        "summary": summary,
    }


def _metrics_block(today: DailyMetrics, baseline: Baseline30d, verdict: Verdict) -> str:
    top_flag_code = verdict.flags[0].code if verdict.flags else None
    other_flag_codes = {flag.code for flag in verdict.flags[1:]} if len(verdict.flags) > 1 else set()
    lines: list[str] = []

    _ = other_flag_codes  # зарезервировано для будущей фильтрации
    rec_line = _metric_line_recovery(today, baseline, suppress=top_flag_code == "recovery_red")
    if rec_line:
        lines.append(rec_line)

    hrv_line = _metric_line(
        name="HRV",
        value=today.hrv_ms,
        baseline_value=baseline.hrv_ms,
        unit="ms",
        epsilon=2.0,
        higher_is_better=True,
        suppress=top_flag_code == "hrv_low",
    )
    if hrv_line:
        lines.append(hrv_line)

    rhr_line = _metric_line(
        name="RHR",
        value=today.rhr_bpm,
        baseline_value=baseline.rhr_bpm,
        unit="",
        epsilon=2.0,
        higher_is_better=False,
        suppress=top_flag_code == "rhr_high",
    )
    if rhr_line:
        lines.append(rhr_line)

    if today.sleep_efficiency_pct is not None and top_flag_code != "sleep_low":
        lines.append(f"✅ Сон-эффективность {_bold(_percent(today.sleep_efficiency_pct))}")

    for flag in verdict.flags[1:]:
        if flag.code in {"recovery_red", "hrv_low", "rhr_high", "sleep_low"}:
            continue
        lines.append(f"{flag.emoji} {flag.text}")

    if not lines:
        lines.append("✅ Все метрики в норме")
    return "\n".join(lines)


def _metric_line_recovery(today: DailyMetrics, baseline: Baseline30d, *, suppress: bool) -> Optional[str]:
    if suppress or today.recovery is None:
        return None
    today_str = _bold(_percent(today.recovery))
    delta_baseline = _format_delta(today.recovery, baseline.recovery, unit=" п.п.", epsilon=3.0)
    if delta_baseline is None:
        return f"✅ Восстановление {today_str} — как baseline"
    diff = today.recovery - (baseline.recovery or 0)
    good = diff > 0
    marker = "✅" if good else "⚠️"
    return f"{marker} Восстановление {today_str} ({delta_baseline})"


def _metric_line(
    *,
    name: str,
    value: Optional[float],
    baseline_value: Optional[float],
    unit: str,
    epsilon: float,
    higher_is_better: bool,
    suppress: bool,
) -> Optional[str]:
    if suppress or value is None:
        return None
    today_str = _bold(_number(value, unit))
    if baseline_value is None:
        return f"✅ {name} {today_str}"
    delta = _format_delta(value, baseline_value, unit=unit, epsilon=epsilon)
    if delta is None:
        return f"✅ {name} {today_str} — как baseline"
    diff = value - baseline_value
    good = (diff > 0) if higher_is_better else (diff < 0)
    marker = "✅" if good else "⚠️"
    return f"{marker} {name} {today_str} ({delta} к baseline {_number(baseline_value, unit)})"


def _format_delta(value: float, baseline: float, *, unit: str, epsilon: float) -> Optional[str]:
    diff = value - baseline
    if abs(diff) <= epsilon:
        return None
    sign = "+" if diff > 0 else "−"
    return f"{sign}{abs(diff):.0f}{unit}"


def _date_header(value: dt.date) -> str:
    return f"{value.day} {MONTH_RU.get(value.month, value.month)} · {WEEKDAY_SHORT[value.weekday()].lower()}"


def _load_template(name: str) -> Template:
    return Template((TEMPLATES_DIR / name).read_text(encoding="utf-8"))


def _avg(values: Iterable[Optional[float]]) -> Optional[float]:
    nums = [float(value) for value in values if value is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _number(value: Optional[float], unit: str = "") -> str:
    if value is None:
        return "н/д"
    return f"{value:.0f}{unit}"


def _percent(value: Optional[float]) -> str:
    if value is None:
        return "н/д"
    return f"{value:.0f}%"


def _spark(values: Iterable[Optional[float]]) -> str:
    nums = [value for value in values if value is not None]
    if not nums:
        return "н/д"
    blocks = "▁▂▃▄▅▆▇█"
    lo = min(nums)
    hi = max(nums)
    if hi == lo:
        return blocks[3] * len(nums)
    out = []
    for value in nums:
        idx = int(round((value - lo) / (hi - lo) * (len(blocks) - 1)))
        out.append(blocks[idx])
    return "".join(out)


def _best_recovery(rows: list[DailyMetrics]) -> str:
    candidates = [item for item in rows if item.recovery is not None]
    if not candidates:
        return "н/д"
    best = max(candidates, key=lambda item: item.recovery or 0)
    return f"{best.recovery:.0f}% ({best.date})"


def _worst_recovery(rows: list[DailyMetrics]) -> str:
    candidates = [item for item in rows if item.recovery is not None]
    if not candidates:
        return "н/д"
    worst = min(candidates, key=lambda item: item.recovery or 0)
    return f"{worst.recovery:.0f}% ({worst.date})"

