"""Умная постановка задачи под КОНКРЕТНОГО менеджера, который делает следующий шаг.

Веб (страница аудита) дёргает синхронно при выборе ответственного. На вход — id аудита
и id выбранного менеджера; на выход — JSON {title, description}:
- речь от первого лица в роде менеджера (учитываем пол: «отправлял/отправляла»);
- если менеджер ПЕРЕХВАТЫВАЕТ сделку у другого — правдоподобная легенда захвата контакта;
- точно «на что нажимать» — рычаги из аудита (непройденная защита/ЛПР, незакрытая боль).

Запуск:  python -m src.audit_task_draft <audit_id> <responsible_bitrix_id>
Печатает в stdout одну строку JSON.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import analyze_llm, bx_client

DRAFT_SYSTEM = """Ты придумываешь, КАК по-человечески и НЕОЖИДАННО переоткрыть остывшую
сделку. Не как менеджер по продажам — а как умный человек, который реально вник в эту
конкретную ситуацию и нашёл небанальный повод позвонить. Менеджер скажет это вживую.
Верни СТРОГО JSON без markdown: {"title": "...", "description": "..."}.

ОБРАЗ МЫШЛЕНИЯ
- Сначала ДУМАЙ: что в этой сделке/нише/клиенте есть НЕОЧЕВИДНОГО, за что можно зацепиться
  оригинально? Какой неожиданный угол, наблюдение или честная шутка снимет защиту и вызовет
  интерес? Опирайся на конкретику: real_cause, what_would_save_it, слова клиента (key_quotes),
  их сайт/нишу. Заход должен быть РАЗНЫМ каждый раз — это твоя выдумка, а не шаблон.
- Допустим лёгкий юмор / самоирония — чтобы звучало как живой человек, а не отдел продаж.

ЧЕГО НЕ ДЕЛАТЬ (это убивает заход)
- НЕ проговаривай очевидное: что сделка «далеко от оплаты», что «застряли», что «давно не
  общались», что «решение ушло на согласование». Клиент это и так знает — звучит как скрипт.
- НЕ говори языком продавца. Запрещено: «ценность», «крючок», «вывести на ЛПР», «снять
  возражение», «предложить нормальный ход», «короткая встреча 15–20 минут, покажу 3 блока»,
  «довести до результата», «адресно выйти», «снимаю тормоз», «я как раз копаюсь в таких задачах».
  Никаких заголовков-ремарок в духе «Открытие-крючок», «Продать ценность» — просто живая речь.
- Не льсти шаблонно и не дави. Веди себя как равный, которому реально интересна их задача.

ЧТО ДОЛЖНО БЫТЬ
- ОТ ПЕРВОГО ЛИЦА в роде менеджера. Пол: gender M=мужской («заметил, подумал, позвонил»),
  F=женский («заметила, подумала, позвонила»). Имя — manager.name.
- handover.is=true (сделку ведёт уже не <handover.prev>, а этот менеджер): объясни это вскользь
  и по-человечески, без драмы и без «передали, чтобы довести». Можно с юмором.
- Сильное, неожиданное ОТКРЫТИЕ (1–2 фразы) — самое важное. Дальше — естественный ход разговора
  и пара живых ответов, если клиент отнекивается («не интересно», «уже с другими»).
- Заверши конкретным следующим шагом, но НЕ канцелярски: предложи созвон по-человечески, 2 слота.
- Реплики клиенту давай в кавычках, готовыми к произнесению. Между ними — короткая логика (зачем).
- title — короткий, живой, с характером (можно с искрой), без «Услуги по».
- Пиши плотно и умно. Лучше меньше, да метко: один блестящий заход дороже пяти вялых шагов.
"""


def _user(uid: int) -> dict[str, Any]:
    r = bx_client.call("user.get", {"ID": uid}).get("result") or []
    return r[0] if r else {}


def _name(u: dict) -> str:
    return f"{u.get('LAST_NAME', '')} {u.get('NAME', '')}".strip() or f"id{u.get('ID', '')}"


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

    payload = {
        "deal": title,
        "recovery": {"score": sig.get("score") or result.get("recovery", {}).get("score"),
                     "real_cause": n.get("real_cause"), "summary": n.get("summary")},
        "what_would_save_it": n.get("what_would_save_it"),
        "next_steps": n.get("next_steps"),
        "key_quotes": [q.get("quote") for q in (n.get("key_quotes") or [])][:4],
        "decision_maker": {"name": sig.get("dm_name"), "phone": sig.get("dm_phone")},
        "manager": {"name": manager_name, "gender": gender or "не указан"},
        "handover": {"is": is_handover, "prev": prev_name},
    }
    client = analyze_llm.get_client()
    resp = analyze_llm._call_with_retry(
        client, model=analyze_llm.MODEL, max_tokens=1500, temperature=0.9,  # креатив, не детерминизм
        system=[{"type": "text", "text": DRAFT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
    )
    out = analyze_llm._parse_llm_json(analyze_llm._response_text(resp)) or {}
    return {"title": str(out.get("title") or "").strip(),
            "description": str(out.get("description") or "").strip()}


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
