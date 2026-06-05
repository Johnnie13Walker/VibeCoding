"""ПРОТОТИП «КД-мозг»: глубокий разбор сделки целиком (брифинг → защита КП).
Читает оба транскрипта встреч сделки, анализирует как коммерческий директор,
ПЕЧАТАЕТ результат (без записи в БД). Запуск на проде (LLM-ключ в окружении):

    python -m src.deal_brain_proto 23596 16326
"""

import json
import sys

from . import analyze_llm, bx_client
from .collect import _fetch_all, SEL_1048
from .enrich import enrich_meetings

CD_SYSTEM = """
Ты — опытный коммерческий директор агентства Belberry (медицинский и B2B маркетинг:
SEO, контекстная реклама, веб-разработка, Strapi, GEO/маркетплейсы, ORM/репутация, SMM).
Тебе дают транскрипты ДВУХ встреч по ОДНОЙ сделке: сначала БРИФИНГ (первичная встреча —
выявление потребности), затем ЗАЩИТА КП. Проанализируй сделку ЦЕЛИКОМ, как коммерческий
директор. Опирайся ТОЛЬКО на транскрипты, цитируй дословно, ничего не выдумывай.

Верни строго JSON без markdown:
{
  "client": "кто клиент, ниша, ситуация — 1-2 фразы",
  "real_needs": [{"need": "реальная потребность", "pain": "боль за ней", "evidence": "цитата/факт из встречи", "uncovered_at_briefing": true}],
  "main_pain": "ГЛАВНАЯ боль клиента твоими словами",
  "briefing_depth": {"score": 7, "note": "насколько глубоко менеджер выявил потребности; что упустил"},
  "kp_alignment": "соответствует|частично|мимо",
  "kp_alignment_note": "что из реальных потребностей легло в КП, а что пропущено или притянуто за уши",
  "briefing_to_defense": "использовал ли менеджер инсайты брифинга в защите КП; где порвалась логика",
  "missed": ["упущенная потребность / недопродажа / предложен не тот продукт"],
  "commercial_verdict": "стоило ли вообще готовить это КП; реальная вероятность закрытия; что сделал бы ты как КД иначе",
  "deal_health": 6,
  "next_action": "конкретно что делать с этой сделкой дальше"
}
"""


def _fetch_deal_meetings(deal_id: int, bx=None) -> list[dict]:
    return _fetch_all(
        bx,
        "crm.item.list",
        {"entityTypeId": 1048, "filter": {"parentId2": deal_id, "stageId": "DT1048_24:SUCCESS"}, "select": SEL_1048},
        idfield="id",
    )


def _mtype(title: str | None) -> str:
    t = (title or "").lower()
    return "защита" if "защ" in t else ("брифинг" if "бриф" in t else "встреча")


def analyze_deal(deal_id: int, bx=None) -> dict | None:
    meetings = _fetch_deal_meetings(deal_id, bx)
    if not meetings:
        print(f"\n=== СДЕЛКА {deal_id}: встреч нет ===")
        return None
    enriched = enrich_meetings({"meet_day": meetings}, bx=bx, refresh=True)
    parts = []
    title = meetings[0].get("title") or str(deal_id)
    for m in sorted(meetings, key=lambda a: a.get("ufCrm16_1751009238") or ""):
        mid = int(m["id"])
        tr = enriched.get(mid, {})
        text = (tr.get("text") or "").strip()
        if not text:
            continue
        parts.append(f"### Встреча: {_mtype(m.get('title'))} ({m.get('ufCrm16_1751009238','')})\n{text}")
    if not parts:
        print(f"\n=== СДЕЛКА {deal_id} ({title}): транскриптов нет ===")
        return None

    client = analyze_llm.get_client()
    response = client.messages.create(
        model=analyze_llm.MODEL,
        max_tokens=4000,
        temperature=0,
        system=[{"type": "text", "text": CD_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"Сделка: {title}\n\n" + "\n\n".join(parts)}],
    )
    raw_text = response.content[0].text
    parsed = analyze_llm._parse_llm_json(raw_text)
    return {"deal_id": deal_id, "title": title, "meetings": len(parts), "analysis": parsed, "raw": raw_text}


def _pp(deal_id: int, bx=None) -> None:
    out = analyze_deal(deal_id, bx)
    if not out:
        return
    a = out["analysis"]
    print(f"\n{'='*70}\nСДЕЛКА {out['deal_id']} — {out['title']}  (встреч с транскриптом: {out['meetings']})\n{'='*70}")
    if not a:
        print("LLM вернул невалидный JSON. Сырой ответ:\n", out["raw"][:2000])
        return
    print(f"\nКЛИЕНТ: {a.get('client','')}")
    print(f"\nГЛАВНАЯ БОЛЬ: {a.get('main_pain','')}")
    print("\nРЕАЛЬНЫЕ ПОТРЕБНОСТИ:")
    for n in a.get("real_needs", []):
        flag = "✓ на брифинге" if n.get("uncovered_at_briefing") else "✗ упущено на брифинге"
        print(f"  • {n.get('need','')} — боль: {n.get('pain','')} [{flag}]")
        if n.get("evidence"):
            print(f"      «{n.get('evidence')}»")
    bd = a.get("briefing_depth", {})
    print(f"\nГЛУБИНА БРИФИНГА: {bd.get('score','—')}/10 — {bd.get('note','')}")
    print(f"\nКП vs ПОТРЕБНОСТИ: {a.get('kp_alignment','—')} — {a.get('kp_alignment_note','')}")
    print(f"\nСВЯЗКА БРИФИНГ→ЗАЩИТА: {a.get('briefing_to_defense','')}")
    if a.get("missed"):
        print("\nУПУЩЕНО:")
        for m in a["missed"]:
            print(f"  • {m}")
    print(f"\nКОММЕРЧЕСКИЙ ВЕРДИКТ: {a.get('commercial_verdict','')}")
    print(f"\nЗДОРОВЬЕ СДЕЛКИ: {a.get('deal_health','—')}/10")
    print(f"СЛЕДУЮЩИЙ ШАГ: {a.get('next_action','')}")


def main() -> None:
    bx_client.ensure_token_fresh()
    for arg in sys.argv[1:]:
        _pp(int(arg))


if __name__ == "__main__":
    main()
