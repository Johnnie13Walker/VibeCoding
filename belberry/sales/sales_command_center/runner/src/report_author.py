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

from collections import Counter

from . import analyze_llm, oper
from .deltas import delta_label
from .health import compute_health_score

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
- В отчёте — ТОЛЬКО отдел продаж и телемаркетинг. Других сотрудников (рекрутёр,
  аккаунт-менеджер, админ, HR, дизайн) НЕ упоминай ни в одном блоке.
- Имена сотрудников — «Фамилия Имя» из payload.users, НИКОГДА не id.
- Роль сотрудника бери из payload.user_roles[<его manager_id/uid>] (WORK_POSITION).
  Если роли там нет — НЕ пиши «роль: нет данных», а ПОЛНОСТЬЮ опусти роль
  (для tiger-role, mgr-role и строк таблицы «Кого пинать»).
- Каждую упомянутую сущность оформляй гиперссылкой на её TITLE/домен:
  сделка → {base}/crm/deal/details/{id}/ ;
  встреча/КП/бриф (смарт-процесс) → {base}/crm/type/{entityTypeId}/details/{id}/ .
- Разбор встреч — глубокий, по чек-листу (брифинг: диалог-не-анкета, потребность,
  кейсы, БЮДЖЕТ, след.шаг; защита КП: кейсы обязательно, аргументация цифр,
  запрос след.шагов от клиента, итоги клиенту). Каждый пункт — ✅/⚠️/❌ + краткая
  заметка. Не верь статусу Bitrix слепо: лови расхождение «статус успех vs суть
  не закрыта». Добавляй дословную цитату клиента из транскрипта (если есть).
- Тон — деловой, конкретный, без воды. Опирайся на цифры и ссылки.
- Фото: src="photo:<manager_id>", где manager_id — из manager_activity[].manager_id
  (НЕ имя!). Тигр: <img class="tiger-photo" src="photo:<manager_id>" alt="Имя">;
  менеджеры: <img class="mgr-ava" src="photo:<manager_id>" alt="">. Подставим сами.
- Сумма по встрече в «рисках» — `meetings[].deal_opportunity` (и ссылка на сделку
  `deal_id`, а не только на встречу); если оно null — «нет данных».
- Причина отказа — `rejections[].reason_label` (НЕ код семантики).
- Цитату дня бери из payload.quote_of_day; coaching-строки — из payload.manager_coaching.
- «Кого пинать» строится по payload.action_items: там уже есть владелец, дедлайн,
  срочность, сделка и причина. Не выдумывай новые задачи.
- Пробелы данных показывай только в подвале по payload.data_quality; не размазывай
  техпроблемы по телу отчёта.
- Запрещено: <script>, on*-атрибуты, внешние src (кроме src="photo:ID").

ДИЗАЙН-КОНТРАКТ (используй ровно эти классы из report.css):

Шапка (открывает тело):
<div class="hero"><div class="wrap">
  <div class="hero-label">Сводка отдела продаж · отчёт за вчера</div>
  <h1>{Деньнедели, D месяца YYYY}</h1>
  <div class="hero-subtitle">Связный абзац-резюме дня со ссылками на сделки/встречи.</div>
  <div class="hero-stats">
    <div class="hstat"><div class="hstat-num">7</div><div class="hstat-lbl">Встречи</div><div class="stat-sub">+75% к прошлому рабочему дню</div></div>
    … 5-7 плиток из payload.hero_stats …
  </div>
  <div class="hero-health health-green|health-amber|health-red" title="{payload.health_score.formula}">
    <div class="health-score">74</div><div><div class="health-label">здоровье дня</div><div class="health-note">Опер 82%, встречи 75%, факт 100%, штраф риска −8</div></div>
  </div>
  <nav class="anchor-nav">
    <a class="anchor-chip" href="#main">Главное</a><a class="anchor-chip" href="#tiger">Тигр</a><a class="anchor-chip" href="#meetings-done">Встречи</a><a class="anchor-chip" href="#meeting-analysis">Разбор</a><a class="anchor-chip" href="#risks">Риски</a>
  </nav>
  <div class="stats">
    <div class="stat accent-green"><div class="stat-value">4</div><div class="stat-label">Встречи проведены</div><div class="stat-sub">разбивка/детали со ссылками</div></div>
    … 6-8 карточек, accent: green|blue|amber|red …
  </div>
  <div class="hero-verdict"><span class="hv-icon">⚠️</span><b>Итог за ночь:</b> связный абзац-вывод со ссылками (НЕ список фрагментов).</div>
  <div class="hero-corr">Источник данных и оговорки.</div>
