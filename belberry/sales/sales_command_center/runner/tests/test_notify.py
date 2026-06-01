import logging

from src import notify


def set_telegram_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100main")
    monkeypatch.setenv("TELEGRAM_ALERT_CHAT_ID", "-100alert")
    monkeypatch.setenv("SCC_BASE_URL", "https://x.example")


def test_send_report_link_posts_day_url(monkeypatch):
    set_telegram_env(monkeypatch)
    calls = []

    def fake_post(url, payload):
        calls.append((url, payload))
        return True

    assert notify.send_report_link("2026-05-29", http_post=fake_post) is True

    url, payload = calls[0]
    assert "api.telegram.org" in url
    assert "123456:secret-token" in url
    assert payload["chat_id"] == "-100main"
    assert payload["parse_mode"] == "HTML"
    assert "https://x.example/day/2026-05-29" in payload["text"]


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


def test_send_report_link_is_fire_and_forget_on_http_error(monkeypatch):
    set_telegram_env(monkeypatch)

    def fake_post(url, payload):
        raise RuntimeError("HTTP 500")

    assert notify.send_report_link("2026-05-29", http_post=fake_post) is False


def test_send_report_link_returns_false_without_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100main")
    monkeypatch.setenv("SCC_BASE_URL", "https://x.example")

    assert notify.send_report_link("2026-05-29", http_post=lambda *_: True) is False


def test_token_is_masked_in_logs(monkeypatch, caplog):
    set_telegram_env(monkeypatch)

    def fake_post(url, payload):
        raise RuntimeError(f"failed with {url}")

    with caplog.at_level(logging.WARNING):
        assert notify.send_report_link("2026-05-29", http_post=fake_post) is False

    assert "123456:secret-token" not in caplog.text
    assert "bot***" in caplog.text or "***" in caplog.text
