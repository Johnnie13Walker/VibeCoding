import json
import os
import re
import time
from types import SimpleNamespace
from typing import Any

from .config import load_config

# Провайдер LLM переключается одной переменной окружения (по умолчанию —
# Anthropic, как спроектировано и отревьюено). OpenAI поддержан через адаптер
# с тем же интерфейсом client.messages.create(...) → response.content[0].text,
# поэтому остальной код и тесты не меняются.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower()

if os.environ.get("LLM_MODEL"):
    MODEL = os.environ["LLM_MODEL"]
elif LLM_PROVIDER == "openai":
    MODEL = "gpt-4o"
else:
    MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Жёсткий таймаут на один LLM-вызов: без него клиенты SDK висят на дефолте
# (~600с) и со встроенными ретраями копят зависший сокет до десятков минут.
# Это критично для unattended-cron 09:00: зависший author держал бы flock и не
# доставил отчёт. _call_with_retry даёт свою повторную попытку — ретраи самого
# SDK отключаем (max_retries=0), чтобы ожидание не множилось. Дефолт 600с = как
# было у SDK на один запрос, поэтому легитимно-медленный author не словит ложный
# таймаут; убран именно неограниченный хвост от перемножения ретраев.
LLM_TIMEOUT = float(os.environ.get("SCC_LLM_TIMEOUT", "600"))
LLM_SDK_RETRIES = int(os.environ.get("SCC_LLM_SDK_RETRIES", "0"))

# reasoning_effort для reasoning-моделей (o-серия, gpt-5.x). low — потому что
# авторство HTML/JSON не требует глубокого рассуждения, а высокий effort съедает
# бюджет max_completion_tokens reasoning-токенами → пустой вывод. minimal у gpt-5.5
# не поддерживается, поэтому дефолт low. Пусто → reasoning_effort не передаём.
REASONING_EFFORT = os.environ.get("SCC_LLM_REASONING_EFFORT", "low")
VALID_MARKS = {"✅", "⚠️", "❌"}

SYSTEM_PROMPT = """
Ты разбираешь встречи отдела продаж Belberry по транскрипту.
Верни строго JSON без markdown.

Типы встреч:
- briefing: брифинг.
- defense: защита КП.
- other: другое.

Чек-лист брифинга: диалог-не-анкета, потребность, кейсы, БЮДЖЕТ, следующий шаг.
Чек-лист защиты КП: кейсы (обязательно), аргументация цифр, запрос следующих шагов
от клиента, итоги клиенту.

Правила:
- Оцени каждый применимый пункт mark: ✅, ⚠️ или ❌.
- Цитату клиента бери только дословно из транскрипта. Если показательной цитаты нет,
  client_quote = null.
- Не верь статусу Bitrix слепо. Лови расхождение между статусом сделки/встречи и сутью
  разговора. Если статус "успех", но клиент не согласовал следующий шаг, ставь
  status_discrepancy=true.
- Поставь встрече итоговый балл score — целое 1..10 по качеству проработки
  (чек-лист + следующий шаг + аргументация). Эталон: сильная защита ≈8, тяжёлый
  брифинг без бюджета ≈5-6.
- observations — 3–6 конкретных наблюдений из разговора: good/risk, что именно
  произошло, и metric = цифра/факт из встречи. Не придумывай цифры.
- next_step — только структурно: что сделать, кто владелец, дедлайн. Если клиент
  не дал явного шага, верни null.
- next_steps — СПИСОК ключевых открытых действий после встречи для постановки задач
  менеджеру. Обычно 1–3 пункта на встречу (НЕ дроби в труху). Правила:
  * Включай ТОЛЬКО то, что ещё НЕ сделано. Если действие уже выполнено на встрече или
    до неё (доступ к Метрике уже получен, материалы уже отправлены) — НЕ включай.
  * НЕ включай «подготовить/сформировать/составить КП (коммерческое предложение)» —
    это ставится автоматически при переходе сделки на стадию КП. (Но «отправить КП»,
    «защитить КП» — это нормальные действия, их включай.)
  * ГРУППИРУЙ однотипное в ОДИН пункт. Все «отправить клиенту …» (запись встречи,
    кейсы, отчёт, материалы, сметы, ссылки, доступы) = ОДНА задача
    «Отправить клиенту материалы» — что именно отправить перечисли внутри what через
    запятую. НЕ делай отдельную задачу на каждое вложение.
  * Отдельными пунктами оставляй только РАЗНЫЕ по сути действия:
    (1) отправить клиенту материалы; (2) получить ответ/обратную связь клиента;
    (3) внутреннее действие (уточнить у департамента/коллег, проверить вручную);
    (4) запланированный созвон/встреча на конкретную дату.
  * kind: "operational" — быстрая отправка/подготовка-и-отправка материалов.
    "scheduled" — привязано к конкретной дате/встрече, о которой договорились.
  * deadline — дословная формулировка срока из разговора, если есть, иначе null.
  Если открытых действий нет — пустой список [].
- objections — реальные возражения клиента и отработаны ли они.
- commitment — сила обязательства клиента: взял_обязательство / подумает / нет.
- duration_min — длительность встречи в минутах, если выводима из метаданных или
  транскрипта; иначе null.
- meeting_segment — primary для первичного брифинга/защиты, repeat для повторной
  встречи с движением от прошлого контакта.
- transcript_based — true только если разбор построен по реальному транскрипту.
- summary_sent — true, если по транскрипту/переписке менеджер ОТПРАВИЛ клиенту итоги
  встречи (резюме договорённостей, следующие шаги). Если этого не видно — false.
- budget_named — true, если на встрече НАЗВАН бюджет клиента (хотя бы ориентир суммы).
  Если бюджет не вскрыт/не обсуждался — false.
- Верни JSON по схеме:
{
  "meeting_type": "defense|briefing|other",
  "score": 1,
  "checklist": [{"item": "...", "mark": "✅|⚠️|❌", "note": "..."}],
  "observations": [{"kind": "good|risk", "text": "...", "metric": "..." | null}],
  "next_step": {"what": "...", "who": "...", "deadline": "..." | null} | null,
  "next_steps": [{"what": "...", "owner": "...", "kind": "operational|scheduled", "deadline": "..." | null}],
  "objections": [{"objection": "...", "handled": true|false, "note": "..."}],
  "commitment": "взял_обязательство|подумает|нет",
  "duration_min": 28 | null,
  "meeting_segment": "primary|repeat",
  "transcript_based": true,
  "client_quote": "..." | null,
  "systemic_conclusion": "...",
  "status_discrepancy": true|false,
  "status_discrepancy_note": "..." | null,
  "verdict": "...",
  "summary_sent": true,
  "budget_named": true,
  "transcript_status": "ok"
}
"""