</div></div>

Дальше каждая секция:
<div class="wrap"><section [class="tinted-green|tinted-amber|tinted-red"]>
  <div class="section-head"><div class="section-icon blue|green|amber|red|purple">ЭМОДЗИ</div><h2>Заголовок</h2></div>
  В section-icon — ЭМОДЗИ (📞 🎯 🚫 🔁 ✅ 🔧 💰 🐅 📋 ⚠️), НЕ латинские буквы.
  …тело секции…
</section></div>
Цветовая семантика везде одна: green = выигрыш/хорошо, amber = риск/внимание, red = горит/срочно. Не используй purple/blue для статуса риска — только для нейтральных акцентов.
Каждой секции ставь id для якорей: main, tiger, action-items, risks, tm-funnel, managers, meetings-done, meetings-today, meeting-analysis. В карточках менеджеров добавляй id="manager-<manager_id>"; если разбор встречи связан с менеджером, можно ссылаться на этот якорь.

Секции по порядку (опускай те, где нет данных):
1. «Главное за 30 секунд» — section id="main"; <div class="cards-3"> три карточки:
   <div class="card-30 c-red"><div class="c30-title">🔥 Горит сегодня</div><ul><li>…</li></ul></div>
   <div class="card-30 c-amber"><div class="c30-title">💰 Денег под риском</div><div class="c30-big">&gt; X млн ₽</div><p>…</p></div>
   <div class="card-30 c-amber"><div class="c30-title">🔧 Исправить системно</div><ul><li>…</li></ul></div>
2. «Тигр дня» (section id="tiger" tinted-green) — менеджер с МАКС. operational_score («Опер»)
   из telephony (НЕ по числу наборов!): <div class="tiger-wrap"><img class="tiger-photo" src="photo:<manager_id>" alt="Имя"><div class="tiger-body"><div class="tiger-name">Имя <span class="tiger-role">· роль</span></div><div class="tiger-quote">…</div><div class="tiger-metrics"><span class="tm-pill">Опер 10.0</span><span class="tm-pill">28% конверсия</span><span class="tm-pill">89 наборов</span>…</div><div class="tiger-note">рейтинг по операционной оценке «Опер»; рядом: следующие по Опер</div></div></div>
   Если payload.quote_of_day.text есть — сразу после Тигра добавь блок:
   <div class="quote-day"><div class="quote-day-text">«дословная цитата»</div><div class="quote-day-meta">кто/сделка/контекст из payload.quote_of_day.meta</div></div>
   НЕ используй .ach-* классы, стрики или ачивки.
3. «Кого пинать сегодня» (section id="action-items") — ТАБЛИЦА (не список) по payload.action_items:
   <div class="tbl-wrap"><table><thead><tr><th>Владелец</th><th>Что сделать</th><th>Дедлайн</th><th>Сделка</th><th>Почему горит</th><th>Срочность</th></tr></thead><tbody>
   <tr><td>Фамилия Имя<br><span class="muted">роль</span></td><td>конкретное действие</td><td>сегодня 18:00</td><td><a href="...">домен</a></td><td>почему</td><td><span class="badge b-red">сейчас</span></td></tr>
   …</tbody></table></div>
   Срочность: <span class="badge b-red">сейчас</span> / <span class="badge b-amber">сегодня</span> / <span class="badge b-blue">на неделе</span>.
4. «Где могут сорваться сделки» (section id="risks" tinted-amber) — лид-абзац (сколько сделок превысили норму на стадии + ядро затора) + ТАБЛИЦА:
   <div class="tbl-wrap"><table><thead><tr><th>Сделка</th><th>Сумма</th><th>Менеджер</th><th>На стадии</th><th>Посл. контакт</th><th>Риск</th></tr></thead><tbody>
   <tr><td><a href="{deal-ссылка}">домен</a></td><td>304 тыс.</td><td>Фамилия Имя</td><td>31 раб.дн</td><td>1 дн назад</td><td><span class="badge b-red">высокий</span></td></tr>
   …топ-10 по сумме…</tbody></table></div>
   Риск: показывай stale[].risk_reason отдельным бейджем причины. Цвет возраста бери по stale[].age_level: critical — красный и текст «31 рабочий день!», warning — amber, normal — обычный. Сумма — из stale[].opportunity; возраст — age+age_unit; контакт — last_contact_days. Сделки ВСЕГДА кликабельны (deal-ссылка по id).
