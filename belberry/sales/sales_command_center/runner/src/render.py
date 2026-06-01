import html
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
        _section("Главное за 30 секунд", llm_placeholder(), "red"),
        _tiger_section(tiger, photos),
        _section("Кого пинать сегодня", llm_placeholder(), "red"),
        _risk_section(stale),
        _stale_section(stale),
        _activity_section(rows.get("manager_activity", []), users, photos),
        _meetings_section(rows.get("meetings", []), raw.get("meet_day", []), users),
        _section("Содержательный разбор встреч", llm_placeholder(), "purple"),
        _briefs_kp_section(rows.get("kp_briefs", []), raw, users),
        _rejections_section(rejections),
        _section("Системные паттерны", llm_placeholder(), "blue"),
        _section("Итог дня", llm_placeholder(), "green"),
        _tech_debt_section(),
        "</div></body></html>",
    ]
    return "\n".join(parts)


def _load_css() -> str:
    ref = Path("/tmp/sales_2905/style.css")
    if ref.exists():
        text = ref.read_text()
        return text.replace("<style>", "").replace("</style>", "")
    return "body{font-family:sans-serif}.data-llm-placeholder{color:#8a93a3}"


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


def _tiger_section(tiger: dict[str, Any] | None, photos: dict[Any, str]) -> str:
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
            f"{llm_placeholder()}</div></div>"
        )
    else:
        body = llm_placeholder()
    body += (
        '<p class="tiger-disclaimer">Рейтинг рассчитан по телефонии за день; '
        'официальная сводка «Опер» недоступна.</p>'
    )
    return _section("Тигр дня", body, "amber")


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
