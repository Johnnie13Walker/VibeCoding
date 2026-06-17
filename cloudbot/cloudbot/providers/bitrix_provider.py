"""Безопасный Bitrix provider для CRM и Sales Copilot."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_SEC = 20
RATE_LIMIT_RETRY_DELAYS_SEC = (1.0, 2.0)
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
    """Безопасная ошибка Bitrix API без секрета в сообщении."""

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


def _env_dict(env: Mapping[str, Any] | None = None) -> dict[str, str]:
    if env is None:
        return {str(key): str(value) for key, value in os.environ.items()}
    return {str(key): str(value) for key, value in env.items()}


def _read_fixture_payload(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(raw, dict):
        return {}
    return raw


def _flatten_params(prefix: str, value: Any) -> list[tuple[str, str]]:
    if value is None:
        return []

    if isinstance(value, dict):
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


def mask_bitrix_webhook_url(url: str | None) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return "https://portal/rest/***/***/"
    return urlunparse((parsed.scheme, parsed.netloc, "/rest/***/***/", "", "", ""))


def sanitize_bitrix_text(
    text: str | None,
    *,
    webhook_url: str | None = None,
    endpoint: str | None = None,
) -> str:
    safe = str(text or "").strip()
    if not safe:
        return "unknown error"

    for marker in ("http://", "https://"):
        if marker in safe:
            parts = safe.split()
            safe = " ".join(
                mask_bitrix_webhook_url(part) if part.startswith(("http://", "https://")) else part
                for part in parts
            )

    target_url = str(webhook_url or endpoint or "").strip()
    if target_url:
        safe = safe.replace(target_url, mask_bitrix_webhook_url(target_url))
    return safe


def _normalize_webhook_url(url: str | None) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    path = parsed.path or "/"
    if path.endswith(".json"):
        path = path.rsplit("/", 1)[0]
    if not path.endswith("/"):
        path += "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _classify_error_code(code: str) -> str:
    upper_code = str(code or "").strip().upper()
    if upper_code in BITRIX_ACCESS_DENIED_CODES or "DENIED" in upper_code or "SCOPE" in upper_code:
        return "access_denied"
    if upper_code in BITRIX_METHOD_NOT_FOUND_CODES or "METHOD_NOT_FOUND" in upper_code:
        return "method_not_found"
    return "error"


def _is_rate_limit_error(error: BitrixAPIError) -> bool:
    upper_code = str(error.code or "").strip().upper()
    message = str(error.message or "").strip().lower()
    if error.http_status == 429:
        return True
    if upper_code in {"QUERY_LIMIT_EXCEEDED", "TOO_MANY_REQUESTS", "HTTP_429"}:
        return True
    return "too many requests" in message or "query limit exceeded" in message


def _extract_result_list(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]

    if isinstance(result, dict):
        for key in ("items", "tasks", "events"):
            nested = result.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


@dataclass
class BitrixProvider:
    base_url: str = ""
    token: str = ""
    webhook_url: str = ""
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    fixture_file: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> "BitrixProvider":
        env_data = _env_dict(env)
        overrides = {str(key): value for key, value in (config or {}).items()}

        base_url = str(
            overrides.get("BITRIX_BASE_URL")
            or overrides.get("bitrixBaseUrl")
            or env_data.get("BITRIX_BASE_URL")
            or ""
        ).strip()
        token = str(
            overrides.get("BITRIX_TOKEN")
            or overrides.get("bitrixToken")
            or env_data.get("BITRIX_TOKEN")
            or ""
        ).strip()
        webhook_url = _normalize_webhook_url(
            overrides.get("BITRIX_WEBHOOK_URL")
            or overrides.get("bitrixWebhookUrl")
            or env_data.get("BITRIX_WEBHOOK_URL")
            or ""
        )
        timeout_sec = int(
            overrides.get("BITRIX_TIMEOUT_SEC")
            or overrides.get("timeoutSec")
            or env_data.get("BITRIX_TIMEOUT_SEC")
            or DEFAULT_TIMEOUT_SEC
        )
        fixture_value = str(
            overrides.get("BITRIX_FIXTURES_FILE")
            or overrides.get("BITRIX_CRM_FIXTURES_FILE")
            or overrides.get("fixtureFile")
            or env_data.get("BITRIX_FIXTURES_FILE")
            or env_data.get("BITRIX_CRM_FIXTURES_FILE")
            or ""
        ).strip()
        fixture_file = Path(fixture_value).expanduser() if fixture_value else None

        return cls(
            base_url=base_url,
            token=token,
            webhook_url=webhook_url,
            timeout_sec=timeout_sec,
            fixture_file=fixture_file,
        )

    def mode(self) -> str:
        if self.fixture_file and self.fixture_file.exists():
            return "fixture"
        if self.webhook_url:
            return "webhook"
        if self.base_url and self.token:
            return "legacy"
        return "not_configured"

    def source(self) -> str:
        if self.mode() == "fixture":
            return "fixture"
        if self.mode() in {"webhook", "legacy"}:
            return "bitrix"
        return "not_configured"

    def is_configured(self) -> bool:
        return self.mode() in {"fixture", "webhook", "legacy"}

    def masked_webhook(self) -> str:
        if self.webhook_url:
            return mask_bitrix_webhook_url(self.webhook_url)
        if self.base_url:
            return mask_bitrix_webhook_url(self.base_url)
        return ""

    def portal_base_url(self) -> str:
        candidate = str(self.webhook_url or self.base_url or "").strip()
        if not candidate:
            return ""

        parsed = urlparse(candidate)
        if not parsed.scheme or not parsed.netloc:
            return ""
        return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")

    def healthcheck(self) -> dict[str, Any]:
        mode = self.mode()
        if mode == "fixture":
            payload = _read_fixture_payload(self.fixture_file)
            return {
                "provider": "bitrix",
                "ok": True,
                "source": "fixture",
                "mode": "fixture",
                "fixture_file": str(self.fixture_file),
                "fixture_keys": sorted(payload.keys()),
            }

        if mode in {"webhook", "legacy"}:
            return {
                "provider": "bitrix",
                "ok": True,
                "source": "bitrix",
                "mode": mode,
                "webhook": self.masked_webhook(),
            }

        return {
            "provider": "bitrix",
            "ok": False,
            "source": "not_configured",
            "mode": "not_configured",
            "error": "BITRIX_WEBHOOK_URL не задан",
        }

    def _fixture_value(self, key: str) -> Any:
        payload = _read_fixture_payload(self.fixture_file)
        return payload.get(key)

    def _build_method_url(self, method: str) -> str:
        if self.mode() == "webhook":
            return f"{self.webhook_url.rstrip('/')}/{method}.json"

        if self.mode() == "legacy":
            query = urlencode({"auth": self.token})
            return f"{self.base_url.rstrip('/')}/rest/{method}.json?{query}"

        raise BitrixAPIError(
            "Bitrix webhook не настроен",
            code="NOT_CONFIGURED",
            category="not_configured",
        )

    def _parse_error_payload(self, raw_body: str, *, http_status: int | None = None) -> BitrixAPIError:
        try:
            payload = json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            payload = {}

        code = str(payload.get("error") or "").strip()
        message = sanitize_bitrix_text(
            payload.get("error_description") or payload.get("error") or "Bitrix request failed",
            webhook_url=self.webhook_url,
        )
        return BitrixAPIError(
            message,
            code=code,
            category=_classify_error_code(code),
            http_status=http_status,
        )

    def _request_payload(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body_pairs = _flatten_params("", dict(params or {}))
        body = urlencode(body_pairs).encode("utf-8")
        request = Request(
            self._build_method_url(method),
            method="POST",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

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
                    last_error = self._parse_error_payload(raw, http_status=int(error.code))
                else:
                    last_error = BitrixAPIError(
                        f"Bitrix HTTP {int(error.code)}",
                        code=f"HTTP_{int(error.code)}",
                        category="error",
                        http_status=int(error.code),
                    )
            except URLError as error:
                reason = sanitize_bitrix_text(str(error.reason or error), webhook_url=self.webhook_url)
                last_error = BitrixAPIError(reason, code="URL_ERROR", category="error")
            except Exception as error:  # noqa: BLE001
                message = sanitize_bitrix_text(str(error), webhook_url=self.webhook_url)
                last_error = BitrixAPIError(message, code="REQUEST_FAILED", category="error")
            else:
                try:
                    payload = json.loads(raw or "{}")
                except json.JSONDecodeError as error:
                    raise BitrixAPIError(
                        f"Bitrix вернул невалидный JSON: {error}",
                        code="INVALID_JSON",
                        category="error",
                    ) from None

                if payload.get("error"):
                    last_error = self._parse_error_payload(raw)
                elif not isinstance(payload, dict):
                    raise BitrixAPIError("Bitrix вернул неожиданный формат ответа", code="INVALID_PAYLOAD")
                else:
                    return payload

            if last_error is None or not _is_rate_limit_error(last_error) or attempt > len(RATE_LIMIT_RETRY_DELAYS_SEC):
                raise last_error or BitrixAPIError("Bitrix request failed", code="REQUEST_FAILED")

        raise last_error or BitrixAPIError("Bitrix request failed", code="REQUEST_FAILED")

    def call_method(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        fixture_key: str | None = None,
        default: Any = None,
    ) -> Any:
        if self.mode() == "fixture":
            key = fixture_key or method.replace(".", "_")
            value = self._fixture_value(key)
            if value is None and default is not None:
                return default
            if value is None:
                raise BitrixAPIError(
                    f"Не найдена fixture для {method}",
                    code="FIXTURE_NOT_FOUND",
                    category="error",
                )
            return value

        payload = self._request_payload(method, params=params)
        if "result" not in payload:
            return default
        return payload.get("result")

    def probe_method(
        self,
        method: str,
        *,
        params: Mapping[str, Any] | None = None,
        fixture_key: str | None = None,
    ) -> dict[str, Any]:
        try:
            result = self.call_method(method, params=params, fixture_key=fixture_key)
        except BitrixAPIError as error:
            payload = error.to_payload()
            payload["method"] = method
            return payload

        sample_list = _extract_result_list(result)
        return {
            "ok": True,
            "status": "ok",
            "method": method,
            "items": len(sample_list),
        }

    def _list(
        self,
        method: str,
        fixture_key: str,
        params: Mapping[str, Any] | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if self.mode() == "fixture":
            raw = self.call_method(method, fixture_key=fixture_key, default=[])
            items = _extract_result_list(raw) if not isinstance(raw, list) else _extract_result_list(raw)
            return items[:limit] if limit else items

        items: list[dict[str, Any]] = []
        start = 0
        request_params = dict(params or {})

        while True:
            payload = self._request_payload(method, {**request_params, "start": start})
            raw_result = payload.get("result")
            chunk = _extract_result_list(raw_result)
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

    def get_profile(self) -> dict[str, Any]:
        result = self.call_method("profile", fixture_key="profile", default={})
        return result if isinstance(result, dict) else {}

    def list_users(
        self,
        *,
        limit: int | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._list("user.get", "users", params=params, limit=limit)

    def list_leads(
        self,
        *,
        limit: int | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._list("crm.lead.list", "leads", params=params, limit=limit)

    def list_deals(
        self,
        *,
        limit: int | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._list("crm.deal.list", "deals", params=params, limit=limit)

    def list_activities(
        self,
        *,
        limit: int | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._list("crm.activity.list", "activities", params=params, limit=limit)

    def list_statuses(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        return self._list("crm.status.list", "statuses", limit=limit)

    def list_companies(
        self,
        *,
        limit: int | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._list("crm.company.list", "companies", params=params, limit=limit)

    def list_contacts(
        self,
        *,
        limit: int | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._list("crm.contact.list", "contacts", params=params, limit=limit)

    def list_departments(self, *, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        return self._list("department.get", "departments", params=params)

    def list_calendar_events(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        owner_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        if owner_id:
            params["ownerId"] = owner_id
            params["type"] = "user"
        return self._list("calendar.event.get", "calendar_events", params=params)

    def list_tasks(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        params = {
            "select": ["ID", "TITLE", "STATUS", "RESPONSIBLE_ID", "DEADLINE"],
            "order": {"ID": "desc"},
        }
        return self._list("tasks.task.list", "tasks", params=params, limit=limit)

    def load_sales_snapshot(self) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "source": self.source(),
                "users": [],
                "leads": [],
                "deals": [],
                "activities": [],
                "statuses": [],
            }

        return {
            "source": self.source(),
            "users": self.list_users(),
            "leads": self.list_leads(),
            "deals": self.list_deals(),
            "activities": self.list_activities(),
            "statuses": self.list_statuses(),
        }


def healthcheck(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    overrides = {str(key): value for key, value in (config or {}).items()}
    provider = BitrixProvider.from_env(config=overrides)
    if provider.is_configured():
        return provider.healthcheck()

    try:
        from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAppAuth

        env_data = _env_dict()
        env_data.update({str(key): str(value) for key, value in overrides.items()})
        app_auth = BitrixAppAuth.from_env(env_data)
        summary = app_auth.summary()
        return {
            "provider": "bitrix",
            "mode": "app_oauth",
            **summary,
        }
    except Exception as error:  # noqa: BLE001
        return {
            "provider": "bitrix",
            "ok": False,
            "status": "error",
            "message": str(error),
            "mode": "app_oauth",
        }
