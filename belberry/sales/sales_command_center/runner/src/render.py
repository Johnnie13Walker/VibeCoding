import html
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .transform import manager_name

PORTAL_BASE = "https://belberrycrm.bitrix24.ru"
REJECTION_STAGES = {"C10:LOSE", "C50:APOLOGY"}
SECTION_TITLES = [
    "Главное за 30 секунд",
    "Тигр дня",
    "Кого пинать сегодня",
    "Где могут сорваться сделки",
    "Зависшие сделки по стадиям",
    "Активность менеджеров",
    "Встречи дня",
    "Содержательный разбор встреч",
    "Брифы и КП дня",
    "Отказы дня",
    "Системные паттерны",
    "Итог дня",
    "Технический долг / ограничения",
]
SECTION_H2_MARKERS = [
    "<h2>Главное за 30 секунд</h2>",
    "<h2>Тигр дня</h2>",
    "<h2>Кого пинать сегодня</h2>",
    "<h2>Где могут сорваться сделки</h2>",
    "<h2>Зависшие сделки по стадиям</h2>",
    "<h2>Активность менеджеров</h2>",
    "<h2>Встречи дня</h2>",
    "<h2>Содержательный разбор встреч</h2>",
    "<h2>Брифы и КП дня</h2>",
    "<h2>Отказы дня</h2>",
    "<h2>Системные паттерны</h2>",
    "<h2>Итог дня</h2>",
    "<h2>Технический долг / ограничения</h2>",
]


def deal_url(item_id: Any) -> str:
    return f"{PORTAL_BASE}/crm/deal/details/{item_id}/"


def meeting_url(item_id: Any) -> str:
    return f"{PORTAL_BASE}/crm/type/1048/details/{item_id}/"


def brief_url(item_id: Any) -> str:
    return f"{PORTAL_BASE}/crm/type/1056/details/{item_id}/"


def kp_url(item_id: Any) -> str:
    return f"{PORTAL_BASE}/crm/type/1106/details/{item_id}/"


def a(url: str, text: Any) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(str(text))}</a>'


def llm_placeholder() -> str:
    return '<div class="data-llm-placeholder">Будет заполнено разбором встреч в Фазе 3</div>'


def extract_rejections(raw: dict[str, Any], users: dict[Any, str] | None = None) -> list[dict[str, Any]]:
    users = users or raw.get("users") or {}
    deal_index = {
        str(deal.get("ID")): deal
        for deal in [*raw.get("deals_created", []), *raw.get("deals_open", [])]
    }
    rejections = []
    for item in raw.get("stagehistory", []):
        if item.get("STAGE_ID") not in REJECTION_STAGES:
            continue
        deal_id = str(item.get("OWNER_ID"))
        deal = deal_index.get(deal_id, {})
        manager_id = deal.get("ASSIGNED_BY_ID")
        rejections.append(
            {
                "deal_id": deal_id,
                "title": deal.get("TITLE") or f"Сделка {deal_id}",
                "manager": manager_name(users, manager_id) if manager_id else "не назначен",
                "stage": item.get("STAGE_ID"),
                "reason": item.get("STAGE_SEMANTIC_ID") or item.get("STAGE_ID"),
                "created_time": item.get("CREATED_TIME"),
            }
        )
    return rejections


