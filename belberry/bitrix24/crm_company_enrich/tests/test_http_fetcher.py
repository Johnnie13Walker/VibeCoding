"""Unit-тесты для HttpFetcher: SSL fallback, DNS retry, condensed logging.

Не делает реальных HTTP-вызовов — monkeypatch'им session.get и time.sleep.
Реальная проблема Phase D (99 ENRICH_FAILED): SSL expired у клиник
(aurumpluc.ru, bodyproject.ru) и intermittent DNS (vitbiomed.ru, nazaraliev.com).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import pytest
import requests

from crm_company_enrich.stages import enrich_web
from crm_company_enrich.stages.enrich_web import FetchResult, HttpFetcher


# ----- helpers -----

@dataclass
class _FakeResp:
    url: str
    status_code: int = 200
    text: str = "<html>ok</html>"


class _FakeSession:
    """Session-stub, отдающий из очереди результаты/исключения."""

    def __init__(self, plan: list):
        self._plan: Iterator = iter(plan)
        self.calls: list[dict] = []

    def get(self, url, *, timeout, allow_redirects, verify):
        self.calls.append({"url": url, "verify": verify, "timeout": timeout})
        item = next(self._plan)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Все тесты ускоряем — отключаем time.sleep в модуле."""
    monkeypatch.setattr(enrich_web.time, "sleep", lambda _s: None)


def _install_session(monkeypatch, fetcher: HttpFetcher, plan: list) -> _FakeSession:
    """Подменить fetcher._ensure_session чтобы вернуть наш _FakeSession."""
    fake = _FakeSession(plan)
    monkeypatch.setattr(fetcher, "_ensure_session", lambda: fake)
    return fake


# ----- 1. SSL fallback -----

def test_ssl_fallback_retries_with_verify_false_and_sets_flag(monkeypatch):
    fetcher = HttpFetcher(timeout=1, retries=3)
    plan = [
        requests.exceptions.SSLError("certificate verify failed"),
        _FakeResp(url="https://aurumpluc.ru/", status_code=200, text="<html>ИНН: 7707083893</html>"),
    ]
    fake = _install_session(monkeypatch, fetcher, plan)

    result = fetcher.fetch("https://aurumpluc.ru/")

    assert result is not None
    assert result.status == 200
    assert result.ssl_unsafe is True
    assert result.text == "<html>ИНН: 7707083893</html>"
    # Первая попытка verify=True, вторая verify=False — fallback на ТОМ ЖЕ URL.
    assert [c["verify"] for c in fake.calls] == [True, False]


def test_ssl_fallback_both_fail_returns_none(monkeypatch):
    fetcher = HttpFetcher(timeout=1, retries=3)
    plan = [
        requests.exceptions.SSLError("ssl error #1"),
        requests.exceptions.SSLError("ssl error #2 even without verify"),
        # Дальше — стандартный retry-loop попробует ещё раз verify=True
        requests.exceptions.SSLError("ssl error #3"),
        requests.exceptions.SSLError("ssl error #4 verify=False fail"),
        requests.exceptions.SSLError("ssl error #5"),
        requests.exceptions.SSLError("ssl error #6"),
    ]
    _install_session(monkeypatch, fetcher, plan)
    assert fetcher.fetch("https://bad.example/") is None


def test_ssl_does_not_taint_global_verify(monkeypatch):
    """Каждый новый fetch начинается с verify=True — SSL flag локален к запросу."""
    fetcher = HttpFetcher(timeout=1, retries=3)
    plan = [
        requests.exceptions.SSLError("first url ssl"),
        _FakeResp(url="https://ssl-broken.ru/", status_code=200),
        # Второй вызов fetch() — снова verify=True
        _FakeResp(url="https://normal.ru/", status_code=200),
    ]
    fake = _install_session(monkeypatch, fetcher, plan)

    r1 = fetcher.fetch("https://ssl-broken.ru/")
    r2 = fetcher.fetch("https://normal.ru/")

    assert r1 is not None and r1.ssl_unsafe is True
    assert r2 is not None and r2.ssl_unsafe is False
    # 3 запроса всего; verify sequence: True, False (fallback), True (clean fetch).
    assert [c["verify"] for c in fake.calls] == [True, False, True]


# ----- 2. DNS retry -----

