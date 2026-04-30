"""Contract metadata for Sales / Lev report formatting."""

from __future__ import annotations

SALES_REPORT_FORMAT_VERSION = "lev-petrovich-telegram-v2026-04-01"
FORMATTER_MODULE = "agents.sales_agent.sales_formatter"
REPORT_FORMATS: dict[str, dict[str, str]] = {
    "sales": {
        "template_id": "lev_petrovich.sales_copilot.daily_v2",
        "headline": "📊 Сводка по продажам",
    },
    "pipeline": {
        "template_id": "lev_petrovich.sales_copilot.daily_v2",
        "headline": "📊 Сводка по продажам",
    },
    "risks": {
        "template_id": "lev_petrovich.sales_risks.daily_v1",
        "headline": "⚠️ Риски по сделкам",
    },
    "focus": {
        "template_id": "lev_petrovich.rop_focus.daily_v2",
        "headline": "🎯 Фокус РОПа",
    },
    "weekly": {
        "template_id": "lev_petrovich.sales_weekly.v1",
        "headline": "📊 Отчёт Льва Петровича по продажам",
    },
}
REPORT_REQUIRED_MARKERS: dict[str, list[str]] = {
    "sales": [
        "📊 Сводка по продажам",
        "Итоги за прошлый рабочий день",
        "Воронка",
        "На стадии договора",
        "Источники новых сделок",
    ],
    "pipeline": [
        "📊 Сводка по продажам",
        "Итоги за прошлый рабочий день",
        "Воронка",
        "На стадии договора",
        "Источники новых сделок",
    ],
    "focus": [
        "🎯 Фокус РОПа",
        "Что РОП обязан сделать сегодня:",
        "🔥 Молодцы за вчера",
    ],
    "risks": [
        "⚠️ Риски по сделкам",
        "Без движения > 14 дн.",
        "Без следующего шага",
        "Без коммуникации > 14 дн.",
        "Сделки с просрочками",
    ],
    "weekly": [
        "📊 Отчёт Льва Петровича по продажам",
    ],
}


def report_format_metadata(report_type: str) -> dict[str, str]:
    normalized = str(report_type or "").strip().lower()
    base = REPORT_FORMATS.get(normalized) or REPORT_FORMATS["sales"]
    return {
        "report_type": normalized or "sales",
        "format_version": SALES_REPORT_FORMAT_VERSION,
        "formatter_module": FORMATTER_MODULE,
        "template_id": base["template_id"],
        "headline": base["headline"],
    }


def report_required_markers(report_type: str) -> list[str]:
    normalized = str(report_type or "").strip().lower()
    markers = REPORT_REQUIRED_MARKERS.get(normalized) or REPORT_REQUIRED_MARKERS["sales"]
    return list(markers)