5. «ТМ-воронка» (section id="tm-funnel") — если payload.tm_funnel.count > 0, покажи компактную воронку телемаркетинга:
   наборы → дозвоны → 120с+ → встречи назначено → встречи проведено → сделки.
   Используй ТОЛЬКО payload.tm_funnel: реальные числа и проценты answered_percent, long_call_percent, meeting_set_percent, deal_create_percent. Не добавляй продукт/нишу и не делай новых выводов из Bitrix.
6. «Активность менеджеров» (section id="managers") — карточки, ОТСОРТИРОВАНЫ по «Опер» убыв. (порядок telephony):
   <div class="mgr hero-mgr"><img class="mgr-ava" src="photo:<manager_id>"><div class="mgr-name">Имя</div><div class="mgr-role">роль · Опер 10.0</div><div class="mgr-row"><span class="mgr-row-label">Наборы</span><span class="mgr-row-value">89</span></div><div class="mgr-row"><span class="mgr-row-label">Дозвоны</span><span class="mgr-row-value">40 (11%)</span></div><div class="mgr-row"><span class="mgr-row-label">120с+</span><span class="mgr-row-value">8</span></div><div class="mgr-row"><span class="mgr-row-label">Встречи</span><span class="mgr-row-value">0</span></div><div class="mgr-row"><span class="mgr-row-label">Опер</span><span class="mgr-row-value">10.0</span></div></div>
   Строки mgr-row: Наборы (dials_total), Дозвоны «40 (11%)» (calls_answered, connect_percent), 120с+ (calls_120s_plus), Чаты (messenger_dialogs), Часы (hours), Встречи (meetings_held), Новых сделок (new_deals), Опер (operational_score). Данные из telephony.
   Если для manager_id есть payload.manager_coaching[] — добавь в карточку <div class="mgr-note"><b>Коучинг:</b> конкретный совет; <span class="muted">основание</span></div>.
   Если away=true (поле telephony) — карточка <div class="mgr away">, строка «Заморожено сделок: frozen_deals». Если vacation_until НЕ пуст — роль «роль · в отпуске до {vacation_until}» (по графику Bitrix). Если vacation_until пуст — «роль · в простое» (нет активности; «в отпуске» НЕ писать без vacation_until).
7. «Встречи дня — проведено N» (section id="meetings-done") — СВОДНАЯ ТАБЛИЦА перед разбором:
   <div class="tbl-wrap"><table><thead><tr><th>Сделка/встреча</th><th>Тип</th><th>Проводит</th><th>Статус</th><th>Балл</th></tr></thead><tbody>
   <tr><td><a href="{встреча}">домен</a></td><td>Защита КП</td><td>Имя</td><td><span class="badge b-green">проведена</span></td><td><b>8/10</b></td></tr></tbody></table></div>
   Балл = meetings[].analysis.score (X/10); если score=null — «—».
8. «Встречи сегодня — N запланировано» (section id="meetings-today"; если meetings_today непустой) — ТАБЛИЦА:
   <div class="tbl-wrap"><table><thead><tr><th>Время</th><th>Сделка</th><th>Проводит</th><th>Статус</th></tr></thead><tbody>
   <tr><td>12:00</td><td><a href="{встреча}">домен</a></td><td>Имя</td><td><span class="badge b-blue">запланирована</span></td></tr></tbody></table></div>
   Время — из meetings_today[].scheduled_at (только HH:MM, МСК).
