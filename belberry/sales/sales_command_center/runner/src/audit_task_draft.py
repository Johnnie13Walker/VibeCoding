"""Умная постановка задачи под КОНКРЕТНОГО менеджера, который делает следующий шаг.

Генерация в ТРИ прохода (чтобы не скатываться в шаблон):
  1. СТРАТЕГ — читает, как сделка умерла (failure_tags + real_cause + слова клиента),
     выбирает ОДНУ «пьесу» реанимации под причину смерти и придумывает угол под эту сделку.
  2. СЦЕНАРИСТ — по замыслу пишет короткий план звонка под менеджера (пол/имя/легенда).
  3. КРИТИК — проверяет по рубрике (нет канцелярита/продажного жаргона, привязка к
     конкретике, есть трипваер/шаг) и при слабом результате переписывает.

Веб (страница аудита) дёргает синхронно при выборе ответственного. На вход — id аудита
и id выбранного менеджера; на выход — JSON {title, description}.

Запуск:  python -m src.audit_task_draft <audit_id> <responsible_bitrix_id>
Печатает в stdout одну строку JSON.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import analyze_llm, bx_client

# ── Пьесы реанимации: стратег выбирает ОДНУ под причину смерти сделки ──────────
STRATEGIST_SYSTEM = """Ты — стратег по реанимации остывших сделок (не продавец). Тебе дают
сделку: как она умерла (failure_tags, real_cause), что спасло бы (what_would_save_it),
ДОСЛОВНЫЕ слова клиента, ЛПР. Твоя работа — выбрать ОДИН самый сильный ход и придумать
конкретный угол ПОД ЭТУ сделку. НЕ пиши скрипт звонка. Верни СТРОГО JSON:
{"play": "...", "objective": "...", "angle": "...", "tripwire": "...", "why": "..."}.

ПАЛИТРА ПЬЕС — выбери одну под причину смерти:
- access_tripwire — сделку держит недостающий ВХОД (доступ к Метрике/аналитике). Ход: дать
  ценность вперёд. Проси гостевой доступ на чтение на НЕСКОЛЬКО ДНЕЙ, взамен — РАЗВЁРНУТАЯ
  веб-аналитика; без брифов и обязательств; рамка «дайте показать возможности, понравится —
  продолжим, нет — разойдёмся». Сначала польза, потом деньги.
- value_reframe — умерла на ЦЕНЕ/«дорого». Ход: не скидка, а пересборка ценности под их
  реальную боль / другой объём / иной порядок работ.
- found_a_gap — ушла в ТИШИНУ. Ход: честно «посмотрел и зацепился за конкретную дыру у вас» —
  предметное наблюдение, которое стоит проверить, без воды.
- competitor_insurance — выбрали КОНКУРЕНТА. Ход: не спорить, а «страховка на старте с другим
  подрядчиком» — что проверить до договора, где красиво звучит, но не даёт результата.
- dm_bypass — работали НЕ С ЛПР / защита не дошла. Ход: повод дать материал, который удобно
  показать именно ЛПР, и так выйти на него.
- fresh_proof — есть СВЕЖИЙ релевантный кейс в их нише. Ход: зайти с конкретным результатом
  у похожего клиента, не с «у нас большой опыт».

ПРАВИЛА:
- objective — РЕАЛЬНАЯ цель звонка (снять блокер: получить доступ/выйти на ЛПР/пересобрать
  оффер), а НЕ «договориться о встрече». Встреча — лишь средство.
- angle — конкретный неочевидный угол захода именно по этой сделке (из её фактуры, не общий).
- tripwire — если ход про обмен ценности на вход, опиши его; иначе пустая строка.
- Опирайся на ДОСЛОВНЫЕ слова клиента, если они есть. Не выдумывай фактов, которых нет.
"""

SCRIPTER_SYSTEM = """Ты пишешь КОРОТКИЙ чёткий план звонка, ДОСЛОВНО воплощая ЗАМЫСЕЛ стратега.
Тебе дают: strategy (play/objective/angle/tripwire), менеджера, фактуру. Верни СТРОГО JSON:
{"title": "...", "description": "..."}.

