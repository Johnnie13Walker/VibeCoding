import logging

from src import notify


def set_telegram_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100main")
    monkeypatch.setenv("TELEGRAM_ALERT_CHAT_ID", "-100alert")


def test_send_alert_uses_alert_chat(monkeypatch):
    set_telegram_env(monkeypatch)
    calls = []

    def fake_post(url, payload):
        calls.append((url, payload))
        return True

    assert notify.send_alert("boom", report_date="2026-05-29", http_post=fake_post) is True

    payload = calls[0][1]
    assert payload["chat_id"] == "-100alert"
    assert "Сбой" in payload["text"]
    assert "2026-05-29" in payload["text"]
    assert "boom" in payload["text"]


def test_send_alert_escapes_html(monkeypatch):
    set_telegram_env(monkeypatch)
    calls = []

    def fake_post(url, payload):
        calls.append((url, payload))
        return True

    assert notify.send_alert("err <script>&", http_post=fake_post) is True

    text = calls[0][1]["text"]
    assert "<script>" not in text
    assert "&lt;script&gt;&amp;" in text


def test_send_alert_returns_false_without_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SCC_TELEGRAM_BOT_TOKEN", raising=False)

    assert notify.send_alert("boom", http_post=lambda *_: True) is False


def test_token_is_masked_in_logs(monkeypatch, caplog):
    set_telegram_env(monkeypatch)

    def fake_post(url, payload):
        raise RuntimeError(f"failed with {url}")

    with caplog.at_level(logging.WARNING):
        assert notify.send_alert("boom", http_post=fake_post) is False

    assert "123456:secret-token" not in caplog.text
    assert "bot***" in caplog.text or "***" in caplog.text