9. «Содержательный разбор встреч» (section id="meeting-analysis") — по каждой встрече с analysis. Формат ближе к
   ручному эталону, НЕ сухой чек-лист:
   <div class="razbor-card" id="meeting-<id>">
     <div class="razbor-head"><h3>домен · тип · Имя · N мин</h3><div class="razbor-score">8/10</div></div>
     <div class="razbor-sum">1–2 предложения: что произошло и чем это управленчески важно.</div>
     <div class="quote client">дословная цитата клиента из analysis.client_quote<div class="quote-author">Клиент · домен</div></div>
     <div class="hilight-grid">
       <div class="hilight good"><span class="hilight-title">Что сработало</span><div class="hilight-body">конкретный момент из analysis.observations[].text</div><span class="hilight-tag tag-good">цифра/факт</span></div>
       <div class="hilight risk"><span class="hilight-title">Где риск</span><div class="hilight-body">конкретный риск из analysis.observations[].text</div><span class="hilight-tag tag-risk">цифра/факт</span></div>
     </div>
     <div class="callout callout-blue"><div class="callout-label">Следующий шаг</div><div class="callout-body">что · кто · дедлайн из analysis.next_step</div></div>
     <div class="callout callout-amber"><div class="callout-label">Возражения</div><div class="callout-body">возражение — отработано/не отработано, note</div></div>
     <div class="razbor-verdict">Коммитмент: взял обязательство / подумает / нет. Вердикт + расхождение статуса, если status_discrepancy.</div>
     <div class="checks">… вторично: чек-лист из analysis.checklist …</div>
     <div class="razbor-good">🌟 Что было хорошо: …</div>
   </div>
   Meta в h3: домен · тип · Имя · duration_min мин; если direction/направления нет в payload — НЕ придумывай и не пиши. Если analysis.transcript_based=false или analysis.analysis_available=false — добавь бейдж <span class="badge b-amber">разбор по краткому статусу, не по транскрипту</span> и не выдавай блок за глубокий. razbor-score = analysis.score (X/10); если score=null — «—».
10. «Брифы и КП дня» — СВЯЗНЫМ ТЕКСТОМ, не простынёй: «Брифы в работе: <ссылки>», «КП: <ссылки и статусы>». Сумма «нет данных» не дублировать в каждой строке.
11. «Отказы дня» — содержательные потери (воронка Продажи, с деньгами) — мини-таблицей (Сделка/Сумма/Менеджер/Комментарий). ТМ-отвалы НЕ перечислять списком — агрегировать счётчиком из rejections_summary («Отвал (телемаркетинг): N — штатный отсев холодной базы»).
12. «Системные паттерны» — <div class="cards-2"> карточки card-pat (что работает / что повторяется).
13. «Итог дня» — короткий вывод.
В конце: <div class="footer"><p>…</p><div class="data-quality"><b>Качество данных:</b> сделки без суммы — N; встречи без транскрипта — N; …</div></div>.
data-quality добавляй только если payload.data_quality непустой. Это единственное место для технических пробелов данных.
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


def _analysis_for(analyses: dict[Any, Any], meeting_id: Any) -> Any:
    if meeting_id is None:
        return None
    for key in (meeting_id, str(meeting_id)):
        if key in analyses:
            return analyses[key]
    try:
        int_key = int(meeting_id)
    except (TypeError, ValueError):
        return None
    return analyses.get(int_key)


_SALES_TM_ROLE_KEYS = ("продаж", "телемаркет", "роп")


def _sales_tm_only(
    manager_activity: list[dict[str, Any]], roles_map: dict[str, Any]
) -> list[dict[str, Any]]:
    """Только отдел продаж и телемаркетинг — остальных (рекрутёр, аккаунт,
    админ, HR, дизайн) НЕ показываем ни в одном блоке (правило ОП+ТМ)."""
    out = []
    for m in manager_activity:
        role = (roles_map.get(str(m.get("manager_id"))) or "").lower()
        if any(k in role for k in _SALES_TM_ROLE_KEYS):
            out.append(m)
    return out


