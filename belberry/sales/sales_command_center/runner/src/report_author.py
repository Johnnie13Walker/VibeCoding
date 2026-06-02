"""LLM-автор отчёта (архитектура B).

Финальный HTML-отчёт пишет модель из собранных за день данных, используя
report.css как дизайн-контракт. Детерминированный render.py остаётся
fallback-скелетом на случай сбоя/невалидного ответа LLM.

Поток: build_payload(rows, extras) → author_report(payload, client) → HTML-тело
(внутренний HTML body) | None. Затем daily_runner: substitute_photos → wrap в
полный документ с CSS; при None — fallback на render.report_report.
"""

import html
import json
import os
import re
from datetime import date
from typing import Any

from . import analyze_llm

PORTAL_BASE = "https://belberrycrm.bitrix24.ru"

WEEKDAYS_RU = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]
MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

SYSTEM_PROMPT = """
Ты — аналитик отдела продаж агентства Belberry. Пишешь ежедневный HTML-отчёт
«Сводка отдела продаж» за прошлый рабочий день для руководителя и РОПа.
Отвечай ТОЛЬКО внутренним HTML тела документа (без <html>, <head>, <style>,
<body>, без markdown и без ``` ). Весь текст — на русском.

ЖЁСТКИЕ ПРАВИЛА:
- Используй ТОЛЬКО данные из payload. НЕ выдумывай имена, сделки, цифры, цитаты.
  Если данных нет — пиши честно «нет данных» или опускай блок.
- Имена сотрудников — «Фамилия Имя» из payload.users, НИКОГДА не id.
- Каждую упомянутую сущность оформляй гиперссылкой на её TITLE/домен:
  сделка → {base}/crm/deal/details/{id}/ ;
  встреча/КП/бриф (смарт-процесс) → {base}/crm/type/{entityTypeId}/details/{id}/ .
- Разбор встреч — глубокий, по чек-листу (брифинг: диалог-не-анкета, потребность,
  кейсы, БЮДЖЕТ, след.шаг; защита КП: кейсы обязательно, аргументация цифр,
  запрос след.шагов от клиента, итоги клиенту). Каждый пункт — ✅/⚠️/❌ + краткая
  заметка. Не верь статусу Bitrix слепо: лови расхождение «статус успех vs суть
  не закрыта». Добавляй дословную цитату клиента из транскрипта (если есть).
- Тон — деловой, конкретный, без воды. Опирайся на цифры и ссылки.
- Фото: <img class="tiger-photo" src="photo:BITRIXID" alt="Имя"> для Тигра и
  <img class="mgr-ava" src="photo:BITRIXID" alt=""> для менеджеров — подставим сами.
- Сумма по встрече в «рисках» — `meetings[].deal_opportunity` (и ссылка на сделку
  `deal_id`, а не только на встречу); если оно null — «нет данных».
- Причина отказа — `rejections[].reason_label` (НЕ код семантики).
- Запрещено: <script>, on*-атрибуты, внешние src (кроме src="photo:ID").

ДИЗАЙН-КОНТРАКТ (используй ровно эти классы из report.css):

Шапка (открывает тело):
<div class="hero"><div class="wrap">
  <div class="hero-label">Сводка отдела продаж · отчёт за вчера</div>
  <h1>{Деньнедели, D месяца YYYY}</h1>
  <div class="hero-subtitle">Связный абзац-резюме дня со ссылками на сделки/встречи.</div>
  <div class="stats">
    <div class="stat accent-green"><div class="stat-value">4</div><div class="stat-label">Встречи проведены</div><div class="stat-sub">разбивка/детали со ссылками</div></div>
    … 6-8 карточек, accent: green|blue|amber|red …
  </div>
  <div class="hero-verdict">⚠️ <b>Итог за ночь:</b> главный риск дня со ссылками.</div>
  <div class="hero-corr">Источник данных и оговорки.</div>
</div></div>

Дальше каждая секция:
<div class="wrap"><section [class="tinted-green|tinted-amber|tinted-red"]>
  <div class="section-head"><div class="section-icon blue|green|amber|red|purple">30s</div><h2>Заголовок</h2></div>
  …тело секции…
</section></div>

Секции по порядку (опускай те, где нет данных):
1. «Главное за 30 секунд» — <div class="cards-3"> три карточки:
   <div class="card-30 c-red"><div class="c30-title">🔥 Горит сегодня</div><ul><li>…</li></ul></div>
   <div class="card-30 c-amber"><div class="c30-title">💰 Денег под риском</div><div class="c30-big">&gt; X млн ₽</div><p>…</p></div>
   <div class="card-30 c-amber"><div class="c30-title">🔧 Исправить системно</div><ul><li>…</li></ul></div>
2. «Тигр дня» (section tinted-green): <div class="tiger-wrap"><img class="tiger-photo" src="photo:ID" alt="Имя"><div class="tiger-body"><div class="tiger-name">Имя <span class="tiger-role">· роль</span></div><div class="tiger-quote">…</div><div class="tiger-metrics"><span class="tm-pill">89 наборов</span>…</div><div class="tiger-note">оговорка</div></div></div>
3. «Кого пинать сегодня» — <ul> или карточки с действиями и ссылками.
4. «Где могут сорваться сделки» (tinted-amber) — <div class="tbl-wrap"><table>…</table></div>, статусы через <span class="badge b-red|b-amber|b-blue|b-green">…</span>.
5. «Зависшие сделки по стадиям» (tinted-red) — таблица с badge по сумме/возрасту.
6. «Активность менеджеров» — карточки:
   <div class="mgr hero-mgr"><img class="mgr-ava" src="photo:ID"><div class="mgr-name">Имя</div><div class="mgr-role">роль</div><div class="mgr-row"><span class="mgr-row-label">Наборы</span><span class="mgr-row-value">89</span></div>…</div>
7. «Встречи дня» — кратко: что проведено, со ссылками.
8. «Содержательный разбор встреч» — по каждой встрече с транскриптом:
   <div class="razbor-card"><div class="razbor-head"><h3>домен — тип</h3><div class="razbor-score">7/10</div></div><div class="razbor-sum">резюме</div><div class="checks"><div class="chk-row"><span class="chk-mark">✅</span><span class="chk-label">Кейсы</span><span class="chk-txt">…</span></div>…</div><div class="razbor-verdict">вердикт</div><div class="razbor-good">Что хорошо: …</div></div>
9. «Брифы и КП дня» — список со ссылками.
10. «Отказы дня» — содержательные отказы с причиной и суммой.
11. «Системные паттерны» — <div class="cards-2"> карточки card-pat (что работает / что повторяется).
12. «Итог дня» — короткий вывод.
13. «Технические ограничения отчёта» — оговорки по данным.
В конце: <div class="footer"><p>…</p></div>.
""".strip()