def render_report(rows: dict[str, list[dict[str, Any]]], extras: dict[str, Any]) -> str:
    users = extras.get("users") or {}
    photos = extras.get("photos") or {}
    raw = extras.get("raw") or {}
    stale = extras.get("stale") or {}
    narrative = extras.get("narrative") or {}
    analyses = extras.get("analyses") or {}
    rejections = extras.get("rejections")
    if rejections is None:
        rejections = extract_rejections(raw, users)

    css = _load_css()
    tiger = _choose_tiger(rows.get("manager_activity", []), users)
    report_date = extras.get("report_date") or raw.get("report_date") or ""

    parts = [
        "<!DOCTYPE html><html lang=\"ru\"><head><meta charset=\"UTF-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
        f"<title>Сводка продаж {html.escape(str(report_date))}</title>",
        f"<style>{css}</style>",
        "</head><body><div class=\"wrap\">",
        f"<h1>Сводка отдела продаж · {html.escape(str(report_date))}</h1>",
        _stats(rows, rejections, stale),
        _section("Главное за 30 секунд", _narrative_text(narrative, "thirty_seconds") or llm_placeholder(), "red"),
        _tiger_section(tiger, photos, narrative),
        _section("Кого пинать сегодня", _narrative_text(narrative, "pinch_list") or llm_placeholder(), "red"),
        _risk_section(stale),
        _stale_section(stale),
        _activity_section(rows.get("manager_activity", []), users, photos),
        _meetings_section(rows.get("meetings", []), raw.get("meet_day", []), users),
        _section(
            "Содержательный разбор встреч",
            _meeting_analysis_body(analyses, rows.get("meetings", []), raw.get("meet_day", []), users),
            "purple",
        ),
        _briefs_kp_section(rows.get("kp_briefs", []), raw, users),
        _rejections_section(rejections),
        _section("Системные паттерны", _narrative_text(narrative, "systemic_patterns") or llm_placeholder(), "blue"),
        _section("Итог дня", _narrative_text(narrative, "day_summary") or llm_placeholder(), "green"),
        _tech_debt_section(),
        "</div></body></html>",
    ]
    return "\n".join(parts)