ГЛАВНОЕ: план обязан ИСПОЛНЯТЬ strategy.angle и вести к strategy.objective. Открытие — это
КОНКРЕТНЫЙ угол из strategy.angle, а не общая фраза («посмотрела историю», «покажу, что видно»).
Если strategy.tripwire непустой — последний шаг просит ИМЕННО его, с явной выгодой взамен.
ЗАПРЕЩЕНО упрощать замысел до рядового «давайте созвонимся на 20 минут, покажу наблюдения» —
это потеря угла, ради которого всё и затевалось.

ФОРМАТ description (жёстко):
- Пронумерованный план: 4–6 пунктов. Каждый — 1, максимум 2 коротких предложения.
- В каждом пункте: что сделать + готовая фраза в кавычках (что менеджер скажет вслух).
- Пункт 1 = ОТКРЫТИЕ по strategy.angle. Последний пункт = strategy.objective (трипваер, если есть;
  иначе конкретный следующий шаг по сути пьесы + 2 слота времени).
- Никаких абзацев-простыней и мета-болтовни «зачем так».

ЗАПРЕЩЕНО:
- Проговаривать очевидное: «далеко от оплаты», «застряли», «давно не общались».
- Язык продавца: «ценность», «крючок», «вывести на ЛПР», «снять возражение», «довести до
  результата», «адресно выйти», «снимаю тормоз», «покажу 3 блока за 20 минут».
- Натужные шутки и выдавленные метафоры («археология переписки», «секретные тоннели») — плоско.
  Юмор только если реально сухой и острый; сомневаешься — без шуток, но умно.
- Обещать то, чего без входа не сделать (например «покажу разбор по Метрике», если доступа нет).

ОБЯЗАТЕЛЬНО:
- ОТ ПЕРВОГО ЛИЦА в роде менеджера: gender M=мужской («заметил, подумал»), F=женский
  («заметила, подумала»). Имя — manager.name.
- handover.is=true: что сделку ведёт теперь этот менеджер (не handover.prev) — ОДНОЙ фразой.
- title — короткий и острый, без «Услуги по».
"""

CRITIC_SYSTEM = """Ты — придирчивый редактор. Проверь план звонка по рубрике и при слабом
результате ПЕРЕПИШИ его (тот же формат и замысел, только живее и чище). Верни СТРОГО JSON:
{"ok": true} ЕСЛИ всё хорошо, ИНАЧЕ {"ok": false, "title": "...", "description": "..."}.

Рубрика (любое нарушение = ok:false и переписать):
- План НЕ исполняет strategy.angle: открытие общее («посмотрела историю», «покажу, что видно»),
  угол стратега потерян, или цель свелась к рядовому «созвону на 20 минут» вместо strategy.objective.
  Если в strategy.tripwire что-то есть, а в плане его нет — тоже ok:false.
- Есть канцелярит или язык продавца («ценность», «довести до результата», «адресно выйти»,
  «снимаю тормоз», «покажу 3 блока за 20 минут»).
