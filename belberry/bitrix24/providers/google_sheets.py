"""Read-only Google Sheets provider через service account JWT."""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
DEFAULT_TIMEOUT_SEC = 20
READ_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
TOKEN_AUDIENCE = "https://oauth2.googleapis.com/token"
TOKEN_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
RETRY_DELAYS_SEC = (1.0, 2.0)
READ_METHODS = ("spreadsheets.values.get", "spreadsheets.get")


@dataclass(frozen=True)
class SheetSnapshot:
    sheet_id: str
    sheet_name: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    fetched_at_msk: str


@dataclass(frozen=True)
class Response:
    status: int
    body: str


HttpTransport = Callable[[Request, int], Response]


class GoogleSheetsError(RuntimeError):
    """Безопасная ошибка Google Sheets provider без private_key/JWT."""


def urllib_transport(request: Request, timeout_sec: int) -> Response:
    """Production HTTP transport. Unit-тесты должны подставлять fake transport."""
    try:
        with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
            return Response(status=int(response.status), body=body)
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        return Response(status=int(error.code), body=raw)
    except URLError as error:
        raise GoogleSheetsError(f"Google Sheets request failed: {error.reason or error}") from error


def _env_dict(env: Mapping[str, Any] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    return {str(key): str(value) for key, value in source.items()}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _json_b64url(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _b64url(raw)


def _now_msk(now_utc: Callable[[], datetime]) -> str:
    value = now_utc()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MOSCOW_TZ).isoformat(timespec="seconds")


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise GoogleSheetsError("Google service account JSON file not found") from error
    except OSError as error:
        raise GoogleSheetsError(f"Google service account JSON cannot be read: {error}") from error
    except json.JSONDecodeError as error:
        raise GoogleSheetsError("Google service account JSON is invalid") from error
    if not isinstance(payload, dict):
        raise GoogleSheetsError("Google service account JSON must be an object")
    return payload


def _require_text(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise GoogleSheetsError(f"Google service account JSON missing {key}")
    return value


def _sign_rs256(private_key_pem: str, signing_input: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except Exception as error:  # noqa: BLE001
        raise GoogleSheetsError(
            "RS256 signing requires cryptography in this environment; no service-account JWT was sent"
        ) from error
    try:
        key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
        return key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    except Exception as error:  # noqa: BLE001
        raise GoogleSheetsError("Google service account private_key is invalid") from error


def _build_jwt_assertion(
    *,
    client_email: str,
    private_key: str,
    token_uri: str,
    now: datetime,
) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    iat = int(now.timestamp())
    exp = int((now + timedelta(minutes=55)).timestamp())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": client_email,
        "scope": READ_SCOPE,
        "aud": token_uri,
        "iat": iat,
        "exp": exp,
    }
    signing_input = f"{_json_b64url(header)}.{_json_b64url(claims)}".encode("ascii")
    return f"{signing_input.decode('ascii')}.{_b64url(_sign_rs256(private_key, signing_input))}"


def _parse_json_response(response: Response, *, context: str) -> dict[str, Any]:
    try:
        payload = json.loads(response.body or "{}")
    except json.JSONDecodeError as error:
        raise GoogleSheetsError(f"{context}: Google returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise GoogleSheetsError(f"{context}: Google returned unexpected payload")
    if int(response.status) >= 400:
        detail = payload.get("error") if isinstance(payload.get("error"), Mapping) else {}
        message = str(detail.get("message") or payload.get("error_description") or "Google request failed")
        raise GoogleSheetsError(f"{context}: {message}")
    return payload


def _should_retry(response: Response) -> bool:
    return int(response.status) in {429, 500, 502, 503, 504}


def _string_rows(values: Any) -> tuple[tuple[str, ...], ...]:
    if not isinstance(values, list):
        return ()
    rows: list[tuple[str, ...]] = []
    for row in values:
        if isinstance(row, list):
            rows = [*rows, tuple(str(cell) for cell in row)]
    return tuple(rows)


class GoogleSheetsClient:
    def __init__(
        self,
        *,
        service_account_path: Path,
        transport: HttpTransport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self.service_account_path = Path(service_account_path).expanduser()
        self.transport = transport
        self.sleep = sleep
        self.now_utc = now_utc
        self.timeout_sec = int(timeout_sec or DEFAULT_TIMEOUT_SEC)
        self._service_account: dict[str, Any] | None = None
        self._access_token = ""
        self._access_token_expires_at = datetime(1970, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, Any] | None = None,
        *,
        transport: HttpTransport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> "GoogleSheetsClient":
        env_data = _env_dict(env)
        raw_path = str(env_data.get("BELBERRY_BITRIX24_GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
        if not raw_path:
            raise GoogleSheetsError("BELBERRY_BITRIX24_GOOGLE_SERVICE_ACCOUNT_JSON не задан")
        return cls(service_account_path=Path(raw_path), transport=transport, sleep=sleep, now_utc=now_utc)

    def _service_account_payload(self) -> dict[str, Any]:
        if self._service_account is None:
            self._service_account = _load_json_object(self.service_account_path)
        return self._service_account

    def _token_uri(self) -> str:
        payload = self._service_account_payload()
        return str(payload.get("token_uri") or TOKEN_AUDIENCE).strip()

    def _send(self, request: Request, *, context: str) -> dict[str, Any]:
        last_response: Response | None = None
        for attempt, delay_sec in enumerate((0.0, *RETRY_DELAYS_SEC), start=1):
            if delay_sec > 0:
                self.sleep(delay_sec)
            response = self.transport(request, self.timeout_sec)
            last_response = response
            if _should_retry(response) and attempt <= len(RETRY_DELAYS_SEC):
                continue
            return _parse_json_response(response, context=context)

    def _access_token_value(self) -> str:
        now = self.now_utc()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        if self._access_token and now < self._access_token_expires_at:
            return self._access_token
        payload = self._service_account_payload()
        token_uri = self._token_uri()
        assertion = _build_jwt_assertion(
            client_email=_require_text(payload, "client_email"),
            private_key=_require_text(payload, "private_key"),
            token_uri=token_uri,
            now=now,
        )
        request = Request(
            token_uri,
            method="POST",
            data=urlencode({"grant_type": TOKEN_GRANT_TYPE, "assertion": assertion}).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_payload = self._send(request, context="google token")
        token = str(token_payload.get("access_token") or "").strip()
        if not token:
            raise GoogleSheetsError("google token: access_token missing")
        try:
            expires_in = int(token_payload.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600
        self._access_token = token
        self._access_token_expires_at = now + timedelta(seconds=max(60, expires_in - 60))
        return token

    def _authed_get(self, url: str, *, context: str) -> dict[str, Any]:
        request = Request(url, method="GET", headers={"Authorization": f"Bearer {self._access_token_value()}"})
        return self._send(request, context=context)

    def metadata(self, sheet_id: str) -> dict[str, Any]:
        clean_id = str(sheet_id or "").strip()
        if not clean_id:
            raise GoogleSheetsError("sheet_id is required")
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(clean_id, safe='')}"
        return self._authed_get(url, context="spreadsheets.get")

    def read_snapshot(self, sheet_id: str, sheet_name: str) -> SheetSnapshot:
        clean_id = str(sheet_id or "").strip()
        clean_name = str(sheet_name or "").strip()
        if not clean_id:
            raise GoogleSheetsError("sheet_id is required")
        if not clean_name:
            raise GoogleSheetsError("sheet_name is required")
        metadata = self.metadata(clean_id)
        sheets = metadata.get("sheets")
        sheet_names = {
            str(item.get("properties", {}).get("title") or "")
            for item in sheets
            if isinstance(item, Mapping) and isinstance(item.get("properties"), Mapping)
        } if isinstance(sheets, list) else set()
        if clean_name not in sheet_names:
            raise GoogleSheetsError(f"sheet not found: {clean_name}")
        range_name = quote(f"{clean_name}!A:Z", safe="")
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(clean_id, safe='')}/values/{range_name}"
        payload = self._authed_get(url, context="spreadsheets.values.get")
        rows = _string_rows(payload.get("values"))
        header = rows[0] if rows else ()
        return SheetSnapshot(
            sheet_id=clean_id,
            sheet_name=clean_name,
            header=header,
            rows=rows[1:] if len(rows) > 1 else (),
            fetched_at_msk=_now_msk(self.now_utc),
        )


def sheets_methods_used() -> tuple[str, ...]:
    """Декларация read-only Google Sheets API methods."""
    return READ_METHODS
