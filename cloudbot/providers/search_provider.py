"""Search provider: адаптер к существующему JS provider."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

DEFAULT_PROVIDER = "duckduckgo"
LEGACY_DISABLED_PROVIDERS = frozenset({"brave", "kimi", "moonshot"})
DEFAULT_SEARCH_ENGINE = "duckduckgo"
DEFAULT_TIMEOUT_SECONDS = 10
SEARXNG_QUERY = "openai"


def _resolve_provider(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})
    raw_provider = str(
        cfg.get("provider") or os.getenv("SEARCH_PROVIDER") or os.getenv("search_provider") or DEFAULT_PROVIDER
    ).strip().lower()
    warnings: list[str] = []

    if raw_provider in LEGACY_DISABLED_PROVIDERS:
        warnings.append(f"provider={raw_provider} больше не поддерживается; принудительно используется {DEFAULT_PROVIDER}")
        raw_provider = DEFAULT_PROVIDER
    elif raw_provider != DEFAULT_PROVIDER:
        warnings.append(f"provider={raw_provider} не поддерживается; принудительно используется {DEFAULT_PROVIDER}")
        raw_provider = DEFAULT_PROVIDER

    base_url = str(
        cfg.get("base_url")
        or cfg.get("baseUrl")
        or os.getenv("SEARCH_BASE_URL")
        or os.getenv("SEARXNG_BASE_URL")
        or ""
    ).strip()
    raw_engine = str(
        cfg.get("engine") or os.getenv("SEARCH_ENGINE") or os.getenv("SEARXNG_ENGINE") or DEFAULT_SEARCH_ENGINE
    ).strip().lower()
    timeout_seconds = int(
        cfg.get("timeout_seconds")
        or cfg.get("timeout")
        or os.getenv("SEARCH_TIMEOUT_SECONDS")
        or os.getenv("SEARXNG_TIMEOUT_SECONDS")
        or DEFAULT_TIMEOUT_SECONDS
    )

    if raw_engine != DEFAULT_SEARCH_ENGINE:
        warnings.append(f"engine={raw_engine} не поддерживается; принудительно используется {DEFAULT_SEARCH_ENGINE}")
        raw_engine = DEFAULT_SEARCH_ENGINE
    if not base_url:
        warnings.append(
            "SEARCH_BASE_URL/SEARXNG_BASE_URL не задан; используется публичный DuckDuckGo fallback, он нестабилен из-за anti-bot"
        )

    cfg["provider"] = raw_provider
    cfg["base_url"] = base_url
    cfg["engine"] = raw_engine
    cfg["timeout_seconds"] = timeout_seconds
    cfg.pop("brave", None)
    cfg.pop("kimi", None)
    cfg.pop("moonshot", None)
    return {"provider": raw_provider, "config": cfg, "warnings": warnings}


def healthcheck(config: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = _resolve_provider(config)
    runtime_config = resolved["config"]
    base_url = str(runtime_config.get("base_url") or "").strip()
    if not base_url:
        return {
            "provider": resolved["provider"],
            "ok": True,
            "warnings": resolved["warnings"],
            "config": runtime_config,
        }

    try:
        probe = _probe_searxng(
            base_url=base_url,
            engine=str(runtime_config.get("engine") or DEFAULT_SEARCH_ENGINE),
            timeout_seconds=int(runtime_config.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
        )
    except Exception as error:  # noqa: BLE001
        return {"provider": resolved["provider"], "ok": False, "error": str(error), "warnings": resolved["warnings"]}

    return {
        "provider": resolved["provider"],
        "ok": True,
        "warnings": resolved["warnings"],
        "config": runtime_config,
        "probe": probe,
    }


def _probe_searxng(*, base_url: str, engine: str, timeout_seconds: int) -> dict[str, Any]:
    request = Request(
        _build_searxng_url(base_url, query=SEARXNG_QUERY, engine=engine, limit=1),
        headers={"Accept": "application/json", "User-Agent": "Cloudbot/1.0"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    return {
        "base_url": base_url.rstrip("/"),
        "engine": engine,
        "result_count": len(payload.get("results") or []),
    }


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
    # DuckDuckGo backend in SearXNG rejects locale filters in our runtime contour.
    if engine != DEFAULT_SEARCH_ENGINE:
        params["language"] = "ru"
    return f"{endpoint}?{urlencode(params)}"
