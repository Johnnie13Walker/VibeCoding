"""App OAuth для локального приложения Bitrix24."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
DEFAULT_TIMEOUT_SEC = 20
RATE_LIMIT_RETRY_DELAYS_SEC = (1.0, 2.0, 4.0)

BITRIX_ACCESS_DENIED_CODES = {
    "ACCESS_DENIED",
    "INSUFFICIENT_SCOPE",
    "ERROR_ACCESS_DENIED",
}

BITRIX_METHOD_NOT_FOUND_CODES = {
    "ERROR_METHOD_NOT_FOUND",
    "METHOD_NOT_FOUND",
}


class BitrixAPIError(RuntimeError):
    """Безопасная ошибка app OAuth Bitrix без секрета в сообщении."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "",
        category: str = "error",
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = str(message)
        self.code = str(code or "")
        self.category = str(category or "error")
        self.http_status = http_status

    def to_status(self) -> str:
        if self.category == "access_denied":
            return "access denied"
        if self.category == "method_not_found":
            return "method not found"
        if self.category == "not_configured":
            return "not configured"
        return "error"

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "ok": False,
            "status": self.to_status(),
            "message": self.message,
        }
        if self.code:
            payload["code"] = self.code
        if self.http_status is not None:
            payload["http_status"] = self.http_status
        return payload


def _mask_webhook_like_url(url: str | None) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return "***"
    return f"{parsed.scheme}://{parsed.netloc}/rest/***/***/"


def sanitize_bitrix_text(
    text: str | None,
    *,
    webhook_url: str | None = None,
    endpoint: str | None = None,
) -> str:
    safe = str(text or "").strip()
    if not safe:
        return "unknown error"

    for candidate in (str(webhook_url or "").strip(), str(endpoint or "").strip()):
        if candidate:
            safe = safe.replace(candidate, _mask_webhook_like_url(candidate))

    parts = safe.split()
    if any(part.startswith(("http://", "https://")) for part in parts):
        safe = " ".join(
            _mask_webhook_like_url(part) if part.startswith(("http://", "https://")) else part
            for part in parts
        )
    return safe


def _env_dict(env: Mapping[str, Any] | None = None) -> dict[str, str]:
    if env is None:
        return {str(key): str(value) for key, value in os.environ.items()}
    return {str(key): str(value) for key, value in env.items()}