DEFAULT_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f4f6fb;color:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.5}
.wrap{max-width:880px;margin:0 auto;padding:24px 20px 64px}
h1{font-size:26px;font-weight:800;margin:8px 0 20px}
section{background:#fff;border:1px solid #e6e9f0;border-radius:14px;padding:18px 20px;margin:16px 0;box-shadow:0 1px 2px rgba(15,23,42,.04)}
.section-head{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.section-head h2{font-size:18px;font-weight:700;margin:0}
.section-icon{width:10px;height:10px;border-radius:50%;font-size:0;flex:0 0 auto}
.section-icon.red{background:#ef4444}.section-icon.blue{background:#3b82f6}.section-icon.green{background:#22c55e}.section-icon.purple{background:#8b5cf6}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin:0 0 8px}
.stat{background:#fff;border:1px solid #e6e9f0;border-radius:12px;padding:14px 16px;text-align:center}
.stat-value{font-size:28px;font-weight:800;line-height:1}
.stat-label{margin-top:6px;font-size:13px;color:#64748b}
.tiger{display:flex;align-items:center;gap:14px;margin-bottom:8px}
.tiger-photo{width:64px;height:64px;border-radius:50%;object-fit:cover;background:#e2e8f0}
.tiger-name{font-size:18px;font-weight:700}
.tiger-metric{color:#475569;font-size:14px}
.tiger-caption{margin-top:6px}
.tiger-disclaimer{margin-top:8px;font-size:12px;color:#94a3b8}
.managers{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.mgr{display:flex;align-items:center;gap:10px;background:#f8fafc;border:1px solid #eef2f7;border-radius:12px;padding:10px 12px}
.mgr-ava{width:40px;height:40px;border-radius:50%;object-fit:cover;background:#e2e8f0;flex:0 0 auto}
.mgr-name{font-weight:600}
.hilight{background:#f1f5f9;border-radius:10px;padding:10px 12px;margin:6px 0}
.hilight.risk{background:#fef2f2;border:1px solid #fee2e2}
.data-llm-placeholder{color:#94a3b8;font-style:italic}
ul{margin:6px 0;padding-left:20px}
strong,b{font-weight:700}
""".strip()


def _load_css() -> str:
    # CSS вшит в модуль. Раньше читался из /tmp/sales_2905/style.css (локальная
    # папка мака) — на сервере её нет → отчёт рендерился без стилей. Override
    # через SCC_REPORT_CSS_PATH оставлен для локальной кастомизации.
    override = os.environ.get("SCC_REPORT_CSS_PATH")
    if override and Path(override).exists():
        return Path(override).read_text().replace("<style>", "").replace("</style>", "")
    return DEFAULT_CSS


def _section(title: str, body: str, color: str = "blue") -> str:
    return (
        f'<section><div class="section-head"><div class="section-icon {color}">•</div>'
        f"<h2>{html.escape(title)}</h2></div>{body}</section>"
    )


def _stats(rows: dict[str, list[dict[str, Any]]], rejections, stale) -> str:
    stale_count = sum(len(items) for items in stale.values())
    calls = sum(item.get("dials_total", 0) for item in rows.get("manager_activity", []))
    cards = [
        ("Встречи дня", len(rows.get("meetings", []))),
        ("Брифы и КП", len(rows.get("kp_briefs", []))),
        ("Звонки", calls),
        ("Зависшие", stale_count),
        ("Отказы", len(rejections)),
    ]
    body = "".join(
        f'<div class="stat"><div class="stat-value">{value}</div><div class="stat-label">{html.escape(label)}</div></div>'
        for label, value in cards
    )
    return f'<div class="stats">{body}</div>'


def _choose_tiger(activity: list[dict[str, Any]], users: dict[Any, str]) -> dict[str, Any] | None:
    if not activity:
        return None
    winner = max(
        activity,
        key=lambda row: (
            row.get("dials_total", 0),
            row.get("calls_120s_plus", 0),
            row.get("calls_answered", 0),
        ),
    )
    return {**winner, "name": manager_name(users, winner.get("manager_id"))}


def _tiger_section(tiger: dict[str, Any] | None, photos: dict[Any, str], narrative: dict[str, Any] | None = None) -> str:
    if tiger:
        name = tiger["name"]
        photo = photos.get(str(tiger.get("manager_id"))) or photos.get(name) or ""
        body = (
            '<div class="tiger">'
            f'<img class="tiger-photo" src="{html.escape(photo, quote=True)}" alt="">'
            f'<div><div class="tiger-name">{html.escape(name)}</div>'
            f'<div class="tiger-metric">{tiger.get("dials_total", 0)} наборов · '
            f'{tiger.get("calls_answered", 0)} дозвонов · '
            f'{tiger.get("calls_120s_plus", 0)} разговоров ≥120 с</div>'
            f"{_tiger_caption(narrative)}</div></div>"
        )
    else:
        body = llm_placeholder()
    body += (
        '<p class="tiger-disclaimer">Рейтинг рассчитан по телефонии за день; '
        'официальная сводка «Опер» недоступна.</p>'
    )
    return _section("Тигр дня", body, "amber")


def _tiger_caption(narrative: dict[str, Any] | None) -> str:
    caption = (narrative or {}).get("tiger_caption")
    if caption:
        return f'<div class="tiger-caption">{html.escape(str(caption))}</div>'
    return '<div class="tiger-caption">Детерминированный лидер по телефонии дня.</div>'


def _narrative_text(narrative: dict[str, Any], key: str) -> str | None:
    value = narrative.get(key)
    if not value:
        return None
    if key == "thirty_seconds" and isinstance(value, dict):
        return "<ul>" + "".join(
            f"<li><b>{html.escape(label)}:</b> {html.escape(str(value.get(label, '')))}</li>"
            for label in ["горит", "деньги", "системно"]
            if value.get(label)
        ) + "</ul>"
    if key == "pinch_list" and isinstance(value, list):
        return "<ul>" + "".join(
            f"<li><b>{html.escape(str(item.get('name', '')))}:</b> "
            f"{html.escape(str(item.get('action', '')))} — {html.escape(str(item.get('why', '')))}</li>"
            for item in value
        ) + "</ul>"
    if key == "systemic_patterns" and isinstance(value, dict):
        works = "".join(f"<li>{html.escape(str(item))}</li>" for item in value.get("works", []))
        repeats = "".join(f"<li>{html.escape(str(item))}</li>" for item in value.get("repeats", []))
        return f"<h3>Что работает</h3><ul>{works}</ul><h3>Что повторяется</h3><ul>{repeats}</ul>"
    if key == "quote_of_day" and isinstance(value, dict):
        return f"<blockquote>{html.escape(str(value.get('text', '')))}</blockquote><p>{html.escape(str(value.get('meta', '')))}</p>"
    return f"<p>{html.escape(str(value))}</p>"


def _meeting_analysis_body(analyses, meetings, raw_meetings, users) -> str:
    raw_index = {int(item.get("id")): item for item in raw_meetings if item.get("id") is not None}
    blocks = []
    for row in meetings:
        meeting_id = int(row["meeting_id"])
        analysis = analyses.get(meeting_id) or analyses.get(str(meeting_id))
        raw = raw_index.get(meeting_id, {})
        title = raw.get("title") or f"Встреча {meeting_id}"
        header = f"<h3>{a(meeting_url(meeting_id), title)} · {html.escape(manager_name(users, row.get('manager_id')))}</h3>"
        if not analysis:
            blocks.append(header + llm_placeholder())
            continue
        if analysis.get("analysis_available") is False or analysis.get("transcript_status") != "ok":
            reason = html.escape(str(analysis.get("reason") or "Разбор невозможен: транскрипта нет"))
            blocks.append(header + f'<div class="hilight risk">⚠️ Разбор невозможен: {reason}. Проблема контроля.</div>')
            continue
        checklist = "".join(
            f"<li>{html.escape(str(item.get('mark', '')))} <b>{html.escape(str(item.get('item', '')))}</b>: "
            f"{html.escape(str(item.get('note', '')))}</li>"
            for item in analysis.get("checklist", [])
        )
        quote = analysis.get("client_quote")
        quote_html = f"<blockquote>💬 {html.escape(str(quote))}</blockquote>" if quote else ""
        conclusion = html.escape(str(analysis.get("systemic_conclusion") or ""))
        discrepancy = ""
        if analysis.get("status_discrepancy"):
            discrepancy = (
                '<div class="hilight risk">Расхождение со статусом Bitrix: '
                f'{html.escape(str(analysis.get("status_discrepancy_note") or ""))}</div>'
            )
        blocks.append(
            header
            + f"<ul>{checklist}</ul>"
            + quote_html
            + f"<p>🔧 {conclusion}</p>"
            + discrepancy
            + f"<p><b>Вердикт:</b> {html.escape(str(analysis.get('verdict') or ''))}</p>"
        )
    return "".join(blocks) or llm_placeholder()


def _risk_section(stale: dict[str, list[dict[str, Any]]]) -> str:
    top = sorted(
        [item for rows in stale.values() for item in rows],
        key=lambda row: row.get("opportunity", 0),
        reverse=True,
    )[:6]
    if not top:
        body = "<p>Критичных зависших сделок по порогам стадии нет.</p>"
    else:
        body = "<ul>" + "".join(
            f"<li>{a(deal_url(item['deal_id']), item['title'])} · "
            f"{_money(item.get('opportunity'))} · {item['stage_label']} · "
            f"{item['age']} {html.escape(item['age_unit'])}</li>"
            for item in top
        ) + "</ul>"
    return _section("Где могут сорваться сделки", body, "amber")


def _stale_section(stale: dict[str, list[dict[str, Any]]]) -> str:
    body = []
    for stage, items in stale.items():
        body.append(f"<h3>{html.escape(stage)}</h3><table><tbody>")
        for item in items[:20]:
            body.append(
                "<tr>"
                f"<td>{a(deal_url(item['deal_id']), item['title'])}</td>"
                f"<td>{_money(item.get('opportunity'))}</td>"
                f"<td>{item['age']} {html.escape(item['age_unit'])}</td>"
                f"<td>контакт {item.get('last_contact_days', 999)} дн.</td>"
                "</tr>"
            )
        body.append("</tbody></table>")
    return _section("Зависшие сделки по стадиям", "".join(body) or "<p>Нет.</p>", "amber")


def _activity_section(activity: list[dict[str, Any]], users: dict[Any, str], photos: dict[Any, str]) -> str:
    rows = []
    for item in sorted(activity, key=lambda row: row.get("dials_total", 0), reverse=True):
        name = manager_name(users, item.get("manager_id"))
        photo = photos.get(str(item.get("manager_id"))) or photos.get(name) or ""
        rows.append(
            '<div class="mgr">'
            f'<img class="mgr-ava" src="{html.escape(photo, quote=True)}" alt="">'
            f'<div class="mgr-name">{html.escape(name)}</div>'
            f'<div>Наборы: {item.get("dials_total", 0)} · дозвоны: {item.get("calls_answered", 0)} · '
            f'120с+: {item.get("calls_120s_plus", 0)} · встречи: {item.get("meetings_held", 0)}</div>'
            "</div>"
        )
    return _section("Активность менеджеров", '<div class="managers">' + "".join(rows) + "</div>", "blue")


def _meetings_section(meetings: list[dict[str, Any]], raw_meetings, users) -> str:
    raw_index = {int(item.get("id")): item for item in raw_meetings if item.get("id") is not None}
    rows = []
    for item in meetings:
        raw = raw_index.get(item["meeting_id"], {})
        title = raw.get("title") or f"Встреча {item['meeting_id']}"
        rows.append(
            "<tr>"
            f"<td>{a(meeting_url(item['meeting_id']), title)}</td>"
            f"<td>{html.escape(str(item.get('meeting_type') or ''))}</td>"
            f"<td>{html.escape(manager_name(users, item.get('manager_id')))}</td>"
            f"<td>{html.escape(str(item.get('scheduled_at') or ''))}</td>"
            "</tr>"
        )
    body = "<table><tbody>" + "".join(rows) + "</tbody></table>"
    return _section("Встречи дня", body, "green")


def _briefs_kp_section(items: list[dict[str, Any]], raw, users) -> str:
    raw_index = {
        ("brief", int(item["id"])): item for item in raw.get("briefs", []) if item.get("id") is not None
    }
    raw_index.update(
        {("kp", int(item["id"])): item for item in raw.get("kp", []) if item.get("id") is not None}
    )
    rows = []
    for item in items:
        raw_item = raw_index.get((item["item_type"], item["item_id"]), {})
        title = raw_item.get("title") or f"{item['item_type']} {item['item_id']}"
        url = brief_url(item["item_id"]) if item["item_type"] == "brief" else kp_url(item["item_id"])
        rows.append(
            "<tr>"
            f"<td>{a(url, title)}</td>"
            f"<td>{html.escape(item['item_type'])}</td>"
            f"<td>{html.escape(manager_name(users, item.get('manager_id')))}</td>"
            f"<td>{_money(item.get('amount'))}</td>"
            "</tr>"
        )
    body = "<table><tbody>" + "".join(rows) + "</tbody></table>"
    return _section("Брифы и КП дня", body, "green")


def _rejections_section(rejections: list[dict[str, Any]]) -> str:
    rows = []
    for item in rejections:
        rows.append(
            "<tr>"
            f"<td>{a(deal_url(item['deal_id']), item['title'])}</td>"
            f"<td>{html.escape(str(item.get('manager') or ''))}</td>"
            f"<td>{html.escape(str(item.get('stage') or ''))}</td>"
            f"<td>{html.escape(str(item.get('reason') or ''))}</td>"
            "</tr>"
        )
    body = "<table><tbody>" + "".join(rows) + "</tbody></table>" if rows else "<p>Отказов дня нет.</p>"
    return _section("Отказы дня", body, "red")


def _tech_debt_section() -> str:
    body = (
        "<ul>"
        "<li>Официальная сводка «Опер» недоступна: Тигр дня рассчитан по телефонии.</li>"
        "<li>Содержательный LLM-разбор встреч не запускался: это граница Фазы 3.</li>"
        "<li>Локально не применялась миграция Postgres: БД поднимается на VPS.</li>"
        "</ul>"
    )
    return _section("Технический долг / ограничения", body, "amber")


def _money(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,.0f} ₽".replace(",", " ")
