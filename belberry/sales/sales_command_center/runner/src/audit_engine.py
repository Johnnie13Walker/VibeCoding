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

import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

from . import analyze_llm, bx_client
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
SCORE_BASE = 30
W_FRESH_CONTACT = 10       # последний контакт ≤14 дней — кто-то ещё на связи
W_DM_LEVER_UNTRIED = 12    # до ЛПР не дошли, но есть его контакт → ясный непройденный путь
W_HAS_BUDGET = 5           # у компании есть оборот / в сделке есть сумма
W_WARM_HISTORY = 5         # были встречи/брифы — нас знают
P_CONTACT_LOST = -8        # контактное лицо ушло из компании
P_KP_NO_DEFENSE = -5       # КП отправлено, но не защищено (знаем дыру, чинится)
P_DM_BUDGET_REJECTION = -25  # ЛПР лично сказал «нет бюджета» — рычаг исчерпан
P_COMPETITOR_WON = -30     # ушли к конкуренту
P_STALE_90 = -15           # без контакта >90 дней
P_HANDOVER_2PLUS = -5      # 2+ передачи между менеджерами
SCORE_MIN, SCORE_MAX = 5, 90  # никогда не 0/100 — честность: абсолютов не бывает
LLM_ADJ_CAP = 10           # LLM может подвинуть балл максимум на ±10


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

    return {
        "deal": deal, "company": company, "contact": contact,
        "meetings": meetings, "briefs": briefs, "kp": kp,
        "activities": acts, "timeline": timeline,
    }


# ── Детерминированные сигналы ────────────────────────────────────────────────
def compute_signals(ctx: dict[str, Any]) -> dict[str, Any]:
    deal = ctx["deal"]
    acts, timeline = ctx["activities"], ctx["timeline"]
    full_text = " ".join(_strip_bb(c.get("COMMENT", "")) for c in timeline)
    full_text += " " + (deal.get(F_DEAL_MGR_COMMENT) or "")
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
    f(days is not None and days <= 14, W_FRESH_CONTACT, "Свежий контакт (≤14 дней)")
    dm_untried = bool(sig.get("dm_phone")) and not sig["had_defense"]
    f(dm_untried, W_DM_LEVER_UNTRIED, "ЛПР не вовлечён — рычаг не нажат", kind="opp")
    f(sig["company_revenue"] > 0 or sig["opportunity"] > 0, W_HAS_BUDGET, "У компании есть бюджет")
    f(sig["meetings_total"] > 0 or sig["briefs_total"] > 0, W_WARM_HISTORY, "Тёплая история (встречи/брифы)")
    f(sig["contact_lost"], P_CONTACT_LOST, "Контактное лицо ушло")
    f(sig["kp_sent"] and not sig["had_defense"], P_KP_NO_DEFENSE, "КП не защищено перед ЛПР")
    # «нет бюджета» от не-ЛПР (защиты не было) — мягкий минус; от ЛПР — жёсткий
    f(sig["budget_objection"] and sig["had_defense"], P_DM_BUDGET_REJECTION, "ЛПР отказал по бюджету")
    f(sig["competitor_won"], P_COMPETITOR_WON, "Ушли к конкуренту")
    f(days is not None and days > 90, P_STALE_90, "Без контакта >90 дней")
    f(sig["handover_count"] >= 2, P_HANDOVER_2PLUS, "2+ передачи менеджера")

    raw = score
    score = max(SCORE_MIN, min(SCORE_MAX, score))
    band = "low" if score < 40 else ("mid" if score < 65 else "hi")
    ev = round(score / 100 * sig["opportunity"]) if sig["opportunity"] else 0
    return {"score": score, "raw": raw, "band": band, "expected_value": ev, "factors": factors}


