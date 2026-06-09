"""Планировщик задач из разбора встречи (Phase 2 «умной постановки»).

Отдельный смысловой проход: берёт УЖЕ готовый разбор встречи (вердикт, обязательство,
возражения, сырые next_steps, стадию сделки) и решает, какие максимум 2 рычажных хода
реально стоит поставить менеджеру — с человеческим заголовком, приоритетом и
обоснованием. Транскрипт повторно не читает → проход дешёвый.

Чистые функции (build_planner_message/normalize_plan) тестируемы; plan_tasks делает
LLM-вызов через тот же клиент, что и основной разбор.
"""

from __future__ import annotations

import json
from typing import Any

from .analyze_llm import MODEL, _call_with_retry, _parse_llm_json, _response_text, _system

MAX_PLANNED = 2  # жёсткий потолок задач на встречу

PLANNER_SYSTEM = """\
Ты — руководитель отдела продаж. По итогу проведённой встречи ставишь менеджеру
МАКСИМУМ 2 задачи — только те, без которых сделка не двинется. Лучше 1 точная, чем
3 шаблонные. Отвечай строго JSON-объектом {"tasks": [...]}, без markdown.

Каждая задача:
- title — короткий человеческий императив С КОНКРЕТИКОЙ из этой встречи, не пересказ
  и не канцелярит. Плохо: «Получить обратную связь». Хорошо: «Дожать клиента по смете
  на контекст — он обещал ответ к среде».
- type — send (отправить клиенту) | await (ждём ответ/доступ/данные от клиента) |
  internal (наша внутренняя работа: расчёт, анализ рынка, проверка) | discuss
  (обсудить/защитить с клиентом) | schedule (созвон/встреча на конкретную дату).
- owner — manager (ответственный за сделку) или internal (внутренний отдел/продакшн),
  если действие не менеджера.
- deadline — срок СЛОВАМИ из договорённостей встречи («к среде», «через неделю»,
  конкретная дата); если не обсуждали — null.
- significance — high только если без шага сделка встанет; иначе medium.
- rationale — одна фраза: почему это двигает сделку (опираясь на сказанное на встрече).
- control — true ТОЛЬКО для одного ключевого шага (уйдёт на контроль постановщику);
  для остального и для всех await — false.

Жёсткие правила:
1. НЕ БОЛЬШЕ 2 задач. Если рычажный ход один — верни одну. Если содержательных нет — [].
2. Группируй однотипное в ОДНУ: все «отправить …» = одна задача (перечисли что внутри
   title); все «получить от клиента …» = одна.
3. НЕ ставь «подготовить/сформировать КП» — это автозадача при переходе на стадию КП.
   («Отправить КП», «защитить КП» — можно.)
4. Выкидывай пустое и очевидное: «обсудить детали», «быть на связи», «уточнить» без
   конкретного предмета — это НЕ задача.
5. «Ждём ответа клиента» ставь как ОДНУ await-задачу-напоминание и только если это
   ключевой блокер; не размножай по каждому пункту, который ждём.
6. Опирайся на стадию сделки: на ранней — двигай к КП/защите; на поздней — к решению."""


def build_planner_message(analysis: dict[str, Any], *, deal_title: str | None, stage: str | None) -> str:
    """Компактный вход планировщику из готового разбора (без транскрипта)."""
    payload = {
        "сделка": deal_title or "—",
        "стадия": stage or "—",
        "тип_встречи": analysis.get("meeting_type"),
        "оценка": analysis.get("score"),
        "вердикт": analysis.get("verdict"),
        "обязательство_клиента": analysis.get("commitment"),
        "бюджет_назван": analysis.get("budget_named"),
        "возражения": analysis.get("objections"),
        "цитата_клиента": analysis.get("client_quote"),
        "наблюдения": analysis.get("observations"),
        # сырые шаги разбора — как материал, планировщик их пересобирает и сокращает
        "черновые_шаги": analysis.get("next_steps") or analysis.get("next_step"),
    }
    return (
        "Разбор встречи (JSON ниже). Поставь максимум 2 задачи менеджеру строго по правилам.\n\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


_TYPES = {"send", "await", "internal", "discuss", "schedule"}


def normalize_plan(parsed: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Валидирует ответ планировщика: ≤2 задач, обязателен непустой title."""
    if not isinstance(parsed, dict):
        return []
    raw = parsed.get("tasks")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for t in raw:
        if not isinstance(t, dict):
            continue
        title = str(t.get("title") or "").strip()
        if not title:
            continue
        typ = str(t.get("type") or "").strip().lower()
        out.append(
            {
                "title": title,
                "type": typ if typ in _TYPES else "internal",
                "owner": str(t.get("owner") or "manager").strip().lower(),
                "deadline": (str(t.get("deadline")).strip() if t.get("deadline") else None),
                "significance": "high" if str(t.get("significance")).lower() == "high" else "medium",
                "rationale": str(t.get("rationale") or "").strip(),
                "control": bool(t.get("control")),
            }
        )
        if len(out) >= MAX_PLANNED:
            break
    # контроль — максимум на одной задаче
    seen_control = False
    for t in out:
        if t["control"] and not seen_control:
            seen_control = True
        elif t["control"]:
            t["control"] = False
    return out


def plan_tasks(analysis: dict[str, Any], *, deal_title: str | None, stage: str | None, client) -> list[dict[str, Any]]:
    """LLM-проход: готовый разбор → ≤2 отобранных задачи. Пустой список при отсутствии
    содержательных шагов или ошибке парсинга (тогда вызывающий код фолбэчит на старую
    логику next_steps)."""
    response = _call_with_retry(
        client,
        model=MODEL,
        max_tokens=1200,
        temperature=0,
        system=_system(PLANNER_SYSTEM),
        messages=[{"role": "user", "content": build_planner_message(analysis, deal_title=deal_title, stage=stage)}],
    )
    return normalize_plan(_parse_llm_json(_response_text(response)))