NARRATIVE_SYSTEM_PROMPT = """
Ты пишешь управленческие нарративные блоки ежедневного отчёта продаж Belberry.
Верни строго JSON без markdown.
Используй имена сотрудников в формате "Фамилия Имя", не ID.

Схема:
{
  "thirty_seconds": {"горит": "...", "деньги": "...", "системно": "..."},
  "pinch_list": [{"name": "Фамилия Имя", "action": "...", "why": "..."}],
  "systemic_patterns": {"works": ["..."], "repeats": ["..."]},
  "day_summary": "...",
  "quote_of_day": {"text": "...", "meta": "..."},
  "manager_coaching": [{"manager": "Фамилия Имя", "manager_id": 123, "advice": "...", "basis": "..."}],
  "tiger_caption": "..."
}

manager_coaching — максимум 1 конкретный совет на менеджера, только по его встречам
или активности из агрегата. Не пиши общие банальности вроде «быть активнее»; если
данных по менеджеру мало, не включай его в manager_coaching.
quote_of_day — сильная дословная фраза менеджера или клиента из разборов встреч.
Не придумывай цитаты.
"""


class _OpenAIMessages:
    """Транслирует Anthropic-style вызов в OpenAI chat.completions."""

    def __init__(self, client):
        self._client = client

    def create(self, *, model, max_tokens=2000, temperature=0, system=None, messages=None):
        sys_text = ""
        if system:
            first = system[0]
            sys_text = first.get("text", "") if isinstance(first, dict) else str(first)
        oai_messages = []
        if sys_text:
            oai_messages.append({"role": "system", "content": sys_text})
        for item in messages or []:
            oai_messages.append({"role": item["role"], "content": item["content"]})
        def _params(reasoning: bool, with_effort: bool = True) -> dict[str, Any]:
            p: dict[str, Any] = {"model": model, "messages": oai_messages}
            if reasoning:
                # reasoning-модели (o-серия, gpt-5.x): max_completion_tokens,
                # температуру не передаём (поддерживается только дефолт).
                # reasoning_effort=low — для авторства HTML/JSON глубокое
                # рассуждение не нужно, иначе reasoning-токены съедают бюджет
                # и видимого вывода не остаётся (пустое тело отчёта).
                p["max_completion_tokens"] = max_tokens
                if with_effort and REASONING_EFFORT:
                    p["reasoning_effort"] = REASONING_EFFORT
            else:
                p["max_tokens"] = max_tokens
                p["temperature"] = temperature
            return p

        # Не форсим response_format=json_object: автор отчёта ждёт HTML, а
        # разбор встреч и так парсит JSON из текста (как на Anthropic).
        # gpt-5.x — reasoning-модель: распознаём заранее, чтобы сразу слать
        # max_completion_tokens (max_tokens она отвергает с 400).
        reasoning = bool(re.match(r"^(o\d|gpt-5)", model or ""))
        try:
            completion = self._client.chat.completions.create(**_params(reasoning))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "reasoning_effort" in msg:
                # модель не приняла reasoning_effort — повтор без него
                completion = self._client.chat.completions.create(**_params(reasoning, with_effort=False))
            elif not reasoning and any(
                k in msg for k in ("max_completion_tokens", "max_tokens", "temperature", "unsupported")
            ):
                # max_tokens/temperature отвергнуты — повтор в reasoning-стиле
                completion = self._client.chat.completions.create(**_params(True))
            else:
                raise
        text = completion.choices[0].message.content or ""
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class _OpenAIAdapter:
    def __init__(self, client):
        self.messages = _OpenAIMessages(client)


