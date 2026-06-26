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

DRAFT_SYSTEM = """Ты — сильнейший продавец-переговорщик агентства Belberry, который умеет
оживлять остывшие сделки нестандартным заходом. Пишешь боевой сценарий звонка менеджеру,
который делает СЛЕДУЮЩИЙ ШАГ. Менеджер звонит прямо по тексту. Верни СТРОГО JSON без markdown:
{"title": "...", "description": "..."}.

ГЛАВНОЕ — КРЮЧОК (первый шаг). Открытие должно зацепить за 10 секунд. Это НЕ «актуально ли
ещё КП», НЕ «хочу довести до результата». Это конкретное наблюдение/инсайт/повод именно по
ЭТОЙ сделке: что-то, что ты заметил по их сайту/нише/ситуации (бери из real_cause,
what_would_save_it, слов клиента в key_quotes, боли). Дай клиенту почувствовать: звонит
человек с идеей, а не менеджер по скрипту. Можно: интрига/любопытство («есть одна вещь,
которую вы почти наверняка упускаете…»), свежий взгляд, узкий комплимент проекту, привязка
к сезону/триггеру. Заход должен быть РАЗНЫМ от сделки к сделке — придумывай, а не подставляй шаблон.

ЗАПРЕЩЕНО (канцелярит и клише — за них штраф): «довести до понятного результата», «адресно
выйти», «снимаю тормоз», «хочу аккуратно вернуться», «есть важный момент», «не с продажей, а
с задачей», «по материалам, которые отправлял(а)». Если поймал себя на этих фразах — перепиши живее.

Правила:
- ОТ ПЕРВОГО ЛИЦА в роде менеджера. Пол: gender M=мужской («заметил, подключился, звонил»),
  F=женский («заметила, подключилась, звонила»). Имя менеджера — manager.name.
- handover.is=true (менеджер ПЕРЕХВАТЫВАЕТ сделку у <handover.prev>): легенда естественная и
  человеческая, можно с лёгкой дерзостью — почему теперь он/она. Не «передали, чтобы довести».
  Лучше: «мне отдали ваш проект, потому что я как раз копаюсь в таких задачах и увидел(а), что…»
  — и сразу крючок. Без вранья и без «мы потеряли ваш запрос».
- ДАВЛЕНИЕ через ценность и конкретику аудита, а не «давайте обсудим». Покажи, что понимаешь
  ИХ боль лучше конкурентов.
- 3–5 коротких шагов, живой разговорный тон. Ключевые фразы — в кавычках, готовые к произнесению.
  Дай 1–2 запасные реплики на возражение («если скажет, что уже не интересно — …»).
- Последний шаг — назначить КОНКРЕТНЫЙ следующий контакт (короткая встреча 15–20 мин, 2 слота).
- title — короткий цепляющий императив, без «Услуги по».
- Никакой воды и советов «будьте вежливы». Только то, что реально двигает ЭТУ сделку.
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
