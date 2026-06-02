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
- Верни JSON по схеме:
{
  "meeting_type": "defense|briefing|other",
  "checklist": [{"item": "...", "mark": "✅|⚠️|❌", "note": "..."}],
  "client_quote": "..." | null,
  "systemic_conclusion": "...",
  "status_discrepancy": true|false,
  "status_discrepancy_note": "..." | null,
  "verdict": "...",
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
  "tiger_caption": "..."
}
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
        completion = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=oai_messages,
            response_format={"type": "json_object"},
        )
        text = completion.choices[0].message.content or ""
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class _OpenAIAdapter:
    def __init__(self, client):
        self.messages = _OpenAIMessages(client)


def get_client():
    if LLM_PROVIDER == "openai":
        load_config(["OPENAI_API_KEY"])
        import openai

        return _OpenAIAdapter(openai.OpenAI())
    load_config(["ANTHROPIC_API_KEY"])
    import anthropic

    return anthropic.Anthropic()


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
    }


def _parse_fallback(status: str = "ok") -> dict[str, Any]:
    return {
        "transcript_status": status,
        "analysis_available": False,
        "reason": "LLM вернул невалидный JSON",
        "control_flag": True,
    }


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
    return {
        "meeting_type": parsed.get("meeting_type") or "other",
        "checklist": checklist,
        "client_quote": parsed.get("client_quote"),
        "systemic_conclusion": parsed.get("systemic_conclusion") or "",
        "status_discrepancy": bool(parsed.get("status_discrepancy")),
        "status_discrepancy_note": parsed.get("status_discrepancy_note"),
        "verdict": parsed.get("verdict") or "",
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
