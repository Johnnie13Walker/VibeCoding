import json

import pytest

from src import analyze_llm

FIXED_ANALYSIS = {
    "meeting_type": "defense",
    "checklist": [{"item": "кейсы", "mark": "❌", "note": "кейсы не показаны"}],
    "observations": [
        {"kind": "good", "text": "Менеджер показал расчёт окупаемости.", "metric": "ROI 177%"},
        {"kind": "risk", "text": "Клиент не подтвердил бюджет.", "metric": "бюджет не назван"},
    ],
    "next_step": {"what": "Отправить прогноз и кейс", "who": "Иванов Иван", "deadline": "понедельник"},
    "objections": [{"objection": "Нет понятного кейса", "handled": False, "note": "Кейс не показали"}],
    "commitment": "подумает",
    "duration_min": 28,
    "meeting_segment": "repeat",
    "transcript_based": True,
    "client_quote": "Без кейса я не понимаю, какой результат можно ожидать.",
    "systemic_conclusion": "Нужна памятка по модели оплаты и кейсам.",
    "status_discrepancy": True,
    "status_discrepancy_note": "В Bitrix успех, но клиент попросил материалы и не согласовал следующий шаг.",
    "verdict": "Защита не закрыта.",
    "transcript_status": "ok",
}
FIXED_NARRATIVE = {
    "thirty_seconds": {"горит": "перевесить базу", "деньги": "риски КП", "системно": "кейсы"},
    "pinch_list": [{"name": "Иванов Иван", "action": "дожать", "why": "зависло"}],
    "systemic_patterns": {"works": ["брифы"], "repeats": ["нет кейсов"]},
    "day_summary": "Итог дня.",
    "quote_of_day": {"text": "Жду прогноз.", "meta": "защита"},
    "manager_coaching": [{"manager": "Иванов Иван", "manager_id": 10, "advice": "Показывать кейс до цены.", "basis": "нет кейса"}],
    "tiger_caption": "Сильный обзвон.",
}


class Content:
    def __init__(self, text):
        self.text = text


class Response:
    def __init__(self, text):
        self.content = [Content(text)]