def _pick(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _payload_has_auth(payload: Mapping[str, Any]) -> bool:
    return bool(
        _pick(payload, "AUTH_ID", "auth_id", "access_token", "auth[access_token]")
        and _pick(payload, "client_endpoint", "CLIENT_ENDPOINT", "auth[client_endpoint]")
    )


def _flatten_params(prefix: str, value: Any) -> list[tuple[str, str]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        items: list[tuple[str, str]] = []
        for key, nested_value in value.items():
            key_name = f"{prefix}[{key}]" if prefix else str(key)
            items.extend(_flatten_params(key_name, nested_value))
        return items
    if isinstance(value, (list, tuple, set)):
        items: list[tuple[str, str]] = []
        for nested_value in value:
            items.extend(_flatten_params(f"{prefix}[]", nested_value))
        return items
    return [(prefix, str(value))]


def _extract_result_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "tasks", "events"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _parse_saved_at(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime(1970, 1, 1, tzinfo=MOSCOW_TZ)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=MOSCOW_TZ)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=MOSCOW_TZ)
    return parsed.astimezone(MOSCOW_TZ)


def _mask_secret(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return "***"
    return f"{raw[:4]}***{raw[-4:]}"


def _is_rate_limit_error(error: BitrixAPIError) -> bool:
    upper_code = str(error.code or "").strip().upper()
    message = str(error.message or "").strip().lower()
    if error.http_status == 429:
        return True
    if upper_code in {"QUERY_LIMIT_EXCEEDED", "TOO_MANY_REQUESTS", "HTTP_429"}:
        return True
    return "too many requests" in message or "query limit exceeded" in message


@dataclass
class BitrixAppState:
    path: Path
    record: dict[str, Any]

    @property
    def payload(self) -> dict[str, Any]:
        payload = self.record.get("payload")
        return payload if isinstance(payload, dict) else {}

    @property
    def saved_at(self) -> datetime:
        return _parse_saved_at(self.record.get("saved_at"))

    @property
    def domain(self) -> str:
        return _pick(self.payload, "DOMAIN", "domain", "auth[domain]")

    @property
    def client_endpoint(self) -> str:
        return _pick(self.payload, "client_endpoint", "CLIENT_ENDPOINT", "auth[client_endpoint]").rstrip("/")

    @property
    def server_endpoint(self) -> str:
        return _pick(self.payload, "server_endpoint", "SERVER_ENDPOINT", "auth[server_endpoint]").rstrip("/")

    @property
    def access_token(self) -> str:
        return _pick(self.payload, "AUTH_ID", "auth_id", "access_token", "auth[access_token]")

    @property
    def refresh_token(self) -> str:
        return _pick(self.payload, "REFRESH_ID", "refresh_id", "refresh_token", "auth[refresh_token]")

    @property
    def member_id(self) -> str:
        return _pick(self.payload, "member_id", "MEMBER_ID", "auth[member_id]")

    @property
    def status(self) -> str:
        return _pick(self.payload, "status", "STATUS", "auth[status]")


class BitrixAppAuth:
    """Читает install/handler state локального приложения и вызывает app-level REST."""

    def __init__(
        self,
        *,
        state_dir: Path,
        state_file: Path | None = None,
        client_id: str = "",
        client_secret: str = "",
        oauth_token_url: str = "",
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self.state_dir = state_dir
        self.state_file = state_file
        self.client_id = str(client_id or "").strip()
        self.client_secret = str(client_secret or "").strip()
        self.oauth_token_url = str(oauth_token_url or "").strip()
        self.timeout_sec = int(timeout_sec or DEFAULT_TIMEOUT_SEC)

    @classmethod
    def from_env(cls, env: Mapping[str, Any] | None = None) -> "BitrixAppAuth":
        env_data = _env_dict(env)
        state_dir = Path(str(env_data.get("BITRIX_APP_STATE_DIR") or "/opt/openclaw/state/bitrix_app")).expanduser()
        state_file_raw = str(env_data.get("BITRIX_APP_INSTALL_STATE_FILE") or "").strip()
        state_file = Path(state_file_raw).expanduser() if state_file_raw else None
        return cls(
            state_dir=state_dir,
            state_file=state_file,
            client_id=str(env_data.get("BITRIX_CLIENT_ID") or "").strip(),
            client_secret=str(env_data.get("BITRIX_CLIENT_SECRET") or "").strip(),
            oauth_token_url=str(env_data.get("BITRIX_OAUTH_TOKEN_URL") or "").strip(),
            timeout_sec=int(env_data.get("BITRIX_TIMEOUT_SEC") or DEFAULT_TIMEOUT_SEC),
        )

    def is_configured(self) -> bool:
        try:
            state = self.load_state()
        except BitrixAPIError:
            return False
        return bool(state.access_token and state.client_endpoint)

    def summary(self) -> dict[str, Any]:
        try:
            state = self.load_state()
        except BitrixAPIError as error:
            return {"ok": False, "status": error.to_status(), "message": error.message}
        return {
            "ok": True,
            "path": str(state.path),
            "saved_at": state.record.get("saved_at"),
            "domain": state.domain,
            "member_id": state.member_id,
            "status": state.status,
            "access_token": _mask_secret(state.access_token),
            "refresh_token": _mask_secret(state.refresh_token),
        }

    def _load_record(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        payload = raw.get("payload")
        if not isinstance(payload, dict) or not _payload_has_auth(payload):
            return None
        return raw

    def load_state(self) -> BitrixAppState:
        candidates: list[BitrixAppState] = []
        if self.state_file is not None:
            record = self._load_record(self.state_file)
            if record:
                candidates.append(BitrixAppState(self.state_file, record))
        else:
            for name in ("handler.latest.json", "install.latest.json"):
                path = self.state_dir / name
                record = self._load_record(path)
                if record:
                    candidates.append(BitrixAppState(path, record))

        if not candidates:
            raise BitrixAPIError(
                "App OAuth state Bitrix не найден",
                code="APP_STATE_NOT_FOUND",
                category="not_configured",
            )

        candidates.sort(key=lambda item: item.saved_at, reverse=True)
        return candidates[0]

    def _persist_state(self, state: BitrixAppState) -> None:
        state.path.parent.mkdir(parents=True, exist_ok=True)
        target = state.path
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(state.record, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temp, 0o600)
        temp.replace(target)

    def _parse_error_payload(
        self,
        raw_body: str,
        *,
        http_status: int | None = None,
        endpoint: str = "",
    ) -> BitrixAPIError:
        try:
            payload = json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            payload = {}

        code = str(payload.get("error") or "").strip()
        message = sanitize_bitrix_text(
            payload.get("error_description") or payload.get("error") or "Bitrix request failed",
            endpoint=endpoint,
        )
        category = "error"
        upper_code = code.upper()
        if upper_code == "EXPIRED_TOKEN":
            category = "access_denied"
        elif "DENIED" in upper_code or "SCOPE" in upper_code:
            category = "access_denied"
        elif "METHOD_NOT_FOUND" in upper_code:
            category = "method_not_found"
        return BitrixAPIError(
            message,
            code=code,
            category=category,
            http_status=http_status,
        )

    def _request_json(self, request: Request, *, endpoint: str) -> dict[str, Any]:
        last_error: BitrixAPIError | None = None
        for attempt, delay_sec in enumerate((0.0, *RATE_LIMIT_RETRY_DELAYS_SEC), start=1):
            if delay_sec > 0:
                time.sleep(delay_sec)
            try:
                with urlopen(request, timeout=self.timeout_sec) as response:  # noqa: S310
                    raw = response.read().decode("utf-8", errors="replace")
            except HTTPError as error:
                raw = ""
                try:
                    raw = error.read().decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    raw = ""
                if raw:
                    last_error = self._parse_error_payload(raw, http_status=int(error.code), endpoint=endpoint)
                else:
                    last_error = BitrixAPIError(
                        f"Bitrix HTTP {int(error.code)}",
                        code=f"HTTP_{int(error.code)}",
                        category="error",
                        http_status=int(error.code),
                    )
            except URLError as error:
                reason = sanitize_bitrix_text(str(error.reason or error), endpoint=endpoint)
                last_error = BitrixAPIError(reason, code="URL_ERROR", category="error")
            except Exception as error:  # noqa: BLE001
                message = sanitize_bitrix_text(str(error), endpoint=endpoint)
                last_error = BitrixAPIError(message, code="REQUEST_FAILED", category="error")
            else:
                try:
                    payload = json.loads(raw or "{}")
                except json.JSONDecodeError as error:
                    raise BitrixAPIError(
                        f"Bitrix вернул невалидный JSON: {error}",
                        code="INVALID_JSON",
                    ) from None

                if payload.get("error"):
                    last_error = self._parse_error_payload(raw, endpoint=endpoint)
                elif not isinstance(payload, dict):
                    raise BitrixAPIError("Bitrix вернул неожиданный формат ответа", code="INVALID_PAYLOAD")
                else:
                    return payload

            if last_error is None or not _is_rate_limit_error(last_error) or attempt > len(RATE_LIMIT_RETRY_DELAYS_SEC):
                raise last_error or BitrixAPIError("Bitrix request failed", code="REQUEST_FAILED")

        raise last_error or BitrixAPIError("Bitrix request failed", code="REQUEST_FAILED")

    def _call_payload_with_state(
        self,
        state: BitrixAppState,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not state.client_endpoint or not state.access_token:
            raise BitrixAPIError(
                "В app OAuth state Bitrix нет access token",
                code="APP_STATE_INVALID",
                category="not_configured",
            )
        body_pairs = [("auth", state.access_token)]
        for key, value in (params or {}).items():
            body_pairs.extend(_flatten_params(str(key), value))
        endpoint = f"{state.client_endpoint}/{method}.json"
        request = Request(
            endpoint,
            method="POST",
            data=urlencode(body_pairs).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._request_json(request, endpoint=state.client_endpoint)

    def _refresh_urls(self, state: BitrixAppState) -> list[str]:
        candidates: list[str] = []

        if self.oauth_token_url:
            candidates.append(self.oauth_token_url.rstrip("/"))

        if state.server_endpoint:
            parsed = urlparse(state.server_endpoint)
            if parsed.scheme and parsed.netloc:
                candidates.append(f"{parsed.scheme}://{parsed.netloc}/oauth/token/")

        if state.domain:
            candidates.append(f"https://{state.domain}/oauth/token/")

        candidates.extend(
            [
                "https://oauth.bitrix.info/oauth/token/",
                "https://oauth.bitrix24.tech/oauth/token/",
            ]
        )

        unique: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            normalized = str(item or "").strip().rstrip("/") + "/"
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
        return unique

    def refresh_access_token(self) -> BitrixAppState:
        state = self.load_state()
        if not self.client_id or not self.client_secret:
            raise BitrixAPIError(
                "Для app OAuth Bitrix не заданы client_id/client_secret",
                code="APP_CLIENT_NOT_CONFIGURED",
                category="not_configured",
            )
        if not state.refresh_token:
            raise BitrixAPIError(
                "В app OAuth state Bitrix нет refresh token",
                code="APP_REFRESH_NOT_FOUND",
                category="not_configured",
            )

        last_error: BitrixAPIError | None = None
        params = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": state.refresh_token,
        }

        for refresh_url in self._refresh_urls(state):
            request = Request(
                refresh_url,
                method="POST",
                data=urlencode(params).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                payload = self._request_json(request, endpoint=refresh_url)
            except BitrixAPIError as error:
                last_error = error
                continue

            access_token = str(payload.get("access_token") or "").strip()
            refresh_token = str(payload.get("refresh_token") or "").strip()
            client_endpoint = str(payload.get("client_endpoint") or state.client_endpoint).strip()
            if not access_token or not refresh_token or not client_endpoint:
                last_error = BitrixAPIError(
                    "Bitrix OAuth refresh вернул неполный payload",
                    code="REFRESH_INVALID_PAYLOAD",
                )
                continue

            state.payload["auth[access_token]"] = access_token
            state.payload["auth[refresh_token]"] = refresh_token
            state.payload["auth[client_endpoint]"] = client_endpoint.rstrip("/")
            if payload.get("server_endpoint"):
                state.payload["auth[server_endpoint]"] = str(payload.get("server_endpoint")).rstrip("/")
            if payload.get("domain"):
                state.payload["auth[domain]"] = str(payload.get("domain")).strip()
            if payload.get("member_id"):
                state.payload["auth[member_id]"] = str(payload.get("member_id")).strip()
            if payload.get("status"):
                state.payload["auth[status]"] = str(payload.get("status")).strip()

            summary = state.record.setdefault("summary", {})
            if isinstance(summary, dict):
                summary.update(
                    {
                        "domain": state.domain,
                        "member_id": state.member_id,
                        "status": state.status,
                        "auth_present": True,
                        "refresh_present": True,
                    }
                )
            state.record["saved_at"] = datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")
            state.record["auth_refreshed_at"] = state.record["saved_at"]
            self._persist_state(state)
            return state

        if last_error is not None:
            raise BitrixAPIError(
                f"Bitrix OAuth refresh не удался: {last_error.message}",
                code=last_error.code or "REFRESH_FAILED",
                category=last_error.category,
                http_status=last_error.http_status,
            )
        raise BitrixAPIError("Bitrix OAuth refresh не удался", code="REFRESH_FAILED")

    def call_method(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        default: Any = None,
    ) -> Any:
        payload = self.call_payload(method, params=params, default=None)
        result = payload.get("result")
        if result is None and default is not None:
            return default
        return result

    def call_payload(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        default: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self.load_state()
        try:
            payload = self._call_payload_with_state(state, method, params=params)
        except BitrixAPIError as error:
            upper_code = str(error.code or "").upper()
            should_refresh = error.http_status == 401 or upper_code == "EXPIRED_TOKEN"
            if not should_refresh:
                raise
            state = self.refresh_access_token()
            payload = self._call_payload_with_state(state, method, params=params)

        if not payload and default is not None:
            return default
        return payload

    def list_method(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        start = 0
        request_params = dict(params or {})

        while True:
            payload = self.call_payload(method, params={**request_params, "start": start}, default={})
            chunk = _extract_result_list(payload.get("result"))
            items.extend(chunk)

            if limit and len(items) >= limit:
                return items[:limit]

            next_value = payload.get("next")
            if next_value is None or not chunk:
                break
            try:
                next_start = int(next_value)
            except (TypeError, ValueError):
                break
            if next_start <= start:
                break
            start = next_start

        return items[:limit] if limit else items