def build_payload(rows: dict[str, Any], extras: dict[str, Any]) -> dict[str, Any]:
    """Компактный структурированный срез дня для LLM-автора."""
    users = extras.get("users") or {}
    raw = extras.get("raw") or {}
    analyses = extras.get("analyses") or {}
    narrative = extras.get("narrative") or {}
    deal_opp = _deal_opportunity_map(raw)
    # ограничиваем состав строго ОП+ТМ ещё до сборки payload
    roles_map = raw.get("user_roles") or extras.get("user_roles") or {}
    mgr_activity = _sales_tm_only(rows.get("manager_activity", []) or [], roles_map)
    # «Опер» (операционная вовлечённость) по формуле Льва Петровича — рейтинг и Тигр
    meetings_by_mgr = Counter(
        str(m.get("manager_id")) for m in (rows.get("meetings") or []) if m.get("manager_id") is not None
    )
    messenger_by_mgr = raw.get("messenger_dialogs") or {}
    for m in mgr_activity:
        uid = str(m.get("manager_id"))
        role = roles_map.get(uid, "")
        is_tm = oper.is_telemarketing(role)
        score = oper.operational_score(
            dials=m.get("dials_total"),
            normal_calls=m.get("calls_answered"),
            messenger_dialogs=messenger_by_mgr.get(uid, 0),
            meetings_count=meetings_by_mgr.get(uid, 0),
            is_tm=is_tm,
        )
        m["operational_score"] = score
        m["oper_status"] = oper.oper_status(score)
        m["role"] = role
        m["meetings_count"] = meetings_by_mgr.get(uid, 0)
        m["messenger_dialogs"] = messenger_by_mgr.get(uid, 0)
    # «away»: владельцы зависших сделок без активности за день (как Деговцова в эталоне).
    # Дату отпуска не выдумываем (нет источника) — показываем факт: 0 активности + N заморожено.
    stale = extras.get("stale") or {}
    absences = raw.get("absences") or {}  # uid -> дата окончания отпуска (DATE_TO)
    frozen_by_mgr = Counter(
        str(it.get("manager_id"))
        for rows_ in stale.values()
        for it in rows_
        if it.get("manager_id") is not None
    )
    present = {str(m.get("manager_id")) for m in mgr_activity}
    for m in mgr_activity:
        uid = str(m.get("manager_id"))
        m["frozen_deals"] = frozen_by_mgr.get(uid, 0)
        m["vacation_until"] = _fmt_until(absences.get(uid))
        m["away"] = bool(absences.get(uid)) or (
            not (m.get("dials_total") or 0)
            and not (m.get("calls_answered") or 0)
            and not (m.get("meetings_held") or 0)
        )
    for uid in set(frozen_by_mgr) | set(map(str, absences)):
        role = roles_map.get(uid, "")
        if uid in present or not any(k in role.lower() for k in _SALES_TM_ROLE_KEYS):
            continue
        mgr_activity.append(
            {
                "manager_id": int(uid) if uid.isdigit() else uid,
                "dials_total": 0, "calls_answered": 0, "calls_120s_plus": 0,
                "talk_seconds": 0, "meetings_held": 0, "deals_created_count": 0,
                "operational_score": 0.0, "oper_status": oper.oper_status(0.0),
                "role": role, "meetings_count": 0, "messenger_dialogs": 0,
                "away": True, "frozen_deals": frozen_by_mgr.get(uid, 0),
                "vacation_until": _fmt_until(absences.get(uid)),
            }
        )
    mgr_activity.sort(key=lambda m: m.get("operational_score") or 0.0, reverse=True)
    # суммы КП/брифов: если своя сумма пуста — фолбэк на opportunity связанной сделки
    for kp in rows.get("kp_briefs") or []:
        if not kp.get("amount"):
            kp["amount"] = deal_opp.get(str(kp.get("deal_id")))
    rows = {**rows, "manager_activity": mgr_activity}

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
                "manager_id": m.get("manager_id"),
                # связанная сделка + её сумма — чтобы у встречи в «рисках» была сумма,
                # а не «нет данных», и чтобы ссылаться на сделку, а не только на встречу.
                "deal_id": deal_id,
                "deal_opportunity": deal_opp.get(str(deal_id)),
                "analysis": _analysis_for(analyses, mid),
            }
        )

    rejections = []
    for r in extras.get("rejections") or []:
        item = dict(r)
        # человекочитаемая причина вместо кода семантики (F): детального loss-reason
        # в stagehistory нет — даём метку по стадии, без «кода F».
        item["reason_label"] = _REJECTION_LABELS.get(r.get("stage"), "Отказ")
        rejections.append(item)

    stats = _stats(rows, extras)
    deltas = extras.get("deltas") or {}
    health_score = compute_health_score(mgr_activity, meetings, stale)
    manager_coaching = _manager_coaching(narrative, meetings)
    data_quality = _data_quality(rows, raw, analyses)
    return {
        "report_date": extras.get("report_date") or raw.get("report_date"),
        "weekday_date_ru": _ru_date(extras.get("report_date") or raw.get("report_date") or ""),
        "portal_base": PORTAL_BASE,
        "link_patterns": {
            "deal": f"{PORTAL_BASE}/crm/deal/details/{{id}}/",
            "smart_process": f"{PORTAL_BASE}/crm/type/{{entityTypeId}}/details/{{id}}/",
        },
        "users": users,
        "user_roles": raw.get("user_roles") or extras.get("user_roles") or {},
        "stats": stats,
        "deltas": deltas,
        "hero_stats": _hero_stats(stats, deltas),
        "health_score": health_score,
        "narrative": narrative,
        "quote_of_day": _quote_of_day(narrative, meetings),
        "manager_coaching": manager_coaching,
        "action_items": _action_items(narrative, meetings, stale, users),
        "data_quality": data_quality,
        "stale": extras.get("stale") or {},
        "rejections": rejections,
        "rejections_summary": dict(Counter(r.get("reason_label") for r in rejections)),
        "manager_activity": rows.get("manager_activity", []),
        "meetings": meetings,
        "meetings_today": _meetings_today(raw, users),
        "kp_briefs": rows.get("kp_briefs", []),
        "deals_created": raw.get("deals_created", []),
        "telephony": _telephony(rows, users),
        "tm_funnel": _tm_funnel(rows.get("manager_activity", [])),
}