class Messages:
    def __init__(self, texts=None, errors_before=0, always_error=False):
        self.texts = list(texts or [json.dumps(FIXED_ANALYSIS, ensure_ascii=False)])
        self.errors_before = errors_before
        self.always_error = always_error
        self.calls = 0
        self.kwargs = []

    def create(self, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        if self.always_error or self.calls <= self.errors_before:
            raise RuntimeError("transient")
        text = self.texts[min(self.calls - self.errors_before - 1, len(self.texts) - 1)]
        return Response(text)


class FakeAnthropic:
    def __init__(self, **kwargs):
        self.messages = Messages(**kwargs)


def test_analyze_meeting_returns_structured_json():
    client = FakeAnthropic()

    result = analyze_llm.analyze_meeting(
        {"meeting_id": 2180, "status": "success"},
        {"transcript_status": "ok", "text": "транскрипт"},
        client=client,
    )

    assert result["meeting_type"] == "defense"
    assert result["checklist"][0]["mark"] == "❌"
    assert result["client_quote"]
    assert result["status_discrepancy"] is True
    assert result["transcript_status"] == "ok"
    assert result["observations"][0]["metric"] == "ROI 177%"
    assert result["next_step"] == {"what": "Отправить прогноз и кейс", "who": "Иванов Иван", "deadline": "понедельник"}
    assert result["objections"][0]["handled"] is False
    assert result["commitment"] == "подумает"
    assert result["duration_min"] == 28
    assert result["meeting_segment"] == "repeat"
    assert result["transcript_based"] is True


def test_system_prompt_uses_cache_control():
    client = FakeAnthropic()

    analyze_llm.analyze_meeting({}, {"transcript_status": "ok", "text": "x"}, client=client)

    kwargs = client.messages.kwargs[0]
    assert kwargs["temperature"] == 0
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_missing_transcript_skips_llm():
    client = FakeAnthropic()

    result = analyze_llm.analyze_meeting({}, {"transcript_status": "missing"}, client=client)

    assert client.messages.calls == 0
    assert result["analysis_available"] is False
    assert result["control_flag"] is True
    assert result["transcript_based"] is False
    assert result["next_step"] is None
    assert result["observations"] == []


def test_mismatch_transcript_skips_llm():
    client = FakeAnthropic()

    result = analyze_llm.analyze_meeting({}, {"transcript_status": "mismatch"}, client=client)

    assert client.messages.calls == 0
    assert "не соответствует" in result["reason"]


def test_client_quote_from_transcript_only_can_be_null():
    payload = dict(FIXED_ANALYSIS)
    payload["client_quote"] = None
    client = FakeAnthropic(texts=[json.dumps(payload, ensure_ascii=False)])

    result = analyze_llm.analyze_meeting({}, {"transcript_status": "ok", "text": "x"}, client=client)

    assert result["client_quote"] is None


def test_analyze_day_maps_by_meeting_id():
    client = FakeAnthropic()

    result = analyze_llm.analyze_day(
        {
            2180: {"transcript_status": "ok", "text": "x"},
            7: {"transcript_status": "missing", "text": ""},
        },
        {2180: {"meeting_id": 2180}, 7: {"meeting_id": 7}},
        client=client,
    )

    assert set(result) == {2180, 7}
    assert client.messages.calls == 1
    assert result[7]["analysis_available"] is False


def test_malformed_llm_json_is_handled_and_markdown_json_parsed():
    markdown = "```json\n" + json.dumps(FIXED_ANALYSIS, ensure_ascii=False) + "\n```"
    client = FakeAnthropic(texts=[markdown, "not json"])

    good = analyze_llm.analyze_meeting({}, {"transcript_status": "ok", "text": "x"}, client=client)
    bad = analyze_llm.analyze_meeting({}, {"transcript_status": "ok", "text": "x"}, client=client)

    assert good["verdict"]
    assert bad["analysis_available"] is False


def test_retry_on_transient_then_success():
    client = FakeAnthropic(errors_before=2)

    result = analyze_llm.analyze_meeting({}, {"transcript_status": "ok", "text": "x"}, client=client)

    assert client.messages.calls == 3
    assert result["verdict"]


def test_retry_exhausted_raises():
    client = FakeAnthropic(always_error=True)

    with pytest.raises(RuntimeError):
        analyze_llm.analyze_meeting({}, {"transcript_status": "ok", "text": "x"}, client=client)

    assert client.messages.calls == 3


def test_analyze_day_narrative_returns_keys():
    client = FakeAnthropic(texts=[json.dumps(FIXED_NARRATIVE, ensure_ascii=False)])

    result = analyze_llm.analyze_day_narrative(
        {"manager_activity": []},
        {"stale": {}, "rejections": []},
        {2180: FIXED_ANALYSIS},
        client=client,
    )

    assert result["thirty_seconds"]["горит"]
    assert result["pinch_list"]
    assert result["systemic_patterns"]["works"]
    assert result["day_summary"]
    assert result["quote_of_day"]["text"]
    assert result["manager_coaching"][0]["advice"]
    assert result["tiger_caption"]
    assert client.messages.kwargs[0]["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_narrative_prompt_requests_coaching_without_achievements():
    assert "manager_coaching" in analyze_llm.NARRATIVE_SYSTEM_PROMPT
    assert "Не пиши общие банальности" in analyze_llm.NARRATIVE_SYSTEM_PROMPT
    assert "ачив" not in analyze_llm.NARRATIVE_SYSTEM_PROMPT.lower()


def test_openai_adapter_params_and_no_json_force():
    from types import SimpleNamespace
    captured = {}

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured.clear()
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        chat = FakeChat()

    adapter = analyze_llm._OpenAIAdapter(FakeOpenAI())

    # chat-модель: max_tokens + temperature, без response_format=json_object
    adapter.messages.create(model="gpt-4.1", max_tokens=1234, temperature=0,
                            system=[{"text": "sys"}], messages=[{"role": "user", "content": "x"}])
    assert captured["max_tokens"] == 1234 and "temperature" in captured
    assert "response_format" not in captured

    # reasoning-модель: max_completion_tokens, без max_tokens/temperature
    adapter.messages.create(model="o3", max_tokens=999, temperature=0,
                            system=None, messages=[{"role": "user", "content": "x"}])
    assert captured["max_completion_tokens"] == 999
    assert "max_tokens" not in captured and "temperature" not in captured


def test_openai_adapter_retries_reasoning_style_on_param_error():
    from types import SimpleNamespace
    calls = []

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            calls.append(kwargs)
            if "max_tokens" in kwargs:
                raise RuntimeError("Unsupported parameter: 'max_tokens'; use 'max_completion_tokens'")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        chat = FakeChat()

    # Модель НЕ из известных reasoning-семейств (gpt-5.x/o-серия уже ловятся
    # заранее) — проверяем общий фолбэк: max_tokens отвергнут → retry reasoning.
    adapter = analyze_llm._OpenAIAdapter(FakeOpenAI())
    out = adapter.messages.create(model="some-new-reasoner", max_tokens=500, temperature=0,
                                  system=None, messages=[{"role": "user", "content": "x"}])
    assert out.content[0].text == "ok"
    assert len(calls) == 2  # первый с max_tokens упал → retry в reasoning-стиле
    assert "max_completion_tokens" in calls[1] and "temperature" not in calls[1]


def test_get_client_bounds_timeout_and_disables_sdk_retries(monkeypatch):
    """Клиент LLM создаётся с жёстким таймаутом и без собственных ретраев SDK —
    иначе зависший сокет копится десятками минут и ломает cron-доставку."""
    import sys
    import types

    captured = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeOpenAI))
    monkeypatch.setattr(analyze_llm, "LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    analyze_llm.get_client()

    assert captured["timeout"] == analyze_llm.LLM_TIMEOUT
    assert captured["max_retries"] == analyze_llm.LLM_SDK_RETRIES
    assert analyze_llm.LLM_SDK_RETRIES == 0
    assert analyze_llm.LLM_TIMEOUT <= 600


class _FakeCompletions:
    def __init__(self):
        self.captured = []

    def create(self, **kwargs):
        import types
        self.captured.append(kwargs)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="<section>ok</section>"))]
        )