def _ru_date(report_date: str) -> str:
    try:
        d = date.fromisoformat(report_date)
    except (ValueError, TypeError):
        return str(report_date)
    return f"{WEEKDAYS_RU[d.weekday()]}, {d.day} {MONTHS_RU[d.month - 1]} {d.year}"


_REJECTION_LABELS = {
    "C10:LOSE": "Отказ (воронка Продажи)",
    "C50:APOLOGY": "Отвал (телемаркетинг)",
}


def _deal_opportunity_map(raw: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for d in [*(raw.get("deals_open") or []), *(raw.get("deals_created") or [])]:
        did = str(d.get("ID"))
        if not did or did == "None":
            continue
        try:
            out[did] = float(d.get("OPPORTUNITY") or 0)
        except (TypeError, ValueError):
            continue
    return out


def build_payload(rows: dict[str, Any], extras: dict[str, Any]) -> dict[str, Any]:
    """Компактный структурированный срез дня для LLM-автора."""
    users = extras.get("users") or {}
    raw = extras.get("raw") or {}
    analyses = extras.get("analyses") or {}
    deal_opp = _deal_opportunity_map(raw)

    meetings = []
    for m in rows.get("meetings", []) or []:
        mid = m.get("meeting_id")
        deal_id = m.get("deal_id")
        meetings.append(
            {
                "id": mid,
                "entityTypeId": 1048,
                "title": m.get("title") or raw_title(raw, mid),
                "type": m.get("meeting_type"),
                "status": m.get("status"),
                "manager": users.get(str(m.get("manager_id")), m.get("manager_id")),
                # связанная сделка + её сумма — чтобы у встречи в «рисках» была сумма,
                # а не «нет данных», и чтобы ссылаться на сделку, а не только на встречу.
                "deal_id": deal_id,
                "deal_opportunity": deal_opp.get(str(deal_id)),
                "analysis": analyses.get(mid) or analyses.get(int(mid)) if mid is not None else None,
            }
        )

    rejections = []
    for r in extras.get("rejections") or []:
        item = dict(r)
        # человекочитаемая причина вместо кода семантики (F): детального loss-reason
        # в stagehistory нет — даём метку по стадии, без «кода F».
        item["reason_label"] = _REJECTION_LABELS.get(r.get("stage"), "Отказ")
        rejections.append(item)

    return {
        "report_date": extras.get("report_date") or raw.get("report_date"),
        "weekday_date_ru": _ru_date(extras.get("report_date") or raw.get("report_date") or ""),
        "portal_base": PORTAL_BASE,
        "link_patterns": {
            "deal": f"{PORTAL_BASE}/crm/deal/details/{{id}}/",
            "smart_process": f"{PORTAL_BASE}/crm/type/{{entityTypeId}}/details/{{id}}/",
        },
        "users": users,
        "stats": _stats(rows, extras),
        "stale": extras.get("stale") or {},
        "rejections": rejections,
        "manager_activity": rows.get("manager_activity", []),
        "meetings": meetings,
        "kp_briefs": rows.get("kp_briefs", []),
        "deals_created": raw.get("deals_created", []),
        "telephony": _telephony(rows, users),
    }


def raw_title(raw: dict[str, Any], mid: Any) -> Any:
    for item in raw.get("meet_day", []) or []:
        if str(item.get("id")) == str(mid):
            return item.get("title")
    return mid


def _stats(rows: dict[str, Any], extras: dict[str, Any]) -> dict[str, Any]:
    stale = extras.get("stale") or {}
    return {
        "meetings": len(rows.get("meetings", []) or []),
        "kp_briefs": len(rows.get("kp_briefs", []) or []),
        "deals_created": len((extras.get("raw") or {}).get("deals_created", []) or []),
        "stale_total": sum(len(v) for v in stale.values()),
        "rejections": len(extras.get("rejections") or []),
        "calls_total": sum(i.get("dials_total", 0) for i in rows.get("manager_activity", []) or []),
    }


def _telephony(rows: dict[str, Any], users: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in rows.get("manager_activity", []) or []:
        out.append(
            {
                "manager": users.get(str(item.get("manager_id")), item.get("manager_id")),
                "dials_total": item.get("dials_total", 0),
                "calls_answered": item.get("calls_answered", 0),
                "calls_120s_plus": item.get("calls_120s_plus", 0),
            }
        )
    return out


_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.S)


def _strip_fence(text: str) -> str:
    return _FENCE.sub("", text.strip()).strip()


def _validate(body: str) -> bool:
    if not body or len(body) < 400:
        return False
    low = body.lower()
    if "<script" in low or "javascript:" in low:
        return False
    return 'class="hero"' in body or "<section" in body


def author_report(payload: dict[str, Any], *, client, model: str | None = None) -> str | None:
    """Просит LLM написать тело отчёта. Возвращает HTML-тело или None при сбое."""
    user_message = "\n\n".join(
        [
            "Данные за день (payload). Пиши отчёт строго по ним:",
            json.dumps(payload, ensure_ascii=False, default=str),
        ]
    )
    max_tokens = int(os.environ.get("SCC_AUTHOR_MAX_TOKENS", "16000"))
    try:
        response = analyze_llm._call_with_retry(
            client,
            model=model or analyze_llm.MODEL,
            max_tokens=max_tokens,
            temperature=0.3,
            system=analyze_llm._system(SYSTEM_PROMPT),
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[author] LLM call failed: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        return None
    body = _strip_fence(analyze_llm._response_text(response))
    if _validate(body):
        return body
    has_hero = 'class="hero"' in body
    print(
        f"[author] invalid body: len={len(body)} has_hero={has_hero} "
        f"has_section={'<section' in body} head={body[:150]!r}",
        flush=True,
    )
    return None


def substitute_photos(body_html: str, photos: dict[str, str]) -> str:
    """Заменяет src="photo:ID" на data-URI из собранных фото; иначе убирает src."""
    photos = photos or {}

    def repl(match: re.Match) -> str:
        uid = match.group(1)
        data = photos.get(str(uid))
        return f'src="{data}"' if data else 'src="" data-no-photo="1"'

    return re.sub(r'src="photo:([^"]+)"', repl, body_html)


def wrap_document(body_html: str, css: str, report_date: Any) -> str:
    safe_date = html.escape(str(report_date))
    return (
        '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>Сводка продаж {safe_date}</title>"
        f"<style>{css}</style></head><body>{body_html}</body></html>"
    )