def _hero_stats(stats: dict[str, Any], deltas: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = (deltas or {}).get("metrics") or {}
    spec = [
        ("meetings", stats.get("meetings", 0), "Встречи проведены"),
        ("dials", stats.get("calls_total", 0), "Наборы"),
        ("kp_sent", stats.get("kp_briefs", 0), "КП/брифы"),
        ("deals_created", stats.get("deals_created", 0), "Новые сделки"),
        ("stale_total", stats.get("stale_total", 0), "Зависшие сделки"),
        ("rejections", stats.get("rejections", 0), "Отказы дня"),
    ]
    out = []
    for key, value, label in spec:
        metric = metrics.get(key, {})
        out.append(
            {
                "key": key,
                "label": metric.get("label") or label,
                "value": value,
                "delta": delta_label(metric) if metric else None,
                "trend": metric.get("trend") if metric else None,
            }
        )
    return out


def _quote_of_day(narrative: dict[str, Any], meetings: list[dict[str, Any]]) -> dict[str, Any] | None:
    quote = narrative.get("quote_of_day")
    if isinstance(quote, dict) and quote.get("text"):
        return {"text": str(quote.get("text")), "meta": str(quote.get("meta") or "")}
    for meeting in meetings:
        analysis = meeting.get("analysis") or {}
        if analysis.get("client_quote"):
            return {
                "text": str(analysis["client_quote"]),
                "meta": " · ".join(
                    str(part)
                    for part in (meeting.get("title"), meeting.get("manager"))
                    if part
                ),
            }
    return None


def _manager_coaching(narrative: dict[str, Any], meetings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in narrative.get("manager_coaching") or []:
        if not isinstance(item, dict):
            continue
        advice = str(item.get("advice") or "").strip()
        manager = str(item.get("manager") or "").strip()
        manager_id = item.get("manager_id")
        key = str(manager_id or manager)
        if not advice or not key or key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "manager": manager,
                "manager_id": manager_id,
                "advice": advice,
                "basis": str(item.get("basis") or "").strip(),
            }
        )
    for meeting in meetings:
        manager_id = meeting.get("manager_id")
        key = str(manager_id or meeting.get("manager"))
        if not key or key in seen:
            continue
        analysis = meeting.get("analysis") or {}
        observation = _coaching_observation(analysis.get("observations") or [])
        if not observation:
            continue
        seen.add(key)
        text = str(observation.get("text") or "").strip()
        output.append(
            {
                "manager": meeting.get("manager"),
                "manager_id": manager_id,
                "advice": (
                    f"Разобрать и закрыть риск: {text}"
                    if observation.get("kind") == "risk"
                    else f"Закрепить удачный приём: {text}"
                ),
                "basis": str(observation.get("metric") or meeting.get("title") or "").strip(),
            }
        )
    return output