def _dns_error() -> requests.exceptions.ConnectionError:
    """Имитация urllib3.exceptions.NameResolutionError, обёрнутая requests'ом."""
    return requests.exceptions.ConnectionError(
        "HTTPSConnectionPool(host='vitbiomed.ru', port=443): "
        "Max retries exceeded with url: / "
        "(Caused by NameResolutionError(...))"
    )


def test_dns_retry_succeeds_after_two_failures(monkeypatch):
    fetcher = HttpFetcher(timeout=1, retries=3)
    plan = [
        _dns_error(),
        _dns_error(),
        _FakeResp(url="https://vitbiomed.ru/", status_code=200, text="ok"),
    ]
    _install_session(monkeypatch, fetcher, plan)

    result = fetcher.fetch("https://vitbiomed.ru/")
    assert result is not None
    assert result.status == 200
    assert result.ssl_unsafe is False


def test_dns_retry_extends_attempts(monkeypatch):
    """DNS-ошибки активируют до 2 дополнительных попыток сверх retries=3."""
    fetcher = HttpFetcher(timeout=1, retries=3)
    plan = [_dns_error() for _ in range(5)]  # 3 базовых + 2 extra
    fake = _install_session(monkeypatch, fetcher, plan)

    result = fetcher.fetch("https://nazaraliev.com/")
    assert result is None
    # Должно быть ровно 5 попыток (3 + 2 extra при детекте DNS).
    assert len(fake.calls) == 5


def test_dns_retry_eventually_succeeds_on_extra_attempt(monkeypatch):
    fetcher = HttpFetcher(timeout=1, retries=3)
    plan = [
        _dns_error(), _dns_error(), _dns_error(),  # 3 базовых fail'а
        _FakeResp(url="https://emsclinic.ru/", status_code=200),  # 4-я (extra) — success
    ]
    fake = _install_session(monkeypatch, fetcher, plan)

    result = fetcher.fetch("https://emsclinic.ru/")
    assert result is not None
    assert len(fake.calls) == 4


def test_dns_uses_extended_backoff(monkeypatch):
    """При DNS-ошибке sleep вызывается с увеличенными значениями (2, 5, 10)."""
    fetcher = HttpFetcher(timeout=1, retries=3)
    plan = [_dns_error(), _dns_error(), _FakeResp(url="https://x.ru/")]

    sleeps: list[float] = []
    monkeypatch.setattr(enrich_web.time, "sleep", lambda s: sleeps.append(s))
    _install_session(monkeypatch, fetcher, plan)

    fetcher.fetch("https://x.ru/")
    # Первые две паузы — DNS backoff (2, 5).
    assert sleeps[:2] == [2.0, 5.0]


# ----- 3. Happy path -----

def test_no_ssl_no_dns_single_attempt(monkeypatch):
    fetcher = HttpFetcher(timeout=1, retries=3)
    plan = [_FakeResp(url="https://ok.ru/", status_code=200, text="hello")]
    fake = _install_session(monkeypatch, fetcher, plan)

    result = fetcher.fetch("https://ok.ru/")
    assert result is not None
    assert result.status == 200
    assert result.text == "hello"
    assert result.ssl_unsafe is False
    assert len(fake.calls) == 1
    # Ни одного sleep на happy-path.


# ----- 4. Logging — финальный verdict, не на каждый attempt -----

def test_log_emits_single_verdict_line(monkeypatch, capsys):
    fetcher = HttpFetcher(timeout=1, retries=3)
    plan = [
        requests.exceptions.ConnectionError("Connection refused"),
        requests.exceptions.ConnectionError("Connection refused"),
        requests.exceptions.ConnectionError("Connection refused"),
    ]
    _install_session(monkeypatch, fetcher, plan)

    result = fetcher.fetch("https://askonamed.ru/")
    captured = capsys.readouterr()

    assert result is None
    log_lines = [ln for ln in captured.out.splitlines() if "[fetch]" in ln or "[enrich-web]" in ln]
    # Ровно один verdict-лог на URL — не три по числу attempts.
    assert len(log_lines) == 1
    assert "askonamed.ru" in log_lines[0]
    assert "3 attempts" in log_lines[0]
    assert "conn" in log_lines[0]


def test_log_classifies_ssl_after_total_failure(monkeypatch, capsys):
    fetcher = HttpFetcher(timeout=1, retries=2)
    plan = [requests.exceptions.SSLError("x") for _ in range(4)]
    _install_session(monkeypatch, fetcher, plan)

    fetcher.fetch("https://aurumpluc.ru/")
    out = capsys.readouterr().out
    assert "ssl" in out