# ── LLM-нарратив (балл уже посчитан, LLM его объясняет) ───────────────────────
AUDIT_SYSTEM = """
Ты — опытный коммерческий директор агентства Belberry (медицинский и B2B маркетинг).
Тебе дают данные ОДНОЙ сделки: карточку, хронологию (timeline/звонки/Wazzup), брифы, КП,
встречи (с транскриптами, если есть) и УЖЕ ПОСЧИТАННЫЙ детерминированный «шанс возврата».

Твоя задача — дать ЧЕСТНЫЙ разбор. Балл возврата НЕ переписывай — он посчитан кодом.
Объясни его словами и, если видишь сильный нюанс из разговоров, предложи поправку
recommended_adjustment в пределах [-10..10] с обоснованием (по умолчанию 0).
Если шансов мало — так и пиши, без приукрашивания. Опирайся на факты, цитируй дословно.

Верни строго JSON без markdown:
{
  "summary": "2-4 фразы: что за сделка, почему встала, реальная причина (не метка)",
  "real_cause": "корневая причина одной фразой",
  "verdict_band_text": "короткая характеристика шанса возврата (напр. 'низкий — но один рычаг не нажат')",
  "failures": [{"title": "провал", "detail": "что именно, с цитатой если есть", "tag": "KP_NO_CARD|NO_DEFENSE|HANDOVER_NO_CONTEXT|NON_DM_CONTACT|STAGE_VS_REALITY|BRIEF_SPRAY|BUDGET_LABEL|COMPETITOR|OTHER"}],
  "what_went_well": ["что сделали хорошо — честно, чтобы разбор не был тенденциозным"],
  "next_steps": ["конкретные шаги к возврату, по порядку"],
  "first_task": {"title": "заголовок первой задачи ответственному", "description": "что сказать/сделать — готовый план звонка/действия, можно с под-пунктами"},
  "recovery_rationale": "почему балл именно такой и что подняло бы его",
  "recommended_adjustment": 0
}
"""


def _build_llm_payload(ctx: dict, sig: dict, score: dict) -> str:
    deal = ctx["deal"]
    tl = []
    for c in ctx["timeline"]:
        t = _strip_bb(c.get("COMMENT", ""))
        if t:
            tl.append(f"[{c.get('CREATED','')[:10]}] {t[:600]}")
    payload = {
        "deal": {
            "id": deal.get("ID"), "title": deal.get("TITLE"),
            "stage": sig["stage_id"], "death_stage": sig["death_stage"],
            "manager_comment": deal.get(F_DEAL_MGR_COMMENT),
            "opportunity": sig["opportunity"], "company_revenue": sig["company_revenue"],
        },
        "company": ctx["company"].get("TITLE"),
        "contact": {"name": f"{ctx['contact'].get('NAME','')} {ctx['contact'].get('LAST_NAME','')}".strip(),
                    "post": ctx["contact"].get("POST")},
        "decision_maker": {"name": sig.get("dm_name"), "phone": sig.get("dm_phone")},
        "signals": sig,
        "recovery_score": {"score": score["score"], "factors": score["factors"]},
        "briefs": [{k: v for k, v in b.items() if isinstance(v, str) and v and not k.startswith("ufCrm20_175")}
                   for b in ctx["briefs"]][:3],
        "timeline": tl,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _meeting_transcripts(ctx: dict) -> str:
    if not ctx["meetings"]:
        return ""
    try:
        enriched = enrich_meetings({"m": ctx["meetings"]}, refresh=True)
    except Exception:
        return ""
    parts = []
    for m in ctx["meetings"]:
        tr = enriched.get(int(m["id"]), {})
        text = (tr.get("text") or "").strip()
        if text:
            parts.append(f"### Встреча {m.get('title','')}\n{text[:8000]}")
    return "\n\n".join(parts)


def llm_narrative(ctx: dict, sig: dict, score: dict, client=None) -> dict[str, Any]:
    client = client or analyze_llm.get_client()
    user = _build_llm_payload(ctx, sig, score)
    transcripts = _meeting_transcripts(ctx)
    if transcripts:
        user += "\n\nТРАНСКРИПТЫ ВСТРЕЧ:\n" + transcripts
    resp = analyze_llm._call_with_retry(
        client,
        model=analyze_llm.MODEL,
        max_tokens=4000,
        temperature=0,
        system=[{"type": "text", "text": AUDIT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    parsed = analyze_llm._parse_llm_json(analyze_llm._response_text(resp))
    return parsed or {}


# ── Оркестрация ──────────────────────────────────────────────────────────────
def audit_deal(deal_id: int, with_llm: bool = True) -> dict[str, Any] | None:
    ctx = collect_deal_context(deal_id)
    if not ctx:
        return None
    sig = compute_signals(ctx)
    score = recovery_score(sig)
    tags = _failure_tags(sig)

    narrative: dict[str, Any] = {}
    if with_llm:
        narrative = llm_narrative(ctx, sig, score)
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
    print("\nПРОВАЛЫ:")
    for fl in n.get("failures", []):
        print(f"  ✗ {fl.get('title','')} [{fl.get('tag','')}] — {fl.get('detail','')[:160]}")
    print("\nТЕГИ (детерм.):", ", ".join(t["tag"] for t in result["failure_tags"]))
    print("\nСЛЕДУЮЩИЕ ШАГИ:")
    for s in n.get("next_steps", []):
        print(f"  → {s}")
    ft = n.get("first_task") or {}
    if ft:
        print(f"\nПЕРВАЯ ЗАДАЧА: {ft.get('title','')}\n{ft.get('description','')[:400]}")
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