def _coaching_observation(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    for kind in ("risk", "good"):
        for item in observations:
            if item.get("kind") == kind and item.get("text"):
                return item
    return None


def _action_items(
    narrative: dict[str, Any],
    meetings: list[dict[str, Any]],
    stale: dict[str, list[dict[str, Any]]],
    users: dict[str, Any],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(item: dict[str, Any]) -> None:
        key = (
            str(item.get("owner") or ""),
            str(item.get("action") or ""),
            str(item.get("deal_id") or item.get("title") or ""),
        )
        if not key[0] or not key[1] or key in seen:
            return
        seen.add(key)
        output.append(item)

    for meeting in meetings:
        step = (meeting.get("analysis") or {}).get("next_step")
        if not isinstance(step, dict):
            continue
        action = str(step.get("what") or "").strip()
        if not action:
            continue
        deadline = step.get("deadline") or "на неделе"
        add(
            {
                "source": "meeting_next_step",
                "owner": step.get("who") or meeting.get("manager"),
                "owner_id": meeting.get("manager_id"),
                "deadline": deadline,
                "action": action,
                "deal_id": meeting.get("deal_id"),
                "title": meeting.get("title"),
                "why": "следующий шаг после встречи",
                "urgency": _urgency(deadline),
            }
        )

    for rows_ in (stale or {}).values():
        for item in rows_:
            manager_id = item.get("manager_id")
            add(
                {
                    "source": "stale",
                    "owner": users.get(str(manager_id), manager_id),
                    "owner_id": manager_id,
                    "deadline": "сегодня",
                    "action": "Связаться с клиентом и вернуть движение по стадии",
                    "deal_id": item.get("deal_id"),
                    "title": item.get("title"),
                    "why": item.get("risk_reason") or "зависла стадия",
                    "urgency": "сейчас" if item.get("age_level") == "critical" else "сегодня",
                }
            )

    for item in narrative.get("pinch_list") or []:
        if not isinstance(item, dict):
            continue
        add(
            {
                "source": "pinch_list",
                "owner": item.get("name"),
                "owner_id": item.get("manager_id"),
                "deadline": item.get("deadline") or "сегодня",
                "action": item.get("action"),
                "deal_id": item.get("deal_id"),
                "title": item.get("deal") or item.get("title"),
                "why": item.get("why") or "нарративный риск дня",
                "urgency": item.get("urgency") or "сегодня",
            }
        )

    priority = {"сейчас": 0, "сегодня": 1, "на неделе": 2}
    output.sort(key=lambda item: priority.get(str(item.get("urgency")), 3))
    return output[:12]


def _urgency(deadline: Any) -> str:
    text = str(deadline or "").lower()
    if "сейчас" in text or "asap" in text:
        return "сейчас"
    if "сегодня" in text or "до конца дня" in text:
        return "сегодня"
    return "на неделе"


def _data_quality(rows: dict[str, Any], raw: dict[str, Any], analyses: dict[Any, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    zero_amount = [
        {
            "id": item.get("ID"),
            "title": item.get("TITLE") or item.get("title") or item.get("ID"),
        }
        for item in [*(raw.get("deals_open") or []), *(raw.get("deals_created") or [])]
        if _float_or_zero(item.get("OPPORTUNITY") or item.get("opportunity")) <= 0
    ]
    if zero_amount:
        issues.append(
            {
                "kind": "zero_amount",
                "label": "сделки без суммы",
                "count": len(zero_amount),
                "items": zero_amount[:10],
            }
        )

    meetings_without_transcript = []
    for meeting in rows.get("meetings") or []:
        mid = meeting.get("meeting_id")
        analysis = _analysis_for(analyses, mid)
        transcript_bad = meeting.get("transcript_ok") is False
        if isinstance(analysis, dict):
            transcript_bad = transcript_bad or analysis.get("transcript_based") is False
        if transcript_bad:
            meetings_without_transcript.append(
                {
                    "id": mid,
                    "title": meeting.get("title") or mid,
                }
            )
    if meetings_without_transcript:
        issues.append(
            {
                "kind": "missing_transcript",
                "label": "встречи без транскрипта",
                "count": len(meetings_without_transcript),
                "items": meetings_without_transcript[:10],
            }
        )
    return issues


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt_until(value: Any) -> str | None:
    """DATE_TO Bitrix («08.06.2026 13:00:00» или ISO) → «08.06»."""
    if not value:
        return None
    head = str(value).split("T")[0].split(" ")[0]
    if "." in head:
        p = head.split(".")
        return f"{p[0]}.{p[1]}" if len(p) >= 2 else head
    if "-" in head:
        p = head.split("-")
        return f"{p[2]}.{p[1]}" if len(p) >= 3 else head
    return head


def _meetings_today(raw: dict[str, Any], users: dict[str, Any]) -> list[dict[str, Any]]:
    """Запланированные на сегодня встречи (для секции «Встречи сегодня»)."""
    out = []
    for it in raw.get("meet_today") or []:
        out.append(
            {
                "id": it.get("id"),
                "entityTypeId": 1048,
                "title": it.get("title"),
                "manager": users.get(str(it.get("assignedById")), it.get("assignedById")),
                "deal_id": it.get("parentId2"),
                "scheduled_at": it.get("ufCrm16_1751009238"),
            }
        )
    return out


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
        dials = item.get("dials_total", 0) or 0
        answered = item.get("calls_answered", 0) or 0
        out.append(
            {
                "manager": users.get(str(item.get("manager_id")), item.get("manager_id")),
                "manager_id": item.get("manager_id"),
                "role": item.get("role"),
                "dials_total": dials,
                "calls_answered": answered,
                "connect_percent": round(answered / dials * 100) if dials else 0,
                "calls_120s_plus": item.get("calls_120s_plus", 0),
                "messenger_dialogs": item.get("messenger_dialogs", 0),
                "hours": round((item.get("talk_seconds") or 0) / 3600, 1),
                "meetings_held": item.get("meetings_held", 0),
                "new_deals": item.get("deals_created_count", 0),
                "meetings_count": item.get("meetings_count", 0),
                "operational_score": item.get("operational_score"),
                "oper_status": item.get("oper_status"),
                "away": item.get("away", False),
                "frozen_deals": item.get("frozen_deals", 0),
                "vacation_until": item.get("vacation_until"),
            }
        )
    out.sort(key=lambda x: x.get("operational_score") or 0.0, reverse=True)
    return out


def _tm_funnel(manager_activity: list[dict[str, Any]]) -> dict[str, Any]:
    tm_rows = [item for item in manager_activity if oper.is_telemarketing(item.get("role"))]
    dials = sum(item.get("dials_total", 0) or 0 for item in tm_rows)
    answered = sum(item.get("calls_answered", 0) or 0 for item in tm_rows)
    long_calls = sum(item.get("calls_120s_plus", 0) or 0 for item in tm_rows)
    meetings_set = sum(item.get("meetings_set", 0) or 0 for item in tm_rows)
    meetings_held = sum(item.get("meetings_held", 0) or 0 for item in tm_rows)
    deals_created = sum(item.get("deals_created_count", 0) or 0 for item in tm_rows)

    return {
        "count": len(tm_rows),
        "dials_total": dials,
        "calls_answered": answered,
        "calls_120s_plus": long_calls,
        "meetings_set": meetings_set,
        "meetings_held": meetings_held,
        "deals_created_count": deals_created,
        "answered_percent": _pct(answered, dials),
        "long_call_percent": _pct(long_calls, answered),
        "meeting_set_percent": _pct(meetings_set, long_calls),
        "deal_create_percent": _pct(deals_created, meetings_held),
    }


def _pct(value: int | float, total: int | float) -> int:
    return round(value / total * 100) if total else 0


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


def substitute_photos(body_html: str, photos: dict[str, str], users: dict[str, str] | None = None) -> str:
    """Заменяет src="photo:ID" на data-URI; без фото оставляет аккуратный fallback."""
    photos = photos or {}
    user_to_photo = {name: photos.get(str(uid)) for uid, name in (users or {}).items()}

    def repl(match: re.Match) -> str:
        tag = match.group(0)
        uid = match.group(1)
        alt = re.search(r'alt="([^"]*)"', tag)
        alt_text = html.unescape(alt.group(1)).strip() if alt else ""
        data = photos.get(str(uid)) or user_to_photo.get(alt_text)
        if data:
            return tag.replace(f'src="photo:{uid}"', f'src="{data}"')
        label = alt_text[:1] or "?"
        classes = re.search(r'class="([^"]*)"', tag)
        class_attr = html.escape((classes.group(1) if classes else "") + " photo-fallback")
        return f'<span class="{class_attr}" data-no-photo="1">{html.escape(label)}</span>'

    return re.sub(r'<img\b[^>]*\bsrc="photo:([^"]+)"[^>]*>', repl, body_html)


def wrap_document(body_html: str, css: str, report_date: Any) -> str:
    safe_date = html.escape(str(report_date))
    return (
        '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>Сводка продаж {safe_date}</title>"
        f"<style>{css}</style></head><body>{body_html}</body></html>"
    )
