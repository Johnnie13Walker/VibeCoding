from __future__ import annotations

import requests

from crm_company_enrich.stages import enrich_web


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class FakeSession:
    calls: list[tuple[str, str]] = []
    head_status = 200
    get_status = 200
    raise_exc: Exception | None = None

    def __init__(self):
        self.headers = {}

    def head(self, url, **kwargs):
        self.calls.append(("HEAD", url))
        if self.raise_exc:
            raise self.raise_exc
        return FakeResponse(self.head_status)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        if self.raise_exc:
            raise self.raise_exc
        return FakeResponse(self.get_status)


def setup_function():
    enrich_web._SITE_ALIVE_CACHE.clear()
    FakeSession.calls = []
    FakeSession.head_status = 200
    FakeSession.get_status = 200
    FakeSession.raise_exc = None


def test_alive_check_ok_2xx(monkeypatch):
    monkeypatch.setattr(requests, "Session", FakeSession)

    result = enrich_web.is_site_alive("example.ru")

    assert result.is_alive is True
    assert result.status_code == 200
    assert result.reason == "ok"
    assert FakeSession.calls == [("HEAD", "https://example.ru/")]


def test_alive_check_dns_error(monkeypatch):
    monkeypatch.setattr(requests, "Session", FakeSession)
    FakeSession.raise_exc = requests.exceptions.ConnectionError("NameResolutionError: failed to resolve")

    result = enrich_web.is_site_alive("missing.example")

    assert result.is_alive is False
    assert result.reason == "dns"


def test_alive_check_timeout(monkeypatch):
    monkeypatch.setattr(requests, "Session", FakeSession)
    FakeSession.raise_exc = requests.exceptions.Timeout("timeout")

    result = enrich_web.is_site_alive("slow.example")

    assert result.is_alive is False
    assert result.reason == "timeout"


def test_alive_check_4xx_blocked(monkeypatch):
    monkeypatch.setattr(requests, "Session", FakeSession)
    FakeSession.head_status = 404

    result = enrich_web.is_site_alive("gone.example")

    assert result.is_alive is False
    assert result.status_code == 404
    assert result.reason == "4xx_blocked"


def test_alive_check_cyrillic_domain(monkeypatch):
    monkeypatch.setattr(requests, "Session", FakeSession)

    result = enrich_web.is_site_alive("https://сп3.рф/контакты/")

    assert result.is_alive is True
    assert result.url == "https://xn--3-2tbf.xn--p1ai/%D0%BA%D0%BE%D0%BD%D1%82%D0%B0%D0%BA%D1%82%D1%8B/"


def test_alive_check_caches_result(monkeypatch):
    monkeypatch.setattr(requests, "Session", FakeSession)

    first = enrich_web.is_site_alive("https://example.ru")
    second = enrich_web.is_site_alive("https://example.ru/")

    assert first is second
    assert FakeSession.calls == [("HEAD", "https://example.ru/")]


def test_alive_check_percent_encoded_cyrillic_host(monkeypatch):
    """REGRESSION: url с percent-encoded кириллицей в host (`%d0%bf...рф`) не должен
    валить is_site_alive с LocationParseError — должен корректно нормализоваться."""
    monkeypatch.setattr(requests, "Session", FakeSession)
    pct = "https://%d0%bf%d0%b5%d1%80%d0%b2%d1%8b%d0%b9%d1%8d%d0%bb%d0%b5%d0%bc%d0%b5%d0%bd%d1%82.%d1%80%d1%84"
    result = enrich_web.is_site_alive(pct)
    # IDNA host первыйэлемент.рф = xn--... .xn--p1ai
    assert result.url.startswith("https://xn--")
    assert result.reason == "ok"


def test_alive_check_invalid_url_returns_bad_url(monkeypatch):
    """Битые URL не валят is_site_alive — bad_url reason."""
    monkeypatch.setattr(requests, "Session", FakeSession)
    for bad in ("://broken", "//", "http://", "   ", ""):
        result = enrich_web.is_site_alive(bad)
        assert result.is_alive is False
        assert result.reason == "bad_url"


def test_alive_check_low_level_exception_does_not_propagate(monkeypatch):
    """Низкоуровневые exception (urllib3 LocationParseError, UnicodeError, ValueError)
    не должны propagate — заворачиваем в bad_url."""
    monkeypatch.setattr(requests, "Session", FakeSession)
    FakeSession.raise_exc = ValueError("malformed URL")
    result = enrich_web.is_site_alive("https://broken.example")
    assert result.is_alive is False
    assert result.reason == "bad_url"


def test_alive_check_3xx_treated_as_alive(monkeypatch):
    """REGRESSION: 3xx redirect = сервер ответил = сайт живой.

    allow_redirects=False намеренно не идёт по Location, потому что
    urllib3 валится на percent-encoded IDN host в Location-header
    (firstel.ru → первыйэлемент.рф). Достаточно факта, что сервер ответил.
    """
    monkeypatch.setattr(requests, "Session", FakeSession)
    for code in (301, 302, 307, 308):
        FakeSession.calls = []
        FakeSession.head_status = code
        result = enrich_web.is_site_alive(f"https://r{code}.example", use_cache=False)
        assert result.is_alive is True, f"status {code} should be alive"
        assert result.status_code == code
        assert result.reason == "redirect"


def test_alive_check_does_not_follow_redirects(monkeypatch):
    """REGRESSION: запрос идёт с allow_redirects=False — иначе urllib3
    валится при попытке разрешить Location с percent-encoded кириллицей."""
    monkeypatch.setattr(requests, "Session", FakeSession)
    captured: dict = {}

    original_head = FakeSession.head

    def spy_head(self, url, **kwargs):
        captured["allow_redirects"] = kwargs.get("allow_redirects")
        return original_head(self, url, **kwargs)

    monkeypatch.setattr(FakeSession, "head", spy_head)
    enrich_web.is_site_alive("https://example.ru", use_cache=False)
    assert captured.get("allow_redirects") is False