def get_client():
    if LLM_PROVIDER == "openai":
        load_config(["OPENAI_API_KEY"])
        import openai

        return _OpenAIAdapter(openai.OpenAI(timeout=LLM_TIMEOUT, max_retries=LLM_SDK_RETRIES))
    load_config(["ANTHROPIC_API_KEY"])
    import anthropic

    return anthropic.Anthropic(timeout=LLM_TIMEOUT, max_retries=LLM_SDK_RETRIES)


def build_user_message(
    meeting_meta: dict[str, Any],
    transcript_text: str,
    wazzup_summary: str | None = None,
) -> str:
    return "\n\n".join(
        [
            "Метаданные встречи:",
            json.dumps(meeting_meta, ensure_ascii=False, default=str),
            "Wazzup/итоги после встречи:",
            wazzup_summary or "нет данных",
            "Транскрипт:",
            transcript_text,
        ]
    )


def build_narrative_message(day_aggregate: dict[str, Any], meeting_analyses: dict[int, dict]) -> str:
    return "\n\n".join(
        [
            "Агрегат дня:",
            json.dumps(day_aggregate, ensure_ascii=False, default=str),
            "Разборы встреч:",
            json.dumps(meeting_analyses, ensure_ascii=False, default=str),
        ]
    )


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response.get("content") if isinstance(response, dict) else [])
    if not content:
        return ""
    first = content[0]
    return getattr(first, "text", first.get("text") if isinstance(first, dict) else str(first))


