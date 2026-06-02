import json

import pytest

from src import analyze_llm

FIXED_ANALYSIS = {
    "meeting_type": "defense",
    "checklist": [{"item": "кейсы", "mark": "❌", "note": "кейсы не показаны"}],
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
    assert result["tiger_caption"]
    assert client.messages.kwargs[0]["system"][0]["cache_control"] == {"type": "ephemeral"}


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

    adapter = analyze_llm._OpenAIAdapter(FakeOpenAI())
    out = adapter.messages.create(model="gpt-5.5", max_tokens=500, temperature=0,
                                  system=None, messages=[{"role": "user", "content": "x"}])
    assert out.content[0].text == "ok"
    assert len(calls) == 2  # первый с max_tokens упал → retry в reasoning-стиле
    assert "max_completion_tokens" in calls[1] and "temperature" not in calls[1]