- Проговаривается очевидное («далеко от оплаты», «застряли», «давно не общались»).
- Натужные шутки/метафоры.
- Длинно/простынёй, а не короткими пунктами; неверный род менеджера.
Переписывая — верни КОНКРЕТНЫЙ угол стратега и его цель, сохрани пол менеджера, короче и острее.
"""


def _user(uid: int) -> dict[str, Any]:
    r = bx_client.call("user.get", {"ID": uid}).get("result") or []
    return r[0] if r else {}


def _name(u: dict) -> str:
    return f"{u.get('LAST_NAME', '')} {u.get('NAME', '')}".strip() or f"id{u.get('ID', '')}"


def _llm_json(client, system: str, payload: dict, max_tokens: int, temperature: float) -> dict | None:
    """Один LLM-проход с JSON-ответом. Возвращает dict или None."""
    resp = analyze_llm._call_with_retry(
        client, model=analyze_llm.MODEL, max_tokens=max_tokens, temperature=temperature,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
    )
    return analyze_llm._parse_llm_json(analyze_llm._response_text(resp))


def draft(audit_id: int, responsible_id: int) -> dict[str, str]:
    from . import db

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT deal_id, title, result FROM deal_audits WHERE id=%s", (audit_id,))
        row = cur.fetchone()
    if not row:
        return {"title": "", "description": ""}
    _deal_id, title, result = row
    result = result or {}
    n = result.get("narrative") or {}
    sig = result.get("signals") or {}

    new_user = _user(responsible_id)
    gender = (new_user.get("PERSONAL_GENDER") or "").upper()  # 'M' | 'F' | ''
    manager_name = _name(new_user)

    # Менеджер на момент аудита = последний в цепочке ответственных по активностям.
    chain = sig.get("responsibles_chain") or []
    prev_id = None
    for x in reversed(chain):
        try:
            prev_id = int(x)
            break
        except (TypeError, ValueError):
            continue
    prev_name = _name(_user(prev_id)) if prev_id else None
    is_handover = bool(prev_id) and prev_id != responsible_id

    # Фактура сделки для стратега: причина смерти, теги провалов, дословные слова клиента.
    deal_ctx = {
        "deal": title,
        "real_cause": n.get("real_cause"),
        "summary": n.get("summary"),
        "failure_tags": [t.get("label") for t in (result.get("failure_tags") or []) if t.get("label")],
        "what_would_save_it": n.get("what_would_save_it"),
        "next_steps": n.get("next_steps"),
        "client_quotes": [q.get("quote") for q in (n.get("key_quotes") or []) if q.get("quote")][:5],
        "decision_maker": {"name": sig.get("dm_name"), "phone": sig.get("dm_phone")},
    }
    manager = {"name": manager_name, "gender": gender or "не указан"}
    handover = {"is": is_handover, "prev": prev_name}

    client = analyze_llm.get_client()

    # 1) Стратег: выбрать пьесу под причину смерти и угол под эту сделку.
    strategy = _llm_json(client, STRATEGIST_SYSTEM, {"deal_context": deal_ctx},
                         max_tokens=600, temperature=0.8) or {}

    # 2) Сценарист: по замыслу написать короткий план под менеджера.
    draft_out = _llm_json(client, SCRIPTER_SYSTEM,
                          {"strategy": strategy, "manager": manager, "handover": handover,
                           "deal_context": deal_ctx},
                          max_tokens=900, temperature=0.8) or {}
    title_out = str(draft_out.get("title") or "").strip()
    desc_out = str(draft_out.get("description") or "").strip()
    if not title_out:
        return {"title": "", "description": ""}

    # 3) Критик: проверить по рубрике и при слабом результате переписать.
    verdict = _llm_json(client, CRITIC_SYSTEM,
                        {"plan": {"title": title_out, "description": desc_out},
                         "strategy": strategy, "manager": manager},
                        max_tokens=900, temperature=0.5) or {}
    if verdict.get("ok") is False and verdict.get("title"):
        title_out = str(verdict.get("title")).strip()
        desc_out = str(verdict.get("description") or "").strip()

    return {"title": title_out, "description": desc_out}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(json.dumps({"error": "usage: audit_task_draft <audit_id> <responsible_id>"}))
        return 2
    try:
        res = draft(int(argv[0]), int(argv[1]))
    except Exception as e:  # noqa: BLE001 — веб получит ошибку и оставит шаблон
        print(json.dumps({"error": str(e)[:300]}, ensure_ascii=False))
        return 1
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
