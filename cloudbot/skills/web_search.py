"""DuckDuckGo-only skill для веб-поиска."""

from __future__ import annotations

import json
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from cloudbot.providers import search_provider

DUCKDUCKGO_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
DEFAULT_TIMEOUT_SECONDS = 10
MAX_RESULTS = 10


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture_title = False
        self._capture_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        classes = attrs_map.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._flush_current()
            self._current = {
                "title": "",
                "url": _normalize_result_url(attrs_map.get("href", "")),
                "snippet": "",
            }
            self._capture_title = True
            self._capture_snippet = False
            return
        if self._current and tag in {"a", "div"} and "result__snippet" in classes:
            self._capture_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            self._capture_title = False
        elif tag in {"a", "div"} and self._capture_snippet:
            self._capture_snippet = False

    def handle_data(self, data: str) -> None:
        if not self._current:
            return
        if self._capture_title:
            self._current["title"] = f"{self._current.get('title', '')}{data}"
        elif self._capture_snippet:
            self._current["snippet"] = f"{self._current.get('snippet', '')}{data}"

    def close(self) -> None:
        super().close()
        self._flush_current()

    def _flush_current(self) -> None:
        if not self._current or not self._current.get("url"):
            self._current = None
            return
        self.results.append(
            {
                "title": _clean_text(self._current.get("title", "")),
                "url": self._current.get("url", ""),
                "snippet": _clean_text(self._current.get("snippet", "")),
            }
        )
        self._current = None
        self._capture_title = False
        self._capture_snippet = False


def run(payload: dict[str, Any], providers: dict[str, Any] | None = None) -> dict[str, Any]:
    providers_data = providers or {}
    resolved = search_provider._resolve_provider(dict(providers_data.get("search") or {}))
    query = " ".join(str(payload.get("query") or "").strip().split())
    limit = max(1, min(int(payload.get("limit") or 5), MAX_RESULTS))
    if not query:
        return {
            "skill": "web_search",
            "provider": resolved["provider"],
            "ok": False,
            "results": [],
            "warnings": resolved["warnings"],
            "error": "Пустой поисковый запрос.",
        }

    runtime_config = dict(resolved["config"])
    try:
        results, backend_warning = _search_with_runtime(query, limit=limit, runtime_config=runtime_config)
    except Exception as error:  # noqa: BLE001
        return {
            "skill": "web_search",
            "provider": resolved["provider"],
            "ok": False,
            "results": [],
            "warnings": resolved["warnings"],
            "error": str(error),
        }

    return {
        "skill": "web_search",
        "provider": resolved["provider"],
        "ok": True,
        "query": query,
        "results": results,
        "warnings": [
            *resolved["warnings"],
            *([backend_warning] if backend_warning else []),
        ],
    }


def _search_with_runtime(query: str, *, limit: int, runtime_config: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    base_url = str(runtime_config.get("base_url") or "").strip()
    engine = str(runtime_config.get("engine") or search_provider.DEFAULT_SEARCH_ENGINE).strip().lower()
    timeout_seconds = int(runtime_config.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    if base_url:
        return _searxng_search(
            base_url=base_url,
            engine=engine,
            query=query,
            limit=limit,
            timeout_seconds=timeout_seconds,
        ), ""
    return _duckduckgo_search(query, limit=limit), (
        "Использован публичный DuckDuckGo fallback без SearXNG; возможна нестабильность из-за anti-bot"
    )


def _searxng_search(
    *,
    base_url: str,
    engine: str,
    query: str,
    limit: int,
    timeout_seconds: int,
) -> list[dict[str, str]]:
    request = Request(
        _build_searxng_url(base_url, query=query, engine=engine, limit=limit),
        headers={"Accept": "application/json", "User-Agent": "Cloudbot/1.0"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))

    unique_results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in payload.get("results") or []:
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        unique_results.append(
            {
                "title": _clean_text(str(item.get("title") or "")),
                "url": url,
                "snippet": _clean_text(str(item.get("content") or item.get("snippet") or "")),
            }
        )
        if len(unique_results) >= limit:
            break
    return unique_results


def _duckduckgo_search(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    request_url = f"{DUCKDUCKGO_HTML_ENDPOINT}?{urlencode({'q': query})}"
    request = Request(
        request_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ru,en;q=0.8",
        },
    )
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        html = response.read().decode("utf-8", errors="replace")
    parser = _DuckDuckGoHTMLParser()
    parser.feed(html)
    parser.close()

    unique_results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in parser.results:
        url = item.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        unique_results.append(item)
        if len(unique_results) >= limit:
            break
    return unique_results


def _build_searxng_url(base_url: str, *, query: str, engine: str, limit: int) -> str:
    normalized_base = base_url.rstrip("/") + "/"
    endpoint = urljoin(normalized_base, "search")
    params: dict[str, Any] = {
        "q": query,
        "format": "json",
        "engines": engine,
        "pageno": 1,
        "safesearch": 0,
        "categories": "general",
    }
    # DuckDuckGo backend in SearXNG is stable only without locale filters.
    if engine != search_provider.DEFAULT_SEARCH_ENGINE:
        params["language"] = "ru"
    return f"{endpoint}?{urlencode(params)}"


def _normalize_result_url(url: str) -> str:
    raw_url = unescape(url or "").strip()
    if not raw_url:
        return ""
    if raw_url.startswith("//"):
        raw_url = f"https:{raw_url}"
    parsed = urlparse(raw_url)
    query = parse_qs(parsed.query)
    redirected = query.get("uddg")
    if redirected:
        return redirected[0]
    return raw_url


def _clean_text(value: str) -> str:
    normalized = unescape(value or "")
    normalized = re.sub(r"\s+", " ", normalized, flags=re.MULTILINE)
    return normalized.strip()
