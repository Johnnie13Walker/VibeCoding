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

import hashlib
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


# Формирование КП ставится автозадачей при переходе сделки на стадию КП — НЕ дублируем.
# «Отправить/защитить/презентовать КП» — это нормальные действия, их оставляем.
_KP_FORM_RE = re.compile(r"(подготов|сформир|состав|формир|готов|сдела|написа|разраб)\w*\s+(кп|коммерческ|предложен)", re.I)
_KP_KEEP_RE = re.compile(r"(отправ|защит|презент|выслать|показа|обсуд|согласова)", re.I)


def is_kp_formation(what: str | None) -> bool:
    t = str(what or "")
    if _KP_KEEP_RE.search(t):
        return False
    return bool(_KP_FORM_RE.search(t))


def actionable_steps(steps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Отбираем шаги под автозадачи: убираем формирование КП (стадийная автозадача).
    Уже выполненные шаги отсекает LLM на этапе разбора (next_steps)."""
    out = []
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        if not str(s.get("what") or "").strip():
            continue
        if is_kp_formation(s.get("what")):
            continue
        out.append(s)
    return out


# ── Семантический дедуп: канон действия (глагол+объект), а не точный текст ──
# Корень дублей 08.06: повторный разбор переформулировал шаги, а step_key (sha1
# точного текста) их не склеил. Канон сводит однотипные действия к одной задаче:
# все «отправить …» = одна, все «получить ответ/доступ/данные от клиента» = одна и т.д.
# Порядок важен — первое совпадение выигрывает.
MAX_TASKS_PER_MEETING = 3  # хард-кап старой логики next_steps (фолбэк)
MAX_PLANNED = 2  # хард-кап умного прохода (планировщик и так отдаёт ≤2; это бэкстоп)

_ACTION_RULES = [
    ("send", re.compile(r"отправ|выслать|направи|перешл|скинуть|презентова|показать", re.I)),
    ("await", re.compile(r"получ|дожда|запрос|обратн\w+\s+связ|доступ", re.I)),
    ("internal", re.compile(r"оцен|проанализир|\bанализ|рассчит|расч[её]т|проверить|собрать", re.I)),
    ("discuss", re.compile(r"обсуд|согласова|защит|созвон|встреч|презентац|договор|связаться", re.I)),
]


def canonical_action(what: str | None) -> str:
    """Канон действия для дедупа — по САМОМУ РАННЕМУ глаголу в тексте (ведущее действие,
    а не порядок правил: «Обсудить … после оценки» → discuss, не internal). Неизвестное
    → other:<точный ключ> (не сливаем разные)."""
    t = str(what or "").lower()
    best: tuple[int, str] | None = None
    for name, rx in _ACTION_RULES:
        m = rx.search(t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else "other:" + step_key(what)


def dedupe_steps(
    steps: list[dict[str, Any]],
    existing_actions: set[str] | None = None,
    cap: int = MAX_TASKS_PER_MEETING,
) -> list[dict[str, Any]]:
    """Склеивает однотипные шаги по канону, отбрасывает уже созданные (existing_actions
    — каноны задач, которые по встрече уже стоят: защита от повторного разбора), режет
    до cap. Сохраняет порядок — оставляем первое вхождение каждого канона."""
    skip = set(existing_actions or ())
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for s in steps:
        ca = canonical_action(s.get("what"))
        if ca in skip or ca in seen:
            continue
        seen.add(ca)
        out.append(s)
        if len(out) >= cap:
            break
    return out


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
    owner = step.get("owner") or step.get("who")
    if owner:
        lines.append(f"Ответственный по договорённости: {_short(owner, 120)}")
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
    # Операционные обещания → следующий рабочий день (даже если на словах «через неделю»).
    # Запланированные/легаси → парсим дату из формулировки.
    if step.get("kind") == "operational":
        deadline = _add_business_days(base_date, FALLBACK_BUSINESS_DAYS)
    else:
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


def build_description_plan(deal_id: int, deal_title: str | None, analysis: dict[str, Any], item: dict[str, Any]) -> str:
    """Описание задачи из плана планировщика: что + зачем + контекст встречи."""
    lines = [f"Что сделать: {_short(item.get('title'), 600)}"]
    if item.get("rationale"):
        lines += ["", f"Зачем: {_short(item.get('rationale'), 400)}"]
    lines += ["", f"Сделка: {deal_title or f'#{deal_id}'} — {PORTAL}/crm/deal/details/{deal_id}/"]
    mt = analysis.get("meeting_type")
    mt_label = {"briefing": "первичная встреча", "defense": "защита КП"}.get(str(mt), "встреча")
    score = analysis.get("score")
    lines.append(f"Встреча: {mt_label}" + (f", оценка {score}/10" if score else ""))
    if item.get("deadline"):
        lines.append(f"Срок по договорённости (из разговора): «{_short(item.get('deadline'), 120)}»")
    if str(item.get("owner")) == "internal":
        lines.append("Исполнение: внутреннее (продакшн/отдел), не на стороне клиента.")
    if analysis.get("verdict"):
        lines += ["", f"Итог встречи: {_short(analysis.get('verdict'), 600)}"]
    if analysis.get("client_quote"):
        lines += ["", f"Цитата клиента: «{_short(analysis.get('client_quote'), 300)}»"]
    lines += ["", "— Поставлено автоматически из разбора встречи (Командный центр продаж)."]
    return "\n".join(lines)


def build_task_fields_from_plan(
    *,
    deal_id: int,
    deal_title: str | None,
    responsible_id: int,
    item: dict[str, Any],
    analysis: dict[str, Any],
    base_date: date,
    creator_id: int = DEFAULT_CREATOR_ID,
) -> dict[str, Any]:
    """Поля tasks.task.add из задачи планировщика. Контроль — только если item.control;
    срок — парсинг короткой формулировки планировщика (иначе следующий рабочий день)."""
    deadline, _recognized = parse_deadline(item.get("deadline"), base_date)
    title = _short(item.get("title") or "Следующий шаг по сделке", 120)
    full_title = f"{deal_title or f'Сделка #{deal_id}'}: {title}"
    return {
        "TITLE": _short(full_title, 250),
        "DESCRIPTION": build_description_plan(deal_id, deal_title, analysis, item),
        "RESPONSIBLE_ID": int(responsible_id),
        "CREATED_BY": int(creator_id),
        "DEADLINE": _deadline_iso(deadline),
        "UF_CRM_TASK": [f"D_{deal_id}"],
        "TASK_CONTROL": "Y" if item.get("control") else "N",
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


# ── Идемпотентность: храним созданные задачи в meeting_tasks (migration 0009) ──

def step_key(what: str | None) -> str:
    """Стабильный ключ шага для дедупликации: нормализованный текст → sha1[:20]."""
    norm = re.sub(r"\s+", " ", str(what or "").strip().lower())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:20]


def _steps_for_meeting(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """next_steps[] (атомарные, без формирования КП); fallback на единичный next_step."""
    steps = analysis.get("next_steps")
    if isinstance(steps, list) and steps:
        return actionable_steps(steps)
    ns = analysis.get("next_step")
    if isinstance(ns, dict) and str(ns.get("what") or "").strip() and not is_kp_formation(ns.get("what")):
        return [ns]
    return []


def _load_day_meetings(conn, target: date, meeting_id: int | None = None):
    q = (
        "SELECT m.meeting_id, m.deal_id, m.manager_id, m.analysis_json, d.title, d.stage "
        "FROM meetings m LEFT JOIN deals_snapshot d "
        "ON d.report_date=m.report_date AND d.deal_id=m.deal_id "
        "WHERE m.report_date=%s AND m.analysis_json IS NOT NULL"
    )
    params: list[Any] = [target.isoformat()]
    if meeting_id:
        q += " AND m.meeting_id=%s"
        params.append(meeting_id)
    with conn.cursor() as cur:
        cur.execute(q, tuple(params))
        return cur.fetchall()


def _plan_for_meeting(analysis, deal_title, stage, client):
    """Планировщик-проход. None при ошибке (→ фолбэк на старую логику next_steps);
    список (возможно пустой) — если планировщик отработал."""
    from . import task_planner

    try:
        return task_planner.plan_tasks(analysis, deal_title=deal_title, stage=stage, client=client)
    except Exception:  # noqa: BLE001
        return None


def create_tasks_for_day(conn, bx, target: date, *, creator_id: int = DEFAULT_CREATOR_ID, meeting_id: int | None = None, dry_run: bool = False, client=None) -> list[dict[str, Any]]:
    """Создаёт задачи Bitrix по итогам встреч за день. Идемпотентно (meeting_tasks.step_key
    + семантический канон). dry_run=True — только собрать план, без записи в Bitrix/БД.

    client задан → умный проход: планировщик (≤2 рычажных задачи, человеческий заголовок,
    срок/контроль) → канон-дедуп → постановка. client=None или ошибка планировщика →
    старая логика next_steps (фолбэк). Возвращает список результатов."""
    import json as _json

    results: list[dict[str, Any]] = []
    for meeting_id_, deal_id, manager_id, analysis_json, deal_title, stage in _load_day_meetings(conn, target, meeting_id):
        if not deal_id or not manager_id:
            continue
        analysis = analysis_json if isinstance(analysis_json, dict) else _json.loads(analysis_json or "{}")

        plan = _plan_for_meeting(analysis, deal_title, stage, client) if client is not None else None
        planner_used = plan is not None
        if planner_used:
            # каждый план-айтем несёт what=title — чтобы общий дедуп/идемпотентность работали
            candidates = [{**t, "what": t.get("title")} for t in plan]
            cap = MAX_PLANNED
        else:
            candidates = _steps_for_meeting(analysis)
            cap = MAX_TASKS_PER_MEETING
        if not candidates:
            continue

        done_keys = set() if dry_run else existing_step_keys(conn, meeting_id_)
        prior_actions = set() if dry_run else existing_actions(conn, meeting_id_)
        candidates = dedupe_steps(candidates, existing_actions=prior_actions, cap=cap)

        for cand in candidates:
            sk = step_key(cand.get("what"))
            entry = {"meeting_id": meeting_id_, "deal_id": deal_id, "what": cand.get("what"), "step_key": sk, "source": "planner" if planner_used else "legacy"}
            if sk in done_keys:
                entry["status"] = "skip_exists"
                results.append(entry)
                continue
            if planner_used:
                fields = build_task_fields_from_plan(
                    deal_id=deal_id, deal_title=deal_title, responsible_id=manager_id,
                    item=cand, analysis=analysis, base_date=target, creator_id=creator_id,
                )
            else:
                fields = build_task_fields(
                    deal_id=deal_id, deal_title=deal_title, responsible_id=manager_id,
                    step=cand, analysis=analysis, base_date=target, creator_id=creator_id,
                )
            entry["fields"] = fields
            if dry_run:
                entry["status"] = "planned"
                results.append(entry)
                continue
            tid = create_task(bx, fields)
            record_task(
                conn, report_date=target.isoformat(), meeting_id=meeting_id_, deal_id=deal_id,
                step_key=sk, task_id=tid, responsible_id=manager_id, title=fields["TITLE"], deadline=fields["DEADLINE"],
            )
            conn.commit()
            done_keys.add(sk)
            entry["status"] = "created"
            entry["task_id"] = tid
            results.append(entry)
    return results


# Статусы Bitrix-задач: 2 ждёт выполнения, 3 выполняется, 4 ждёт контроля,
# 5 завершена, 6 отложена, 7 отклонена. Закрываем (скрываем из дашборда) при 5/7.
CLOSED_STATUSES = {5, 7}


def sync_task_statuses(conn, bx, limit: int = 300) -> int:
    """Синкает статус/дедлайн открытых задач из Bitrix в meeting_tasks.
    closed=true при завершении/отклонении (или если задача удалена в Bitrix)."""
    with conn.cursor() as cur:
        cur.execute("SELECT task_id FROM meeting_tasks WHERE closed=false ORDER BY id LIMIT %s", (limit,))
        ids = [row[0] for row in cur.fetchall()]
    if not ids:
        return 0
    r = bx.call("tasks.task.list", {"filter": {"ID": ids}, "select": ["ID", "STATUS", "DEADLINE"]})
    items = (r or {}).get("result", {}).get("tasks", []) or []
    found: dict[int, dict] = {}
    for t in items:
        tid = t.get("id") or t.get("ID")
        if tid is not None:
            found[int(tid)] = t
    updated = 0
    with conn.cursor() as cur:
        for tid in ids:
            t = found.get(tid)
            if t is None:  # задача удалена в Bitrix → закрываем
                cur.execute("UPDATE meeting_tasks SET closed=true, updated_at=now() WHERE task_id=%s", (tid,))
                updated += 1
                continue
            try:
                status = int(t.get("status") or t.get("STATUS") or 0)
            except (TypeError, ValueError):
                status = 0
            deadline = t.get("deadline") or t.get("DEADLINE") or None
            cur.execute(
                "UPDATE meeting_tasks SET status=%s, deadline=COALESCE(%s, deadline), closed=%s, updated_at=now() WHERE task_id=%s",
                (status, deadline, status in CLOSED_STATUSES, tid),
            )
            updated += 1
    conn.commit()
    return updated


def existing_step_keys(conn, meeting_id: int) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT step_key FROM meeting_tasks WHERE meeting_id=%s", (int(meeting_id),))
        return {row[0] for row in cur.fetchall()}


def existing_actions(conn, meeting_id: int) -> set[str]:
    """Каноны действий уже созданных по встрече задач (для межпрогонного дедупа).
    Текст шага восстанавливаем из TITLE «{сделка}: {что}» — отрезаем префикс сделки."""
    with conn.cursor() as cur:
        cur.execute("SELECT title FROM meeting_tasks WHERE meeting_id=%s", (int(meeting_id),))
        out: set[str] = set()
        for (title,) in cur.fetchall():
            what = title.split(": ", 1)[1] if title and ": " in title else (title or "")
            out.add(canonical_action(what))
        return out


def record_task(conn, *, report_date, meeting_id, deal_id, step_key, task_id, responsible_id, title, deadline) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meeting_tasks
              (report_date, meeting_id, deal_id, step_key, task_id, responsible_id, title, deadline, status, closed, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (meeting_id, step_key) DO NOTHING
            """,
            (report_date, int(meeting_id), deal_id, step_key, int(task_id), responsible_id, title, deadline, 2, False),
        )
