"""Движок аудита сделки для «Командного центра».

Собирает сделку целиком (карточка + встречи 1048 + брифы 1056 + КП 1106 +
звонки/активности + timeline-переписка Wazzup), вычисляет ДЕТЕРМИНИРОВАННЫЕ
сигналы и честный «шанс возврата» (recovery score), ожидаемую ценность (EV) и
теги системных провалов, затем зовёт LLM ТОЛЬКО за нарративом (вердикт, разбор
провалов словами, следующий шаг, текст первой задачи). Балл задаёт код, не LLM —
LLM может лишь объяснить балл и предложить узкую поправку в заданных границах.

Запуск (LLM-ключ в окружении):
    python -m src.audit_engine 23332
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

from . import analyze_llm, bx_client, call_audio, reputation, web_context
from .enrich import enrich_meetings

# ── Поля Bitrix ───────────────────────────────────────────────────────────────
F_MEETING_TYPE = "ufCrm16_1751006460"  # 2638=брифинг, 2640=защита
MTYPE_BRIEFING, MTYPE_DEFENSE = 2638, 2640
F_DEAL_REVENUE = "UF_CRM_67B35193BAFB4"  # оборот компании "value|RUB"
F_DEAL_DEATH_STAGE = "UF_CRM_1772007767"  # этап, на котором встала сделка
F_DEAL_MGR_COMMENT = "UF_CRM_635011179F7DD"  # свободный комментарий менеджера
F_DEAL_LOST_REASON = "UF_CRM_1771495464"  # enum причины отвала
F_DEAL_AUDIT = "UF_CRM_DEAL_AUDIT"  # поле для .docx аудита
SPAM_REASON_ID = "8588"
WAZZUP_AUTHOR_ID = "2358"  # все Wazzup-сообщения идут от тех. пользователя интеграции

SEL_1048 = ["id", "title", "stageId", F_MEETING_TYPE, "ufCrm16_1751009238",
            "ufCrm16_1751006555", "ufCrm16Transcript", "assignedById", "createdBy"]

# Стадии воронки «Продажи» (CATEGORY_ID=10), значения semantic.
LOST_STAGE, DEFERRED_STAGE = "C10:LOSE", "C10:1"

# ── Детерминированная модель «шанса возврата» ────────────────────────────────
# Константы в одном месте — чтобы откалибровать на истории (улучшение #4).
# Балл = forward-looking «шанс ВЫИГРАТЬ бизнес у этого клиента сейчас», а не «отыграть ту
# сделку, что упустили». Поэтому активный диалог СЕЙЧАС — сильный плюс, а старые потери
# (увели одну ветку конкуренту) — контекст, а не приговор, если клиент ещё на связи.
SCORE_BASE = 30
W_FRESH_CONTACT = 10       # последний контакт ≤14 дней — кто-то ещё на связи
W_LIVE_DEAL = 8            # активный диалог сейчас (≤7 дней) — клиент вовлечён, живая ветка
                           # (умеренный плюс: days_since ловит и внутренние заметки, не только клиента)
W_DM_LEVER_UNTRIED = 12    # до ЛПР не дошли, но есть его контакт → ясный непройденный путь
W_HAS_BUDGET = 5           # у компании есть оборот / в сделке есть сумма
W_WARM_HISTORY = 5         # были встречи/брифы — нас знают
P_CONTACT_LOST = -8        # контактное лицо ушло из компании
P_KP_NO_DEFENSE = -5       # КП отправлено, но не защищено (знаем дыру, чинится)
P_DM_BUDGET_REJECTION = -25  # ЛПР лично сказал «нет бюджета» — рычаг исчерпан
P_COMPETITOR_WON = -30     # ушли к конкуренту (клиент потерян целиком)
P_COMPETITOR_WON_LIVE = -10  # конкурент увёл ВЕТКУ, но клиент ещё активно с нами — не приговор
P_STALE_90 = -15           # без контакта >90 дней
P_HANDOVER_2PLUS = -5      # 2+ передачи между менеджерами
SCORE_MIN, SCORE_MAX = 5, 90  # никогда не 0/100 — честность: абсолютов не бывает
LLM_ADJ_CAP = 15           # LLM может подвинуть балл на ±15 (запас на живой разворот сделки)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(raw: Any) -> int:
    if raw in (None, "", 0):
        return 0
    s = str(raw).split("|")[0].replace(" ", "")
    try:
        return int(float(s))
    except ValueError:
        return 0


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _strip_bb(text: str) -> str:
    text = re.sub(r"\[img\][^\[]*\[/img\]", "", text or "")
    text = re.sub(r"\[/?[a-zA-Z][^\]]*\]", "", text)
    return text.replace("&nbsp;", " ").strip()


def _strip_html(text: str) -> str:
    """HTML-тело письма → плоский текст: режем style/script, теги, схлопываем пробелы."""
    text = re.sub(r"(?is)<(style|script|head)[^>]*>.*?</\1>", " ", text or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _emails(acts: list[dict]) -> list[dict]:
    """Email-активности сделки (TYPE_ID=4, CRM_EMAIL) в хронологии: дата, направление,
    тема, тело (из HTML в текст). Тело режем — длинные цепочки тянут хвост цитат."""
    out = []
    for a in sorted(acts, key=lambda x: x.get("CREATED") or ""):
        if str(a.get("TYPE_ID")) != "4":
            continue
        body = _strip_html(a.get("DESCRIPTION") or "")
        out.append({
            "date": (a.get("CREATED") or "")[:10],
            "direction": "входящее" if str(a.get("DIRECTION")) == "1" else "исходящее",
            "subject": (a.get("SUBJECT") or "").strip(),
            "body": body[:2500],
        })
    return out


# ── Сбор данных ──────────────────────────────────────────────────────────────
def collect_deal_context(deal_id: int) -> dict[str, Any] | None:
    deal = bx_client.call("crm.deal.get", {"id": deal_id}).get("result")
    if not deal:
        return None
    company = {}
    if deal.get("COMPANY_ID") and deal["COMPANY_ID"] != "0":
        company = bx_client.call("crm.company.get", {"id": deal["COMPANY_ID"]}).get("result") or {}
    contact = {}
    if deal.get("CONTACT_ID") and deal["CONTACT_ID"] != "0":
        contact = bx_client.call("crm.contact.get", {"id": deal["CONTACT_ID"]}).get("result") or {}

    def sp(etid: int) -> list[dict]:
        r = bx_client.call("crm.item.list", {"entityTypeId": etid, "filter": {"parentId2": deal_id}})
        return (r.get("result") or {}).get("items", [])

    meetings, briefs, kp = sp(1048), sp(1056), sp(1106)

    acts = bx_client.fetch_all(
        "crm.activity.list",
        {"filter": {"OWNER_ID": deal_id, "OWNER_TYPE_ID": 2}, "select": ["*"]},
        cap=500,
    )
    timeline = bx_client.call(
        "crm.timeline.comment.list",
        {"filter": {"ENTITY_ID": deal_id, "ENTITY_TYPE": "deal"}, "order": {"CREATED": "ASC"}},
    ).get("result") or []

    external = None
    try:  # внешний контекст (сайт клиента + репутация) — строго fail-safe, не валит аудит
        external = web_context.deal_external_context(deal) or {}
        site = external.get("site") if isinstance(external, dict) else None
        site_ok = site if (isinstance(site, dict) and site.get("ok")) else None
        # репутация: матчим по БРЕНДУ. Бренд надёжнее в title сайта («клиника Улыбка»), а не в
        # юрлице карточки («ООО НОЙ»). Поэтому site.title первым, company.TITLE — фолбэк.
        name = ((site_ok or {}).get("title") or company.get("TITLE") or "").strip()
        rep = reputation.collect(name, (site_ok or {}).get("text"))
        if rep:
            external["reputation"] = rep
        external = external or None
    except Exception:
        external = None

    return {
        "deal": deal, "company": company, "contact": contact,
        "meetings": meetings, "briefs": briefs, "kp": kp,
        "activities": acts, "timeline": timeline, "external": external,
    }


# ── Детерминированные сигналы ────────────────────────────────────────────────
def compute_signals(ctx: dict[str, Any]) -> dict[str, Any]:
    deal = ctx["deal"]
    acts, timeline = ctx["activities"], ctx["timeline"]
    full_text = " ".join(_strip_bb(c.get("COMMENT", "")) for c in timeline)
    full_text += " " + (deal.get(F_DEAL_MGR_COMMENT) or "")
    # Письма тоже учитываем в детекте КП/pitch — клиент часто получает КП по почте.
    full_text += " " + " ".join(f"{e['subject']} {e['body']}" for e in _emails(acts))
    for b in ctx["briefs"]:
        for v in b.values():
            if isinstance(v, str) and "pitch.com" in v:
                full_text += " " + v

    # последний реальный контакт = последняя активность или комментарий
    contact_dts = []
    for a in acts:
        d = _parse_dt(a.get("CREATED") or a.get("LAST_UPDATED"))
        if d:
            contact_dts.append(d)
    for c in timeline:
        d = _parse_dt(c.get("CREATED"))
        if d:
            contact_dts.append(d)
    last_contact = max(contact_dts) if contact_dts else _parse_dt(deal.get("DATE_MODIFY"))
    days_since = (_now() - last_contact).days if last_contact else None

    # handover = смены RESPONSIBLE_ID по звонкам/активностям во времени
    responsibles = []
    for a in sorted(acts, key=lambda x: x.get("CREATED") or ""):
        rid = a.get("RESPONSIBLE_ID")
        if rid and (not responsibles or responsibles[-1] != rid):
            responsibles.append(rid)
    handover_count = max(0, len(set(responsibles)) - 1)

    calls = [a for a in acts if str(a.get("TYPE_ID")) == "2"]
    kp_cards = len(ctx["kp"])
    kp_via_pitch = "pitch.com" in full_text
    meeting_types = {int(m.get(F_MEETING_TYPE)) for m in ctx["meetings"] if m.get(F_MEETING_TYPE)}
    had_defense = MTYPE_DEFENSE in meeting_types
    kp_sent = kp_via_pitch or kp_cards > 0 or "коммерческое предложение" in full_text.lower() or "кп" in full_text.lower()

    lost_reason = str(deal.get(F_DEAL_LOST_REASON) or "")
    death_stage = deal.get(F_DEAL_DEATH_STAGE) or ""
    revenue = _money(ctx["company"].get("REVENUE") or deal.get(F_DEAL_REVENUE))
    opportunity = _money(deal.get("OPPORTUNITY"))

    # текстовые эвристики (мягкие сигналы — будут уточнены LLM в rationale)
    low = full_text.lower()
    contact_lost = bool(re.search(r"(не работает|уволил|больше не|сменил|ушла из|ушёл из)", low))
    competitor_won = lost_reason == "" and bool(re.search(r"(конкурент|выбрали друг|ушли к)", low))
    budget_no = bool(re.search(r"(нет бюджета|не имеет.*бюджет|бюджет не соглас|нехватка бюджет)", low))

    return {
        "stage_id": deal.get("STAGE_ID"),
        "stage_semantic": deal.get("STAGE_SEMANTIC_ID"),
        "death_stage": death_stage,
        "lost_reason_id": lost_reason,
        "is_spam": lost_reason == SPAM_REASON_ID,
        "closed": deal.get("CLOSED") == "Y",
        "opportunity": opportunity,
        "company_revenue": revenue,
        "kp_cards": kp_cards,
        "kp_via_pitch": kp_via_pitch,
        "kp_sent": kp_sent,
        "had_defense": had_defense,
        "meetings_total": len(ctx["meetings"]),
        "briefs_total": len(ctx["briefs"]),
        "calls_total": len(calls),
        "handover_count": handover_count,
        "responsibles_chain": responsibles,
        # текущий ответственный за сделку на момент аудита (ASSIGNED_BY_ID карточки).
        # Цепочка responsibles_chain хвостом ловит постановщика задач (Щемелёв 12),
        # поэтому "менеджер на начало аудита" берём именно отсюда.
        "deal_responsible_id": (int(deal.get("ASSIGNED_BY_ID")) if str(deal.get("ASSIGNED_BY_ID") or "").isdigit() else None),
        "last_contact": last_contact.isoformat() if last_contact else None,
        "days_since_contact": days_since,
        "contact_lost": contact_lost,
        "competitor_won": competitor_won,
        "budget_objection": budget_no,
        # ЛПР: есть ли в компании директор и дошли ли до него — эвристика
        "dm_name": ctx["company"].get("UF_CRM_1737098484851"),
        "dm_phone": ctx["company"].get("UF_CRM_1737098509308"),
    }


def _failure_tags(sig: dict[str, Any]) -> list[dict[str, str]]:
    """Канонические теги провалов — для агрегации по менеджерам (улучшение #6)."""
    tags: list[dict[str, str]] = []
    def add(tag, label):
        tags.append({"tag": tag, "label": label})
    if sig["kp_cards"] == 0 and sig["kp_sent"]:
        add("KP_NO_CARD", "КП без карточки в CRM")
    if sig["kp_via_pitch"]:
        add("KP_VIA_PITCH", "КП ушло через pitch.com мимо CRM")
    if sig["kp_sent"] and not sig["had_defense"]:
        add("NO_DEFENSE", "Защита КП не проведена")
    if sig["handover_count"] >= 2:
        add("HANDOVER_NO_CONTEXT", "Двойная передача между менеджерами")
    elif sig["handover_count"] == 1:
        add("HANDOVER", "Передача между менеджерами")
    if sig["briefs_total"] >= 3:
        add("BRIEF_SPRAY", "Стрельба по площадям брифами")
    if sig["budget_objection"]:
        add("BUDGET_LABEL", "Причина-метка «нет бюджета»")
    if sig["contact_lost"]:
        add("CONTACT_LOST", "Контактное лицо ушло")
    if sig["competitor_won"]:
        add("COMPETITOR", "Ушли к конкуренту")
    return tags


def recovery_score(sig: dict[str, Any]) -> dict[str, Any]:
    """Честный шанс возврата (0–100) из детерминированных сигналов."""
    score = SCORE_BASE
    factors: list[dict[str, Any]] = []

    def f(cond, weight, label, kind=None):
        nonlocal score
        if cond:
            score += weight
            factors.append({
                "label": label, "weight": weight,
                "kind": kind or ("pos" if weight > 0 else "neg"),
            })

    days = sig["days_since_contact"]
    is_live = days is not None and days <= 7  # активный диалог прямо сейчас
    f(days is not None and days <= 14, W_FRESH_CONTACT, "Свежий контакт (≤14 дней)")
    f(is_live, W_LIVE_DEAL, "Активный диалог сейчас — клиент вовлечён")
    dm_untried = bool(sig.get("dm_phone")) and not sig["had_defense"]
    f(dm_untried, W_DM_LEVER_UNTRIED, "ЛПР не вовлечён — рычаг не нажат", kind="opp")
    f(sig["company_revenue"] > 0 or sig["opportunity"] > 0, W_HAS_BUDGET, "У компании есть бюджет")
    f(sig["meetings_total"] > 0 or sig["briefs_total"] > 0, W_WARM_HISTORY, "Тёплая история (встречи/брифы)")
    f(sig["contact_lost"], P_CONTACT_LOST, "Контактное лицо ушло")
    f(sig["kp_sent"] and not sig["had_defense"], P_KP_NO_DEFENSE, "КП не защищено перед ЛПР")
    # «нет бюджета» от не-ЛПР (защиты не было) — мягкий минус; от ЛПР — жёсткий
    f(sig["budget_objection"] and sig["had_defense"], P_DM_BUDGET_REJECTION, "ЛПР отказал по бюджету")
    # Конкурент: если клиент ещё активно с нами (живая ветка) — увели лишь часть, не клиента целиком
    f(sig["competitor_won"], P_COMPETITOR_WON_LIVE if is_live else P_COMPETITOR_WON,
      "Конкурент увёл ветку (диалог жив)" if is_live else "Ушли к конкуренту")
    f(days is not None and days > 90, P_STALE_90, "Без контакта >90 дней")
    f(sig["handover_count"] >= 2, P_HANDOVER_2PLUS, "2+ передачи менеджера")

    raw = score
    score = max(SCORE_MIN, min(SCORE_MAX, score))
    band = "low" if score < 40 else ("mid" if score < 65 else "hi")
    ev = round(score / 100 * sig["opportunity"]) if sig["opportunity"] else 0
    return {"score": score, "raw": raw, "band": band, "expected_value": ev, "factors": factors}


# ── LLM-нарратив (балл уже посчитан, LLM его объясняет) ───────────────────────
# Каталог паттернов отдела — «насмотренность» из инсайтов проекта deal-analysis.
# Именно привязка находок к этим паттернам отличает аудит коммерческого директора
# от общего LLM-ревью: разбор узнаёт «это снова КП мимо CRM / 5-й handover / метка
# вместо причины», а не описывает сделку с нуля.
PATTERNS_CATALOG = """
КАТАЛОГ СИСТЕМНЫХ ПАТТЕРНОВ ОТДЕЛА (привязывай находки к ним по pattern_id):

8 столпов провала на «Подготовке КП»:
- KP_NO_CARD: КП готовится/шлётся мимо CRM (pitch.com, Google Sheets, почта) — РОП не видит цены/состава/даты. (эталон: mpya.ru — 4 КП, 0 карточек)
- KP_OVER_BUDGET: КП превышает озвученный бюджет клиента >20% без согласования.
- KP_STUCK_INSIDE: готовое КП лежит внутри агентства неделями — клиент остывает. (sinai-clinic.ru — 15 дней)
- BRIEF_SPRAY: несколько КП/брифов на один запрос — перегруз, «уйду подумать». (правило: 1 сделка = 1 КП)
- CANT_DEFEND_PRICE: менеджер не может защитить цену («чем лучше бесплатного шаблона?»).

Реальная причина ≠ метка CRM (60% отвалов — управляемые ошибки):
- LABEL_NO_CONTACT: «Нет связи» = клиент выбрал молчанием = нет интереса (плохой дожим).
- LABEL_CHANGED_MIND: «Передумали» = бюджет не сошёлся (не выяснили на встрече).
- LABEL_COMPETITOR: «Ушли к конкуренту» = мы взяли слишком долгую паузу в горячий момент после КП.
- LABEL_BUDGET: «Нехватка бюджета» = бюджет не квалифицировали на первом контакте.

5 ловушек коммуникации:
- TRAP_URGENCY: давление срочностью на B2B — не работает.
- TRAP_FAKE_REASON: ставят «передумали» вместо реальной причины (снять ответственность).
- TRAP_CLIENT_WILL_CALL: «я сама свяжусь» приняли как живой шаг вместо фиксации даты = дверь закрыта.
- TRAP_NO_VALUE: не объяснили ценность (клиент слышит «менеджер сам не знает за что цена»).
- TRAP_COLD_HANDOVER: передача от уволенного как холодный звонок («незнакомец называет имя другого незнакомца»).

Сквозные антипаттерны:
- NO_DEFENSE: защиту КП не провели — КП самотёком, не-ЛПР не «продаёт внутрь».
- NON_DM_CONTACT: работа не с ЛПР; решение зависит от того, кого не вывели на встречу.
- HANDOVER_NO_CONTEXT: передача между менеджерами без передаточного листа — клиент «не помнит». (5 кейсов: mpya, sinai, mitekpumps, klinikastom, drmannanov)
- STAGE_VS_REALITY: стадия CRM рисует активную работу там, где сделка фактически встала.
"""

AUDIT_SYSTEM = """
Ты — опытный коммерческий директор агентства Belberry (медицинский и B2B маркетинг:
SEO, контекст, веб-разработка/Strapi, GEO/маркетплейсы, ORM/репутация, SMM). Ты разобрал
сотни сделок и узнаёшь типовые провалы с полуслова.

Тебе дают ОДНУ сделку целиком: карточку, ПОЛНУЮ хронологию (timeline/Wazzup дословно +
журнал звонков + ПЕРЕПИСКУ ПО ПОЧТЕ в поле emails: тема и тело каждого письма с указанием
входящее/исходящее), брифы, КП, встречи (с транскриптами, если есть), УЖЕ ПОСЧИТАННЫЙ
детерминированный «шанс возврата» и КАТАЛОГ ПАТТЕРНОВ отдела. Письма читай так же
внимательно, как Wazzup: там бывают реальные возражения, обещания и сигналы охлаждения.
Если есть поле client_site_now — это СНИМОК САЙТА КЛИЕНТА ПРЯМО СЕЙЧАС (текст главной). Сверь
реальность с перепиской: что у клиента уже есть/сделано, какая ниша и услуги на самом деле,
какие очевидные дыры в веб-присутствии (нет цен/отзывов/слабая первичка) — это даёт предметные
рычаги для возврата и не даёт опираться на устаревшие слова из старых переговоров. Если поля нет
или сайт пустой — просто игнорируй, без догадок.
Если есть поле client_reputation — это РЕЙТИНГ И ЧИСЛО ОТЗЫВОВ клиента в публичных агрегаторах
(ProDoctorov и др.) + блок competitors (конкуренты города с их рейтингами). Используй как рычаг:
слабый рейтинг/мало отзывов = реальная боль (репутация теряет первичку — повод зайти с ORM/отзывами);
сильный = аргумент «вам есть что защищать в выдаче». СРАВНИ клиента с конкурентами: отстаёт по
рейтингу/отзывам → конкретный повод («у соседних клиник 5.7–6.4, у вас столько-то — вот где теряете
выбор пациента»). Не выдумывай цифр сверх данных.

Дай ГЛУБОКИЙ и ЧЕСТНЫЙ разбор уровня документа для команды — как тот, что коммерческий
директор приносит на разбор с РОПом. Требования к глубине:
- Восстанови ХРОНОЛОГИЮ по датам (что произошло → кто), как её видно из данных.
  КАЖДУЮ дату указывай С ГОДОМ в формате ДД.ММ.ГГГГ (год обязателен — события сделки
  могут охватывать несколько лет). Отсортируй хронологию СТРОГО от самого раннего
  события к самому позднему.
- Если даны РАСШИФРОВКИ ЗВОНКОВ — разбери каждый разговор (call_analysis): о чём говорили,
  тон клиента, возражения, как отработал менеджер, что клиент пообещал. Бери из них дословные
  цитаты в key_quotes/failures. Расшифровка может быть с мелкими ошибками распознавания —
  трактуй по смыслу, имена/бренды восстанавливай (напр. «Белл Дыри»→Belberry).
- Каждый провал подкрепляй ДОСЛОВНОЙ цитатой из таймлайна/транскрипта/звонка с датой. Цитаты бери
  только дословно; если показательной нет — пиши detail без выдуманной цитаты.
- Привязывай находки к каталогу паттернов (pattern_id) — узнавай повторяющееся, а не описывай с нуля.
- Отдели «как было» от «как должно было быть» (секции what_would_save_it и systemic_conclusions),
  иначе разбор станет тенденциозным.
- СВЕЖЕСТЬ И ЖИВАЯ ВЕТКА. Сделка эволюционирует: часть направлений могла УМЕРЕТЬ (увели, отказ),
  а другое обсуждается ПРЯМО СЕЙЧАС. Определи по СВЕЖИМ коммуникациям, что ЖИВО сегодня, и веди
  вердикт (summary) и следующий шаг ОТ ЖИВОЙ ТЕМЫ. Умершие направления — кратко как контекст
  («сайт/SEO уже проехали — увели»), НЕ пережёвывай их как главную драму. Балл — это шанс ВЫИГРАТЬ
  бизнес у клиента сейчас, а не отыграть упущенное; если клиент активно с нами по новой теме —
  это не «почти ноль».
- ЧЕСТНАЯ АТРИБУЦИЯ. Не вешай на менеджера то, что пришло ОТ КЛИЕНТА. Если клиент САМ пришёл с
  широким/расфокусированным запросом («хочу и сайт, и SEO, и карты, и…») — это НЕ «стрельба по
  площадям» менеджера; структурный тег (3+ брифа) — факт, но в разборе укажи источник расфокуса
  честно (клиент vs менеджер). Так же аккуратно с «работа не с ЛПР»: если общались с тем, кого
  клиент сам выставил контактным — это его устройство, а вина — лишь в том, что не добились выхода на ЛПР.
- Балл возврата НЕ переписывай — он посчитан кодом. Объясни его и, если видишь сильный нюанс
  (например живой разворот сделки в новую тему), предложи recommended_adjustment в пределах
  [-15..15] (по умолчанию 0).
- Если шансов мало — так и пиши прямо, без приукрашивания.
- ЯЗЫК: пиши по-русски, человеческим языком руководителя отдела продаж. В текстах (summary,
  detail, цитаты-пояснения и т.д.) ЗАПРЕЩЕНО упоминать технические имена полей и сигналов
  (например kp_cards, kp_via_pitch, had_defense, signals, handover_count, pattern_id, true/false)
  и латиницу/англицизмы. Вместо «kp_cards = 0» пиши «карточки КП в системе нет»; вместо
  «kp_via_pitch=true» — «КП ушло сторонним сервисом». pattern_id оставляй кодом ТОЛЬКО в поле
  pattern_id (его подменяет интерфейс) — но в title и detail его не пиши. Названия сервисов/брендов
  (Belberry, ПроДокторов) — можно.

Верни строго JSON без markdown:
{
  "current_state": {
    "live_topic": "что обсуждаем С КЛИЕНТОМ ПРЯМО СЕЙЧАС (живая тема одной строкой); если всё умерло — 'диалог не ведётся'",
    "client_wanted": "что клиент хотел/просил (по сути, кратко)",
    "we_didnt_give": "что мы НЕ дали / где провалили (кратко, по делу)",
    "agreed_next_step": "на какой следующий шаг ДОГОВОРИЛИСЬ (с датой, если есть) ЛИБО честно 'не договорились — диалог завис на <чём>'",
    "ball_is_on": "на чьей стороне мяч сейчас: 'на нас' | 'на клиенте' | 'повис'",
    "client_mood": "тёплый | нейтральный | остывает | потерян"
  },
  "summary": "3-5 фраз: что за сделка, путь, почему встала, реальная причина (не метка)",
  "real_cause": "корневая причина одной фразой",
  "verdict_band_text": "короткая характеристика шанса (напр. 'низкий — но один рычаг не нажат')",
  "chronology": [{"date": "ДД.ММ.ГГГГ", "event": "что произошло", "who": "кто"}],
  "key_quotes": [{"date": "ДД.ММ.ГГГГ", "speaker": "кто", "quote": "дословная цитата (можно из расшифровки звонка)", "why": "что показывает"}],
  "call_analysis": [{"date": "ДД.ММ.ГГГГ", "summary": "о чём говорили", "client_tone": "тон/настрой клиента", "objections": ["возражения из разговора"], "manager_quality": "как отработал менеджер", "commitment": "что клиент пообещал/не пообещал"}],
  "failures": [{"title": "провал", "detail": "что именно + дословная цитата с датой", "pattern_id": "KP_NO_CARD|NO_DEFENSE|HANDOVER_NO_CONTEXT|NON_DM_CONTACT|STAGE_VS_REALITY|BRIEF_SPRAY|LABEL_BUDGET|...", "severity": "high|med|low"}],
  "pattern_matches": [{"pattern_id": "...", "note": "как именно проявился в этой сделке"}],
  "what_went_well": ["что сделали хорошо — честно"],
  "what_would_save_it": ["что конкретно спасло бы/спасёт сделку, по этапам"],
  "next_steps": ["конкретные шаги к возврату, по порядку"],
  "first_task": {"title": "заголовок первой задачи ответственному", "description": "готовый план звонка/действия с под-пунктами и репликами"},
  "systemic_conclusions": [{"broken": "что сломано в процессе", "fix": "как лечить (регламент/триггер)"}],
  "recovery_rationale": "почему балл именно такой и что подняло бы его",
  "recommended_adjustment": 0
}
""" + PATTERNS_CATALOG


def _build_llm_payload(ctx: dict, sig: dict, score: dict) -> str:
    deal = ctx["deal"]
    # Полный таймлайн дословно (Wazzup + заметки менеджеров) — главный источник
    # «как было сказано». Не режем: глубина разбора рождается именно здесь.
    tl = []
    for c in ctx["timeline"]:
        t = _strip_bb(c.get("COMMENT", ""))
        if t:
            tl.append(f"[{c.get('CREATED','')[:10]}] {t[:2500]}")
    # Журнал звонков: дата · направление · автор · длительность — восстанавливает темп.
    calls = []
    for a in sorted(ctx["activities"], key=lambda x: x.get("CREATED") or ""):
        if str(a.get("TYPE_ID")) == "2":
            dur = (a.get("SETTINGS") or {}).get("DURATION") if isinstance(a.get("SETTINGS"), dict) else None
            calls.append(f"[{a.get('CREATED','')[:10]}] звонок dir={a.get('DIRECTION')} автор={a.get('AUTHOR_ID')} {dur or ''}".strip())
    # Брифы целиком (вопрос→ответ), без служебных пустот.
    briefs = [{k: v for k, v in b.items() if isinstance(v, str) and v and len(v) > 1
               and not k.endswith(("Time",)) and "http" not in v[:8]}
              for b in ctx["briefs"]]
    payload = {
        "deal": {
            "id": deal.get("ID"), "title": deal.get("TITLE"),
            "stage": sig["stage_id"], "death_stage": sig["death_stage"],
            "manager_comment": deal.get(F_DEAL_MGR_COMMENT),
            "opportunity": sig["opportunity"], "company_revenue": sig["company_revenue"],
            "created": deal.get("DATE_CREATE"), "modified": deal.get("DATE_MODIFY"),
        },
        "company": ctx["company"].get("TITLE"),
        "contact": {"name": f"{ctx['contact'].get('NAME','')} {ctx['contact'].get('LAST_NAME','')}".strip(),
                    "post": ctx["contact"].get("POST")},
        "decision_maker": {"name": sig.get("dm_name"), "phone": sig.get("dm_phone")},
        "signals": sig,
        "recovery_score": {"score": score["score"], "factors": score["factors"]},
        "briefs": briefs,
        "calls_log": calls,
        "timeline": tl,
        "emails": _emails(ctx["activities"]),
    }
    # Внешний контекст: что СЕЙЧАС на сайте клиента (если удалось снять).
    ext = ctx.get("external") or {}
    site = ext.get("site") if isinstance(ext, dict) else None
    if site and site.get("ok") and site.get("text"):
        payload["client_site_now"] = {"url": site.get("url"), "title": site.get("title"), "text": site.get("text")}
    # Репутация в агрегаторах (рейтинг/отзывы): ProDoctorov и др.
    rep = ext.get("reputation") if isinstance(ext, dict) else None
    if rep:
        payload["client_reputation"] = rep
    return json.dumps(payload, ensure_ascii=False, default=str)


F_MEETING_RECORD = "ufCrm16_1751006555"  # ссылка на видеозапись встречи (Drive)


def _meeting_transcripts(ctx: dict) -> str:
    if not ctx["meetings"]:
        return ""
    try:
        enriched = enrich_meetings({"m": ctx["meetings"]}, refresh=True)
    except Exception:
        enriched = {}
    parts = []
    for m in ctx["meetings"]:
        tr = enriched.get(int(m["id"]), {})
        text = (tr.get("text") or "").strip()
        if not text and call_audio.audio_enabled():
            # Транскрипта нет — пробуем распознать видеозапись встречи (Drive).
            rec = m.get(F_MEETING_RECORD)
            url = rec[0] if isinstance(rec, list) and rec else (rec if isinstance(rec, str) else None)
            if url:
                vtext, status = call_audio.transcribe_meeting_video(url)
                if vtext:
                    text = vtext
                    parts.append(f"### Встреча {m.get('title','')} (распознано из видеозаписи)\n{text[:12000]}")
                    continue
                else:
                    parts.append(f"### Встреча {m.get('title','')}: видеозапись есть, но не распознана ({status})")
                    continue
        if text:
            parts.append(f"### Встреча {m.get('title','')}\n{text[:12000]}")
    return "\n\n".join(parts)


def _run_llm(client, user: str) -> dict[str, Any]:
    resp = analyze_llm._call_with_retry(
        client,
        model=analyze_llm.MODEL,
        max_tokens=8000,  # документ-уровень: хронология + цитаты + системные выводы
        temperature=0,
        system=[{"type": "text", "text": AUDIT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    return analyze_llm._parse_llm_json(analyze_llm._response_text(resp)) or {}


def llm_narrative(ctx: dict, sig: dict, score: dict, client=None, call_transcripts=None) -> dict[str, Any]:
    client = client or analyze_llm.get_client()
    base = _build_llm_payload(ctx, sig, score)
    extras = ""
    meetings = _meeting_transcripts(ctx)
    if meetings:
        extras += "\n\nТРАНСКРИПТЫ ВСТРЕЧ:\n" + meetings
    if call_transcripts:
        spoken = call_audio.format_for_llm(call_transcripts)
        if spoken:
            extras += "\n\nРАСШИФРОВКИ ЗВОНКОВ (анализируй диалоги: тон, кто что сказал, возражения, обязательства):\n" + spoken
    parsed = _run_llm(client, base + extras)
    # Раздутый промпт (много расшифровок) иногда даёт пустой/неразборный ответ —
    # повторяем на базовом payload (карточка+сигналы+таймлайн), без аудио/встреч.
    if not parsed and extras:
        parsed = _run_llm(client, base)
    return parsed


# ── Оркестрация ──────────────────────────────────────────────────────────────
def audit_deal(deal_id: int, with_llm: bool = True) -> dict[str, Any] | None:
    ctx = collect_deal_context(deal_id)
    if not ctx:
        return None
    sig = compute_signals(ctx)
    score = recovery_score(sig)
    tags = _failure_tags(sig)

    call_transcripts = call_audio.transcribe_deal_calls(ctx)  # пусто без SCC_AUDIO

    narrative: dict[str, Any] = {}
    if with_llm:
        narrative = llm_narrative(ctx, sig, score, call_transcripts=call_transcripts)
        adj = narrative.get("recommended_adjustment")
        if isinstance(adj, (int, float)) and adj:
            adj = max(-LLM_ADJ_CAP, min(LLM_ADJ_CAP, int(adj)))
            new = max(SCORE_MIN, min(SCORE_MAX, score["score"] + adj))
            score["llm_adjustment"] = adj
            score["score"] = new
            score["band"] = "low" if new < 40 else ("mid" if new < 65 else "hi")
            score["expected_value"] = round(new / 100 * sig["opportunity"]) if sig["opportunity"] else 0

    return {
        "deal_id": deal_id,
        "title": ctx["deal"].get("TITLE"),
        "company": ctx["company"].get("TITLE"),
        "recovery": score,
        "signals": sig,
        "failure_tags": tags,
        "call_recordings": [{k: v for k, v in c.items() if k != "transcript"} | (
            {"transcript_len": len(c.get("transcript", ""))} if c.get("transcript") else {}
        ) for c in call_transcripts],
        "call_transcripts": call_transcripts,
        "narrative": narrative,
    }


def _pp(result: dict) -> None:
    r, n = result["recovery"], result["narrative"]
    print(f"\n=== АУДИТ {result['title']} #{result['deal_id']} ===")
    print(f"Компания: {result['company']}")
    print(f"\nШАНС ВОЗВРАТА: {r['score']}% ({r['band']}) · EV={r['expected_value']:,} ₽"
          + (f" · LLM-поправка {r.get('llm_adjustment'):+d}" if r.get("llm_adjustment") else ""))
    print("Факторы:")
    for f in r["factors"]:
        sign = "＋" if f["weight"] > 0 else "－"
        print(f"  {sign} {f['label']} ({f['weight']:+d})")
    if n.get("summary"):
        print(f"\nРЕЗЮМЕ: {n['summary']}")
        print(f"РЕАЛЬНАЯ ПРИЧИНА: {n.get('real_cause','')}")
    if n.get("chronology"):
        print("\nХРОНОЛОГИЯ:")
        for e in n["chronology"]:
            print(f"  {e.get('date',''):>8}  {e.get('event','')}  — {e.get('who','')}")
    if n.get("key_quotes"):
        print("\nКЛЮЧЕВЫЕ ЦИТАТЫ:")
        for q in n["key_quotes"]:
            print(f"  «{q.get('quote','')}» — {q.get('speaker','')}, {q.get('date','')} → {q.get('why','')}")
    recs = result.get("call_recordings") or []
    if recs:
        ok = sum(1 for r in recs if r.get("status") == "ok")
        print(f"\nЗАПИСИ ЗВОНКОВ: {len(recs)} (расшифровано {ok}, недоступно {len(recs)-ok})")
    if n.get("call_analysis"):
        print("\nАНАЛИЗ ЗВОНКОВ:")
        for ca in n["call_analysis"]:
            print(f"  ☎ {ca.get('date','')}: {ca.get('summary','')}")
            if ca.get("client_tone"): print(f"     тон: {ca['client_tone']}")
            if ca.get("objections"): print(f"     возражения: {'; '.join(ca['objections'])}")
            if ca.get("manager_quality"): print(f"     менеджер: {ca['manager_quality']}")
            if ca.get("commitment"): print(f"     обязательство: {ca['commitment']}")
    print("\nПРОВАЛЫ:")
    for fl in n.get("failures", []):
        sev = fl.get("severity", "")
        print(f"  ✗ [{fl.get('pattern_id', fl.get('tag',''))}/{sev}] {fl.get('title','')} — {fl.get('detail','')[:220]}")
    if n.get("pattern_matches"):
        print("\nПАТТЕРНЫ ОТДЕЛА:")
        for p in n["pattern_matches"]:
            print(f"  ◆ {p.get('pattern_id','')}: {p.get('note','')}")
    print("\nТЕГИ (детерм.):", ", ".join(t["tag"] for t in result["failure_tags"]))
    if n.get("what_went_well"):
        print("\nЧТО ХОРОШО:")
        for w in n["what_went_well"]:
            print(f"  ✓ {w}")
    if n.get("what_would_save_it"):
        print("\nЧТО СПАСЛО БЫ СДЕЛКУ:")
        for w in n["what_would_save_it"]:
            print(f"  ⤷ {w}")
    print("\nСЛЕДУЮЩИЕ ШАГИ:")
    for s in n.get("next_steps", []):
        print(f"  → {s}")
    ft = n.get("first_task") or {}
    if ft:
        print(f"\nПЕРВАЯ ЗАДАЧА: {ft.get('title','')}\n{ft.get('description','')[:600]}")
    if n.get("systemic_conclusions"):
        print("\nСИСТЕМНЫЕ ВЫВОДЫ (сломано → лечить):")
        for c in n["systemic_conclusions"]:
            print(f"  • {c.get('broken','')} → {c.get('fix','')}")
    print(f"\nОБОСНОВАНИЕ БАЛЛА: {n.get('recovery_rationale','')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.audit_engine <deal_id> [--no-llm]")
        sys.exit(1)
    dl = int(sys.argv[1])
    res = audit_deal(dl, with_llm="--no-llm" not in sys.argv)
    if not res:
        print(f"Сделка {dl} не найдена")
        sys.exit(1)
    if "--json" in sys.argv:
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    else:
        _pp(res)
