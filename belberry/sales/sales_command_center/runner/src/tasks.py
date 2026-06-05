"""Создание задач Bitrix24 из следующих шагов разбора встреч.

Каждый следующий шаг (next_step из analysis_json) → задача в сделке:
- постановщик/контролёр = Управляющий партнёр (CREATED_BY, по умолчанию 12 / Щемелёв),
- исполнитель = ответственный за сделку,
- срок = парсинг свободного текста дедлайна в дату (МСК),
- TASK_CONTROL=Y → после выполнения задача уходит «на контроль» постановщику;
  как только он принял — задача завершена (и пропадает из дашборда).

Live-запись в Bitrix делает create_task(); build_* — чистые функции (тестируемы).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

DEFAULT_CREATOR_ID = 12  # Щемелёв Евгений, Управляющий партнёр
PORTAL = "https://belberrycrm.bitrix24.ru"
DEADLINE_HOUR = 15  # дедлайн ставим на 15:00 МСК
# Операционные обещания (отправить почту/кейсы/материалы) и нераспознанный срок —
# на следующий рабочий день. Договорённости с конкретной датой → на эту дату (15:00).
# Классификация «операционное vs запланированное» — в LLM next_steps[] (Phase 2).
FALLBACK_BUSINESS_DAYS = 1  # если срок не распознан → следующий рабочий день

_WEEKDAYS = {
    "понедельник": 0, "пн": 0,
    "вторник": 1, "вт": 1,
    "сред": 2, "ср": 2,
    "четверг": 3, "чт": 3,
    "пятниц": 4, "пт": 4,
    "суббот": 5, "сб": 5,
    "воскрес": 6, "вс": 6,
}


def _add_business_days(start: date, days: int) -> date:
    d = start
    added = 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5:  # пн-пт
            added += 1
    return d


def parse_deadline(text: str | None, base: date) -> tuple[date, bool]:
    """Свободный текст дедлайна → (дата, распознан ли). base — дата встречи.
    Если не распознан — base + FALLBACK_BUSINESS_DAYS рабочих дней, recognized=False."""
    t = (text or "").strip().lower()
    if not t:
        return _add_business_days(base, FALLBACK_BUSINESS_DAYS), False

    if "послезавтра" in t:
        return base + timedelta(days=2), True
    if "завтра" in t:
        return base + timedelta(days=1), True

    # «через N дней» / «через N-M дней» (берём верхнюю границу)
    m = re.search(r"через\s+(\d+)\s*[-–—]\s*(\d+)\s*(дн|день|дня|дней)", t)
    if m:
        return base + timedelta(days=int(m.group(2))), True
    m = re.search(r"через\s+(\d+)\s*(дн|день|дня|дней)", t)
    if m:
        return base + timedelta(days=int(m.group(1))), True

    # дни недели — РАНЬШЕ общей проверки «недел», иначе «на следующей неделе» ловится как +7.
    # Берём ближайший упомянутый день недели; «на следующей неделе» сдвигает на неделю вперёд.
    next_week = "следующ" in t
    days_to_sunday = 6 - base.weekday()
    best: int | None = None
    for name, wd in _WEEKDAYS.items():
        if re.search(rf"\b{name}", t):
            ahead = (wd - base.weekday()) % 7
            if ahead == 0:
                ahead = 7
            # «на следующей неделе» сдвигает только если ближайший день — ещё в текущей неделе
            if next_week and ahead <= days_to_sunday:
                ahead += 7
            best = ahead if best is None else min(best, ahead)
    if best is not None:
        return base + timedelta(days=best), True

    # недели (без явного дня недели)
    if re.search(r"(две|2)\s+недел", t):
        return base + timedelta(days=14), True
    if "недел" in t:  # «через неделю», «недельку», «в течение недели»
        return base + timedelta(days=7), True

    return _add_business_days(base, FALLBACK_BUSINESS_DAYS), False


def _deadline_iso(d: date) -> str:
    return datetime(d.year, d.month, d.day, DEADLINE_HOUR, 0, 0).strftime("%Y-%m-%dT%H:%M:%S") + "+03:00"


def _short(text: Any, limit: int = 400) -> str:
    s = str(text or "").strip()
    return s[: limit - 1] + "…" if len(s) > limit else s


def build_description(deal_id: int, deal_title: str | None, analysis: dict[str, Any], step: dict[str, Any], deadline_text: str | None) -> str:
    """Полный контекст в описании задачи."""
    lines = [
        f"Что сделать: {_short(step.get('what'), 600)}",
        "",
        f"Сделка: {deal_title or f'#{deal_id}'} — {PORTAL}/crm/deal/details/{deal_id}/",
    ]
    mt = analysis.get("meeting_type")
    mt_label = {"briefing": "первичная встреча", "defense": "защита КП"}.get(str(mt), "встреча")
    score = analysis.get("score")
    lines.append(f"Встреча: {mt_label}" + (f", оценка {score}/10" if score else ""))
    if step.get("who"):
        lines.append(f"Ответственный по договорённости: {_short(step.get('who'), 120)}")
    if deadline_text:
        lines.append(f"Срок по договорённости (из разговора): «{_short(deadline_text, 120)}»")
    if analysis.get("verdict"):
        lines += ["", f"Итог встречи: {_short(analysis.get('verdict'), 600)}"]
    if analysis.get("client_quote"):
        lines += ["", f"Цитата клиента: «{_short(analysis.get('client_quote'), 300)}»"]
    if analysis.get("systemic_conclusion"):
        lines += ["", f"Системный вывод: {_short(analysis.get('systemic_conclusion'), 500)}"]
    lines += ["", "— Поставлено автоматически из разбора встречи (Командный центр продаж)."]
    return "\n".join(lines)


def build_task_fields(
    *,
    deal_id: int,
    deal_title: str | None,
    responsible_id: int,
    step: dict[str, Any],
    analysis: dict[str, Any],
    base_date: date,
    creator_id: int = DEFAULT_CREATOR_ID,
) -> dict[str, Any]:
    """Поля для tasks.task.add. TASK_CONTROL=Y → задача требует принятия постановщиком."""
    deadline_text = step.get("deadline")
    deadline, _recognized = parse_deadline(deadline_text, base_date)
    what = _short(step.get("what"), 90) or "Следующий шаг по сделке"
    title = f"{deal_title or f'Сделка #{deal_id}'}: {what}"
    return {
        "TITLE": _short(title, 250),
        "DESCRIPTION": build_description(deal_id, deal_title, analysis, step, deadline_text),
        "RESPONSIBLE_ID": int(responsible_id),
        "CREATED_BY": int(creator_id),
        "DEADLINE": _deadline_iso(deadline),
        "UF_CRM_TASK": [f"D_{deal_id}"],
        "TASK_CONTROL": "Y",
        "ALLOW_CHANGE_DEADLINE": "N",
        "GROUP_ID": 0,
    }


def create_task(bx, fields: dict[str, Any]) -> int:
    """Создаёт задачу в Bitrix, возвращает её id. Бросает при ошибке API."""
    r = bx.call("tasks.task.add", {"fields": fields})
    task = (r or {}).get("result", {}).get("task", {})
    tid = task.get("id") or task.get("ID")
    if not tid:
        raise RuntimeError(f"tasks.task.add без id: {str(r)[:300]}")
    return int(tid)


def task_url(task_id: int) -> str:
    return f"{PORTAL}/company/personal/user/{DEFAULT_CREATOR_ID}/tasks/task/view/{task_id}/"
