import json
import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests

DEFAULT_STATE_PATH = (
    "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json"
)


def _flatten_params(params: dict[str, Any]) -> list[tuple[str, Any]]:
    flat: list[tuple[str, Any]] = []

    def encode(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                encode(f"{prefix}[{key}]", child)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                encode(f"{prefix}[{index}]", child)
        else:
            flat.append((prefix, value))

    for key, value in params.items():
        encode(key, value)
    return flat


def _load_auth() -> tuple[str, str]:
    state_path = Path(os.environ.get("BITRIX_STATE_PATH", DEFAULT_STATE_PATH))
    payload = json.loads(state_path.read_text())["payload"]
    endpoint = payload["auth[client_endpoint]"].rstrip("/")
    token = payload["auth[access_token]"]
    return endpoint, token


def _mask_auth(text: str) -> str:
    return re.sub(r"auth=[^&\s]+", "auth=***", text)


def ensure_token_fresh() -> None:
    script = os.environ.get("BITRIX_SYNC_SCRIPT")
    if not script or not Path(script).exists():
        return
    subprocess.run(["bash", script], check=True)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


_SESSION: requests.Session | None = None


def _http_session() -> requests.Session:
    # Одна сессия с keep-alive переиспользует TLS-соединение на ВСЕ вызовы.
    # Раньше urllib открывал новый хендшейк на каждый запрос — на Hetzner→Bitrix
    # сотни мелких вызовов (пагинация + per-user + per-deal) давали ~17 мин/день.
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def call(method: str, params: dict[str, Any] | None = None, retries: int = 3, timeout: int = 60):
    endpoint, token = _load_auth()
    params = params or {}
    data = urllib.parse.urlencode([("auth", token), *_flatten_params(params)])
    url = f"{endpoint}/{method}"
    effective_retries = _env_int("BITRIX_HTTP_RETRIES", retries)
    effective_timeout = _env_int("BITRIX_HTTP_TIMEOUT", timeout)

    for attempt in range(effective_retries):
        try:
            response = _http_session().post(url, data=data, timeout=effective_timeout)
            try:
                return response.json()
            except ValueError:
                # не-JSON тело (HTML-ошибка и т.п.) — Bitrix-ошибки приходят JSON
                if attempt == effective_retries - 1:
                    return {
                        "error": _mask_auth(f"HTTP {response.status_code}"),
                        "body": _mask_auth(response.text[:300]),
                    }
        except Exception as exc:
            if attempt == effective_retries - 1:
                return {"error": _mask_auth(str(exc))}
            time.sleep(1.5 * (attempt + 1))
    return {"error": "Bitrix request failed"}


def fetch_all(
    method: str,
    params: dict[str, Any] | None = None,
    idfield: str = "ID",
    cap: int = 5000,
) -> list[dict[str, Any]]:
    params = dict(params or {})
    params.setdefault("order", {})[idfield] = "ASC"
    output: list[dict[str, Any]] = []
    last: Any = 0

    while len(output) < cap:
        page_params = dict(params)
        page_params["filter"] = dict(page_params.get("filter") or {})
        page_params["filter"][f">{idfield}"] = last
        page_params["start"] = -1
        response = call(method, page_params)
        if isinstance(response, dict) and response.get("error") and "result" not in response:
            # Ошибка REST/Bitrix при сборе списка — НЕ продолжать с пустым
            # результатом (иначе отчёт «0 сделок/встреч» уйдёт как валидный).
            raise RuntimeError(f"Bitrix {method} failed: {response.get('error')}")
        result = response.get("result") if isinstance(response, dict) else None
        if isinstance(result, dict) and "items" in result:
            result = result["items"]
        if not result:
            break
        output.extend(result)
        last = result[-1].get(idfield) or result[-1].get(idfield.lower()) or result[-1].get("id")
        if last is None:
            break

    return output[:cap]