class _FakeOpenAIClient:
    def __init__(self):
        import types
        self.completions = _FakeCompletions()
        self.chat = types.SimpleNamespace(completions=self.completions)


def test_openai_adapter_gpt5_uses_completion_tokens_and_effort():
    """gpt-5.x распознаётся как reasoning: max_completion_tokens + reasoning_effort,
    без max_tokens/temperature (их модель отвергает 400)."""
    client = _FakeOpenAIClient()
    adapter = analyze_llm._OpenAIMessages(client)
    resp = adapter.create(
        model="gpt-5.5", max_tokens=40000, temperature=0.3,
        system=[{"text": "sys"}], messages=[{"role": "user", "content": "hi"}],
    )
    sent = client.completions.captured[0]
    assert sent["max_completion_tokens"] == 40000
    assert "max_tokens" not in sent
    assert "temperature" not in sent
    assert sent["reasoning_effort"] == analyze_llm.REASONING_EFFORT
    assert resp.content[0].text == "<section>ok</section>"


def test_openai_adapter_gpt4o_keeps_max_tokens_and_temperature():
    """Не-reasoning модель (gpt-4o) — прежний путь: max_tokens + temperature."""
    client = _FakeOpenAIClient()
    adapter = analyze_llm._OpenAIMessages(client)
    adapter.create(
        model="gpt-4o", max_tokens=2000, temperature=0.3,
        system=[{"text": "sys"}], messages=[{"role": "user", "content": "hi"}],
    )
    sent = client.completions.captured[0]
    assert sent["max_tokens"] == 2000
    assert sent["temperature"] == 0.3
    assert "max_completion_tokens" not in sent
    assert "reasoning_effort" not in sent
