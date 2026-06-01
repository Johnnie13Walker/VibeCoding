import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

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


def call(method: str, params: dict[str, Any] | None = None, retries: int = 3, timeout: int = 60):
    endpoint, token = _load_auth()
    params = params or {}
    data = urllib.parse.urlencode([("auth", token), *_flatten_params(params)]).encode()
    url = f"{endpoint}/{method}"

    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                if attempt == retries - 1:
                    return {"error": _mask_auth(str(exc)), "body": _mask_auth(body[:300])}
        except Exception as exc:
            if attempt == retries - 1:
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
