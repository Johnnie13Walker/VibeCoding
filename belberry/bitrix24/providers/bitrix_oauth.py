"""App OAuth provider для Bitrix24 в изолированном workspace.

Контракт:
- env namespace только BELBERRY_BITRIX24_*;
- state dir не имеет legacy default;
- refresh token URL берется только из state.server_endpoint;
- HTTP transport injectable для unit-тестов без сети.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from belberry.bitrix24.providers.logging import mask_secret, sanitize_bitrix_text

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
DEFAULT_TIMEOUT_SEC = 20
RATE_LIMIT_RETRY_DELAYS_SEC = (1.0, 2.0, 4.0)


class BitrixOAuthError(RuntimeError):
    """Безопасная ошибка Bitrix OAuth без токенов и полных REST URL."""

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
        payload: dict[str, Any] = {
            "ok": False,
            "status": self.to_status(),
            "message": self.message,
        }
        if self.code:
            payload["code"] = self.code
        if self.http_status is not None:
            payload["http_status"] = self.http_status
        return payload


@dataclass(frozen=True)
class BitrixHttpRequest:
    url: str
    method: str
    data: bytes
    headers: Mapping[str, str]


@dataclass(frozen=True)
class BitrixHttpResponse:
    status: int
    body: str


BitrixTransport = Callable[[BitrixHttpRequest, int], BitrixHttpResponse]


def urllib_transport(request: BitrixHttpRequest, timeout_sec: int) -> BitrixHttpResponse:
    """Production transport. Unit-тесты должны подставлять fake transport."""
    urllib_request = Request(
        request.url,
        method=request.method,
        data=request.data,
        headers=dict(request.headers),
    )
    try:
        with urlopen(urllib_request, timeout=timeout_sec) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
            return BitrixHttpResponse(status=int(response.status), body=body)
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        return BitrixHttpResponse(status=int(error.code), body=raw)
    except URLError as error:
        message = sanitize_bitrix_text(str(error.reason or error), endpoint=request.url)
        raise BitrixOAuthError(message, code="URL_ERROR") from error


def _env_dict(env: Mapping[str, Any] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    return {str(key): str(value) for key, value in source.items()}


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


def _parse_saved_at(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime(1970, 1, 1, tzinfo=MOSCOW_TZ)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=MOSCOW_TZ)
    return parsed.replace(tzinfo=MOSCOW_TZ) if parsed.tzinfo is None else parsed.astimezone(MOSCOW_TZ)


def _flatten_params(prefix: str, value: Any) -> list[tuple[str, str]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        result: list[tuple[str, str]] = []
        for key, nested in value.items():
            name = f"{prefix}[{key}]" if prefix else str(key)
            result.extend(_flatten_params(name, nested))
        return result
    if isinstance(value, (list, tuple, set)):
        result: list[tuple[str, str]] = []
        for nested in value:
            result.extend(_flatten_params(f"{prefix}[]", nested))
        return result
    return [(prefix, str(value))]


def _extract_result_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, Mapping):
        for key in ("items", "tasks", "events"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _is_rate_limit_error(error: BitrixOAuthError) -> bool:
    code = str(error.code or "").strip().upper()
    message = str(error.message or "").strip().lower()
    return (
        error.http_status == 429
        or code in {"QUERY_LIMIT_EXCEEDED", "TOO_MANY_REQUESTS", "HTTP_429"}
        or "too many requests" in message
        or "query limit exceeded" in message
    )


@dataclass(frozen=True)
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


class BitrixOAuth:
    """Читает isolated OAuth state и вызывает app-level Bitrix REST."""

    def __init__(
        self,
        *,
        state_dir: Path,
        state_file: Path | None = None,
        client_id: str = "",
        client_secret: str = "",
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
        transport: BitrixTransport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.state_dir = Path(state_dir).expanduser()
        self.state_file = Path(state_file).expanduser() if state_file else None
        self.client_id = str(client_id or "").strip()
        self.client_secret = str(client_secret or "").strip()
        self.timeout_sec = int(timeout_sec or DEFAULT_TIMEOUT_SEC)
        self.transport = transport
        self.sleep = sleep

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, Any] | None = None,
        *,
        transport: BitrixTransport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> "BitrixOAuth":
        env_data = _env_dict(env)
        state_dir_raw = str(env_data.get("BELBERRY_BITRIX24_APP_STATE_DIR") or "").strip()
        if not state_dir_raw:
            raise BitrixOAuthError(
                "BELBERRY_BITRIX24_APP_STATE_DIR не задан",
                code="APP_STATE_DIR_NOT_CONFIGURED",
                category="not_configured",
            )
        state_file_raw = str(env_data.get("BELBERRY_BITRIX24_APP_INSTALL_STATE_FILE") or "").strip()
        return cls(
            state_dir=Path(state_dir_raw),
            state_file=Path(state_file_raw) if state_file_raw else None,
            client_id=str(env_data.get("BELBERRY_BITRIX24_CLIENT_ID") or "").strip(),
            client_secret=str(env_data.get("BELBERRY_BITRIX24_CLIENT_SECRET") or "").strip(),
            timeout_sec=int(env_data.get("BELBERRY_BITRIX24_TIMEOUT_SEC") or DEFAULT_TIMEOUT_SEC),
            transport=transport,
            sleep=sleep,
        )

    def is_configured(self) -> bool:
        try:
            state = self.load_state()
        except BitrixOAuthError:
            return False
        return bool(state.access_token and state.client_endpoint)

    def summary(self) -> dict[str, Any]:
        try:
            state = self.load_state()
        except BitrixOAuthError as error:
            return {"ok": False, "status": error.to_status(), "message": error.message}
        return {
            "ok": True,
            "path": str(state.path),
            "saved_at": state.record.get("saved_at"),
            "domain": state.domain,
            "member_id": state.member_id,
            "status": state.status,
            "access_token": mask_secret(state.access_token),
            "refresh_token": mask_secret(state.refresh_token),
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
            raise BitrixOAuthError(
                "App OAuth state Bitrix не найден",
                code="APP_STATE_NOT_FOUND",
                category="not_configured",
            )
        return sorted(candidates, key=lambda item: item.saved_at, reverse=True)[0]

    def _persist_state(self, state: BitrixAppState) -> None:
        state.path.parent.mkdir(parents=True, exist_ok=True)
        target = state.path
        tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(state.record, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
            os.chmod(target, 0o600)
        finally:
            tmp.unlink(missing_ok=True)

    def _parse_error_payload(
        self,
        raw_body: str,
        *,
        http_status: int | None = None,
        endpoint: str = "",
    ) -> BitrixOAuthError:
        try:
            payload = json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            payload = {}
        code = str(payload.get("error") or "").strip() if isinstance(payload, Mapping) else ""
        raw_message = payload.get("error_description") if isinstance(payload, Mapping) else ""
        message = sanitize_bitrix_text(raw_message or code or "Bitrix request failed", endpoint=endpoint)
        category = "error"
        upper_code = code.upper()
        if upper_code == "EXPIRED_TOKEN" or "DENIED" in upper_code or "SCOPE" in upper_code:
            category = "access_denied"
        elif "METHOD_NOT_FOUND" in upper_code:
            category = "method_not_found"
        return BitrixOAuthError(message, code=code, category=category, http_status=http_status)

    def _request_json(self, request: BitrixHttpRequest, *, endpoint: str) -> dict[str, Any]:
        last_error: BitrixOAuthError | None = None
        for attempt, delay_sec in enumerate((0.0, *RATE_LIMIT_RETRY_DELAYS_SEC), start=1):
            if delay_sec > 0:
                self.sleep(delay_sec)
            try:
                response = self.transport(request, self.timeout_sec)
            except BitrixOAuthError as error:
                last_error = error
            except Exception as error:  # noqa: BLE001
                message = sanitize_bitrix_text(str(error), endpoint=endpoint)
                last_error = BitrixOAuthError(message, code="REQUEST_FAILED")
            else:
                raw = str(response.body or "")
                if int(response.status) >= 400:
                    last_error = self._parse_error_payload(raw, http_status=int(response.status), endpoint=endpoint)
                else:
                    try:
                        payload = json.loads(raw or "{}")
                    except json.JSONDecodeError as error:
                        raise BitrixOAuthError(f"Bitrix вернул невалидный JSON: {error}", code="INVALID_JSON") from None
                    if not isinstance(payload, dict):
                        raise BitrixOAuthError("Bitrix вернул неожиданный формат ответа", code="INVALID_PAYLOAD")
                    if payload.get("error"):
                        last_error = self._parse_error_payload(raw, endpoint=endpoint)
                    else:
                        return payload

            if last_error is None or not _is_rate_limit_error(last_error) or attempt > len(RATE_LIMIT_RETRY_DELAYS_SEC):
                raise last_error or BitrixOAuthError("Bitrix request failed", code="REQUEST_FAILED")

    def _call_payload_with_state(
        self,
        state: BitrixAppState,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not state.client_endpoint or not state.access_token:
            raise BitrixOAuthError(
                "В app OAuth state Bitrix нет access token",
                code="APP_STATE_INVALID",
                category="not_configured",
            )
        body_pairs = [("auth", state.access_token)]
        for key, value in (params or {}).items():
            body_pairs.extend(_flatten_params(str(key), value))
        endpoint = f"{state.client_endpoint}/{method}.json"
        request = BitrixHttpRequest(
            url=endpoint,
            method="POST",
            data=urlencode(body_pairs).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._request_json(request, endpoint=state.client_endpoint)

    def _refresh_url(self, state: BitrixAppState) -> str:
        if not state.server_endpoint:
            raise BitrixOAuthError(
                "В app OAuth state Bitrix нет server_endpoint для refresh",
                code="APP_SERVER_ENDPOINT_NOT_FOUND",
                category="not_configured",
            )
        parsed = urlparse(state.server_endpoint)
        if not parsed.scheme or not parsed.netloc:
            raise BitrixOAuthError(
                "server_endpoint Bitrix некорректен",
                code="APP_SERVER_ENDPOINT_INVALID",
                category="not_configured",
            )
        return f"{parsed.scheme}://{parsed.netloc}/oauth/token/"

    def refresh_access_token(self) -> BitrixAppState:
        state = self.load_state()
        if not self.client_id or not self.client_secret:
            raise BitrixOAuthError(
                "Для app OAuth Bitrix не заданы client_id/client_secret",
                code="APP_CLIENT_NOT_CONFIGURED",
                category="not_configured",
            )
        if not state.refresh_token:
            raise BitrixOAuthError(
                "В app OAuth state Bitrix нет refresh token",
                code="APP_REFRESH_NOT_FOUND",
                category="not_configured",
            )
        params = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": state.refresh_token,
        }
        refresh_url = self._refresh_url(state)
        request = BitrixHttpRequest(
            url=refresh_url,
            method="POST",
            data=urlencode(params).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        payload = self._request_json(request, endpoint=refresh_url)
        access_token = str(payload.get("access_token") or "").strip()
        refresh_token = str(payload.get("refresh_token") or "").strip()
        client_endpoint = str(payload.get("client_endpoint") or state.client_endpoint).strip()
        if not access_token or not refresh_token or not client_endpoint:
            raise BitrixOAuthError("Bitrix OAuth refresh вернул неполный payload", code="REFRESH_INVALID_PAYLOAD")

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
        except BitrixOAuthError as error:
            upper_code = str(error.code or "").upper()
            if not (error.http_status == 401 or upper_code == "EXPIRED_TOKEN"):
                raise
            state = self.refresh_access_token()
            payload = self._call_payload_with_state(state, method, params=params)
        if not payload and default is not None:
            return default
        return payload

    def call_method(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        default: Any = None,
    ) -> Any:
        payload = self.call_payload(method, params=params, default=None)
        result = payload.get("result")
        return default if result is None and default is not None else result

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