def _parse_llm_json(raw_text: str) -> dict | None:
    text = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _call_with_retry(client, **kwargs):
    last_exc = None
    for attempt in range(3):
        try:
            return client.messages.create(**kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt == 2:
                raise
            time.sleep(0.1 * (2**attempt))
    raise last_exc  # pragma: no cover


def _system(prompt: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]


def _unavailable(status: str, reason: str) -> dict[str, Any]:
    return {
        "transcript_status": status,
        "analysis_available": False,
        "reason": reason,
        "control_flag": True,
        "observations": [],
        "next_step": None,
        "next_steps": [],
        "objections": [],
        "commitment": "нет",
        "duration_min": None,
        "meeting_segment": "primary",
        "transcript_based": False,
    }


def _parse_fallback(status: str = "ok") -> dict[str, Any]:
    return {
        "transcript_status": status,
        "analysis_available": False,
        "reason": "LLM вернул невалидный JSON",
        "control_flag": True,
        "observations": [],
        "next_step": None,
        "next_steps": [],
        "objections": [],
        "commitment": "нет",
        "duration_min": None,
        "meeting_segment": "primary",
        "transcript_based": status == "ok",
    }


def _normalize_observations(value: Any) -> list[dict[str, Any]]:
    output = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").lower()
        output.append(
            {
                "kind": kind if kind in {"good", "risk"} else "risk",
                "text": str(item.get("text") or "").strip(),
                "metric": item.get("metric") if item.get("metric") not in ("", None) else None,
            }
        )
    return [item for item in output if item["text"]][:6]


def _normalize_next_step(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    what = str(value.get("what") or "").strip()
    who = str(value.get("who") or "").strip()
    if not what and not who:
        return None
    return {
        "what": what,
        "who": who,
        "deadline": value.get("deadline") if value.get("deadline") not in ("", None) else None,
    }


def _normalize_next_steps(value: Any) -> list[dict[str, Any]]:
    """Атомарные открытые действия для постановки задач. Фильтр формирования КП и
    уже сделанного — на стороне tasks.py (детерминированно), здесь только структура."""
    out: list[dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        what = str(item.get("what") or "").strip()
        if not what:
            continue
        kind = str(item.get("kind") or "").strip().lower()
        out.append(
            {
                "what": what,
                "owner": str(item.get("owner") or item.get("who") or "").strip(),
                "kind": kind if kind in {"operational", "scheduled"} else "operational",
                "deadline": item.get("deadline") if item.get("deadline") not in ("", None) else None,
            }
        )
    return out[:10]


def _normalize_objections(value: Any) -> list[dict[str, Any]]:
    output = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        objection = str(item.get("objection") or "").strip()
        if not objection:
            continue
        output.append(
            {
                "objection": objection,
                "handled": bool(item.get("handled")),
                "note": str(item.get("note") or "").strip(),
            }
        )
    return output


def _normalize_commitment(value: Any) -> str:
    value = str(value or "").strip().lower()
    return value if value in {"взял_обязательство", "подумает", "нет"} else "нет"


def _normalize_duration(value: Any) -> int | None:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def _normalize_segment(value: Any) -> str:
    value = str(value or "").strip().lower()
    return value if value in {"primary", "repeat"} else "primary"


def _opt_bool(value: Any) -> bool | None:
    """Дискретный флаг качества: True/False, либо None если LLM не вернул."""
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    return str(value).strip().lower() in {"true", "1", "да", "yes"}


def _normalize_analysis(parsed: dict[str, Any]) -> dict[str, Any]:
    checklist = []
    for item in parsed.get("checklist") or []:
        mark = item.get("mark")
        checklist.append(
            {
                "item": str(item.get("item") or ""),
                "mark": mark if mark in VALID_MARKS else "⚠️",
                "note": str(item.get("note") or ""),
            }
        )
    score = parsed.get("score")
    try:
        score = max(1, min(10, int(score))) if score is not None else None
    except (TypeError, ValueError):
        score = None
    return {
        "meeting_type": parsed.get("meeting_type") or "other",
        "score": score,
        "checklist": checklist,
        "observations": _normalize_observations(parsed.get("observations")),
        "next_step": _normalize_next_step(parsed.get("next_step")),
        "next_steps": _normalize_next_steps(parsed.get("next_steps")),
        "objections": _normalize_objections(parsed.get("objections")),
        "commitment": _normalize_commitment(parsed.get("commitment")),
        "duration_min": _normalize_duration(parsed.get("duration_min")),
        "meeting_segment": _normalize_segment(parsed.get("meeting_segment")),
        "transcript_based": bool(parsed.get("transcript_based", True)),
        "client_quote": parsed.get("client_quote"),
        "systemic_conclusion": parsed.get("systemic_conclusion") or "",
        "status_discrepancy": bool(parsed.get("status_discrepancy")),
        "status_discrepancy_note": parsed.get("status_discrepancy_note"),
        "verdict": parsed.get("verdict") or "",
        "summary_sent": _opt_bool(parsed.get("summary_sent")),
        "budget_named": _opt_bool(parsed.get("budget_named")),
        "transcript_status": "ok",
    }


def analyze_meeting(
    meeting_meta: dict[str, Any],
    enriched: dict[str, Any],
    *,
    client,
    wazzup_summary: str | None = None,
) -> dict[str, Any]:
    status = enriched.get("transcript_status")
    if status == "missing":
        return _unavailable("missing", "Записи/транскрипта нет — разбор невозможен")
    if status == "mismatch":
        return _unavailable("mismatch", "Транскрипт не соответствует встрече")
    if status != "ok":
        return _unavailable(status or "missing", "Разбор невозможен")

    response = _call_with_retry(
        client,
        model=MODEL,
        max_tokens=2000,
        temperature=0,
        system=_system(SYSTEM_PROMPT),
        messages=[
            {
                "role": "user",
                "content": build_user_message(meeting_meta, enriched.get("text", ""), wazzup_summary),
            }
        ],
    )
    parsed = _parse_llm_json(_response_text(response))
    if parsed is None:
        return _parse_fallback("ok")
    return _normalize_analysis(parsed)


def analyze_day(
    transcripts: dict[int, dict[str, Any]],
    meetings_meta: dict[int, dict[str, Any]],
    *,
    client,
    wazzup: dict | None = None,
) -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {}
    for meeting_id, enriched in transcripts.items():
        output[int(meeting_id)] = analyze_meeting(
            meetings_meta.get(int(meeting_id), {"meeting_id": int(meeting_id)}),
            enriched,
            client=client,
            wazzup_summary=json.dumps((wazzup or {}).get(str(meeting_id), ""), ensure_ascii=False),
        )
    return output


def analyze_day_narrative(rows, extras, meeting_analyses, *, client) -> dict[str, Any]:
    day_aggregate = {
        "counts": {key: len(value) for key, value in rows.items() if isinstance(value, list)},
        "stale": extras.get("stale", {}),
        "rejections": extras.get("rejections", []),
        "manager_activity": rows.get("manager_activity", []),
    }
    response = _call_with_retry(
        client,
        model=MODEL,
        max_tokens=2000,
        temperature=0,
        system=_system(NARRATIVE_SYSTEM_PROMPT),
        messages=[
            {
                "role": "user",
                "content": build_narrative_message(day_aggregate, meeting_analyses),
            }
        ],
    )
    parsed = _parse_llm_json(_response_text(response))
    return parsed or {}
