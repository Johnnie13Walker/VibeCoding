from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
SYNC_SCRIPT = Path("/opt/openclaw/repos/vibecoding/shared/scripts/bitrix-sync-state.sh")
OWNER_TYPE_COMPANY = "4"


class BitrixError(RuntimeError):
    """Базовая ошибка Bitrix REST."""


class BitrixNotFound(BitrixError):
    """Сущность не найдена."""


class BitrixTokenExpired(BitrixError):
    """OAuth state не удалось обновить."""


class BitrixRateLimited(BitrixError):
    """Bitrix не ответил после retry на rate limit или 5xx."""


class BitrixClient:
    def __init__(self, state_path: Path, log_path: Path | None = None):
        self.state_path = state_path
        self.log_path = log_path
        self._state = self._read_state()

    def call(self, method: str, params: dict | None = None) -> dict:
        self._ensure_fresh_state()
        normalized_params = params or {}
        started = time.monotonic()
        body: dict[str, Any] = {}
        ok = False

        try:
            body = self._call_with_retries(method, normalized_params)
            ok = "error" not in body or body.get("error") in (None, "")
            if body.get("error") and not _is_not_found_body(body):
                raise BitrixError(
                    f"Bitrix method {method} failed: {body.get('error')} "
                    f"{body.get('error_description', '')}".strip()
                )
            return body
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            self._log_call(method, normalized_params, body, ok, duration_ms)

    def batch(self, commands: dict[str, tuple[str, dict]]) -> dict:
        merged: dict[str, Any] = {}
        items = list(commands.items())
        for offset in range(0, len(items), 50):
            chunk = dict(items[offset : offset + 50])
            cmd = {
                name: self._build_batch_command(method, params)
                for name, (method, params) in chunk.items()
            }
            body = self.call("batch", {"cmd": cmd})
            result = body.get("result", {})
            if isinstance(result, dict):
                result_result = result.get("result")
                if isinstance(result_result, dict):
                    merged.update(result_result)
                else:
                    merged.update(result)
        return merged

    def paginate(self, method: str, params: dict, id_field: str = "ID") -> Iterator[dict]:
        last_id = 0
        while True:
            page_params = _deepcopy_jsonable(params)
            filters = _extract_filter(page_params)
            filters[f">{id_field}"] = last_id
            page_params["filter"] = filters
            page_params["order"] = {id_field: "ASC"}
            page_params["start"] = -1

            body = self.call(method, page_params)
            records = _result_records(body.get("result"))
            if not records:
                break

            for record in records:
                yield record
            next_last_id = max(_int_id(record.get(id_field)) for record in records)
            if next_last_id <= last_id:
                raise BitrixError(
                    f"Bitrix pagination did not advance for {method} by {id_field}; "
                    "method may not support filter[>ID]"
                )
            last_id = next_last_id

            if len(records) < 50:
                break

    def find_companies_by_inn(self, inn: str) -> list[str]:
        rows = self.paginate(
            "crm.requisite.list",
            {"filter": {"RQ_INN": inn, "ENTITY_TYPE_ID": OWNER_TYPE_COMPANY}},
        )
        return sorted({str(row["ENTITY_ID"]) for row in rows if row.get("ENTITY_ID")}, key=int)

    def list_deals(self, company_id: str, closed: bool | None = None) -> list[dict]:
        filter_: dict[str, Any] = {"COMPANY_ID": company_id}
        if closed is not None:
            filter_["CLOSED"] = "Y" if closed else "N"
        return list(self.paginate("crm.deal.list", {"filter": filter_}))

    def list_contacts(self, company_id: str) -> list[dict]:
        return list(self.paginate("crm.contact.list", {"filter": {"COMPANY_ID": company_id}}))

    def list_activities(self, company_id: str) -> list[dict]:
        return list(
            self.paginate(
                "crm.activity.list",
                {
                    "filter": {"OWNER_TYPE_ID": OWNER_TYPE_COMPANY, "OWNER_ID": company_id},
                    "select": [
                        "ID",
                        "PROVIDER_ID",
                        "TYPE_ID",
                        "SUBJECT",
                        "COMPLETED",
                        "OWNER_TYPE_ID",
                        "OWNER_ID",
                    ],
                },
            )
        )

    def list_leads(self, company_id: str) -> list[dict]:
        return list(self.paginate("crm.lead.list", {"filter": {"COMPANY_ID": company_id}}))

    def list_smart_items_for_company(self, company_id: str) -> list[tuple[int, list[dict]]]:
        types_body = self.call("crm.type.list")
        types = types_body.get("result", {}).get("types", [])
        found: list[tuple[int, list[dict]]] = []
        for item_type in types:
            entity_type_id = item_type.get("entityTypeId")
            if entity_type_id is None:
                continue
            items = list(
                self.paginate(
                    "crm.item.list",
                    {"entityTypeId": int(entity_type_id), "filter": {"companyId": company_id}},
                    id_field="id",
                )
            )
            if items:
                found.append((int(entity_type_id), items))
        return found

    def list_requisites(self, company_id: str) -> list[dict]:
        return list(
            self.paginate(
                "crm.requisite.list",
                {"filter": {"ENTITY_TYPE_ID": OWNER_TYPE_COMPANY, "ENTITY_ID": company_id}},
            )
        )

    def list_bank_details(self, requisite_id: str) -> list[dict]:
        return list(
            self.paginate("crm.requisite.bankdetail.list", {"filter": {"ENTITY_ID": requisite_id}})
        )

    def list_timeline_comments(self, entity_type: str, entity_id: str) -> list[dict]:
        comments: list[dict] = []
        start: int | None = 0
        seen_starts: set[int] = set()
        while start is not None:
            if start in seen_starts:
                raise BitrixError("Bitrix timeline comment pagination repeated start value")
            seen_starts.add(start)
            body = self.call(
                "crm.timeline.comment.list",
                {
                    "filter": {"ENTITY_TYPE": entity_type, "ENTITY_ID": entity_id},
                    "order": {"ID": "ASC"},
                    "start": start,
                },
            )
            comments.extend(_result_records(body.get("result")))
            raw_next = body.get("next")
            start = int(raw_next) if raw_next is not None else None
        return comments

    def get_company(self, company_id: str) -> dict | None:
        return self._get_or_none("crm.company.get", {"id": company_id})

    def get_deal(self, deal_id: str) -> dict | None:
        return self._get_or_none("crm.deal.get", {"id": deal_id})

    def get_contact(self, contact_id: str) -> dict | None:
        return self._get_or_none("crm.contact.get", {"id": contact_id})

    def get_lead(self, lead_id: str) -> dict | None:
        return self._get_or_none("crm.lead.get", {"id": lead_id})

    def get_smart_item(self, entity_type_id: int, item_id: str) -> dict | None:
        return self._get_or_none(
            "crm.item.get", {"entityTypeId": entity_type_id, "id": item_id}
        )

    def get_requisite(self, requisite_id: str) -> dict | None:
        return self._get_or_none("crm.requisite.get", {"id": requisite_id})

    def update_company(self, company_id: str, fields: dict) -> bool:
        return self._bool_result("crm.company.update", {"id": company_id, "fields": fields})

    def update_deal(self, deal_id: str, fields: dict) -> bool:
        return self._bool_result("crm.deal.update", {"id": deal_id, "fields": fields})

    def update_contact(self, contact_id: str, fields: dict) -> bool:
        return self._bool_result("crm.contact.update", {"id": contact_id, "fields": fields})

    def update_activity(self, activity_id: str, fields: dict) -> bool:
        return self._bool_result("crm.activity.update", {"id": activity_id, "fields": fields})

    def update_lead(self, lead_id: str, fields: dict) -> bool:
        return self._bool_result("crm.lead.update", {"id": lead_id, "fields": fields})

    def update_smart_item(self, entity_type_id: int, item_id: str, fields: dict) -> bool:
        return self._bool_result(
            "crm.item.update",
            {"entityTypeId": entity_type_id, "id": item_id, "fields": fields},
        )

    def add_timeline_comment(self, entity_type: str, entity_id: str, text: str) -> str:
        body = self.call(
            "crm.timeline.comment.add",
            {"fields": {"ENTITY_TYPE": entity_type, "ENTITY_ID": entity_id, "COMMENT": text}},
        )
        return str(body.get("result", ""))

    def delete_company(self, company_id: str) -> bool:
        return self._bool_result("crm.company.delete", {"id": company_id})

    def delete_requisite(self, requisite_id: str) -> bool:
        return self._bool_result("crm.requisite.delete", {"id": requisite_id})

    def delete_bank_detail(self, bank_detail_id: str) -> bool:
        return self._bool_result("crm.requisite.bankdetail.delete", {"id": bank_detail_id})

    def _get_or_none(self, method: str, params: dict) -> dict | None:
        body = self.call(method, params)
        if _is_not_found_body(body):
            return None
        result = body.get("result")
        return result if isinstance(result, dict) else None

    def _bool_result(self, method: str, params: dict) -> bool:
        body = self.call(method, params)
        return bool(body.get("result"))

    def _call_with_retries(self, method: str, params: dict) -> dict:
        delays = (1, 2, 4)
        attempts = len(delays) + 1
        last_body: dict[str, Any] | None = None
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                body = self._post(method, params)
            except HTTPError as exc:
                last_error = exc
                error_body = _http_error_body(exc)
                if error_body is not None and _is_not_found_body(error_body):
                    return error_body
                if exc.code < 500 or attempt == attempts - 1:
                    if exc.code >= 500:
                        raise BitrixRateLimited(
                            f"Bitrix HTTP {exc.code} after {attempt + 1} attempts on {method}"
                        ) from exc
                    raise BitrixError(f"HTTP {exc.code} on Bitrix method {method}") from exc
                time.sleep(delays[attempt])
                continue
            except URLError as exc:
                last_error = exc
                if attempt == attempts - 1:
                    raise BitrixError(f"Network error on Bitrix method {method}: {exc}") from exc
                time.sleep(delays[attempt])
                continue

            last_body = body
            if body.get("error") == "QUERY_LIMIT_EXCEEDED":
                if attempt == attempts - 1:
                    raise BitrixRateLimited(
                        f"Bitrix rate limit after {attempts} attempts on {method}"
                    )
                time.sleep(delays[attempt])
                continue
            return body

        if last_body and last_body.get("error") == "QUERY_LIMIT_EXCEEDED":
            raise BitrixRateLimited(f"Bitrix rate limit after {attempts} attempts on {method}")
        if last_error:
            raise BitrixRateLimited(f"Bitrix retry exhausted on {method}") from last_error
        raise BitrixError(f"Bitrix method {method} failed without response")

    def _post(self, method: str, params: dict) -> dict:
        payload = {"auth": self._access_token()}
        payload.update(params)
        data = urllib.parse.urlencode(_flatten_params(payload), doseq=True).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint() + f"/{method}.json",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def _ensure_fresh_state(self) -> None:
        expires = self._expires()
        if expires >= int(time.time()) + 300:
            return
        if not SYNC_SCRIPT.exists():
            raise BitrixTokenExpired(
                "Bitrix OAuth state истёк, а sync-скрипт не найден. "
                f"Положите скрипт в {SYNC_SCRIPT}"
            )
        subprocess.run([str(SYNC_SCRIPT)], check=True)
        self._state = self._read_state()
        if self._expires() < int(time.time()) + 300:
            raise BitrixTokenExpired("Bitrix OAuth state остался протухшим после sync")

    def _read_state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise BitrixTokenExpired(f"Bitrix state-файл не найден: {self.state_path}") from exc

    def _payload(self) -> dict[str, Any]:
        payload = self._state.get("payload", {})
        if not isinstance(payload, dict):
            raise BitrixTokenExpired("Bitrix state не содержит payload")
        return payload

    def _access_token(self) -> str:
        payload = self._payload()
        token = payload.get("auth[access_token]") or payload.get("AUTH_ID")
        if not token:
            raise BitrixTokenExpired("Bitrix state не содержит access_token")
        return str(token)

    def _endpoint(self) -> str:
        payload = self._payload()
        endpoint = payload.get("auth[client_endpoint]") or payload.get("client_endpoint")
        if not endpoint:
            raise BitrixTokenExpired("Bitrix state не содержит client_endpoint")
        return str(endpoint).rstrip("/")

    def _expires(self) -> int:
        raw = self._payload().get("auth[expires]") or 0
        try:
            return int(float(str(raw)))
        except ValueError:
            return 0

    def _build_batch_command(self, method: str, params: dict) -> str:
        query = urllib.parse.urlencode(_flatten_params(params), doseq=True)
        return f"{method}?{query}" if query else method

    def _log_call(
        self,
        method: str,
        params: dict,
        response: dict,
        ok: bool,
        duration_ms: int,
    ) -> None:
        row = [
            datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
            method,
            _params_hash(params),
            _response_summary(response),
            "1" if ok else "0",
            str(duration_ms),
        ]
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8", newline="") as handle:
                csv.writer(handle).writerow(row)
        else:
            print(" ".join(row), file=sys.stderr)


def _is_not_found_body(body: dict[str, Any]) -> bool:
    return body.get("error_description") == "Not found"


def _http_error_body(exc: HTTPError) -> dict[str, Any] | None:
    try:
        raw = exc.read()
    except Exception:
        return None
    if not raw:
        return None
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return body if isinstance(body, dict) else None


def _params_hash(params: dict) -> str:
    encoded = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _response_summary(response: dict) -> str:
    if not response:
        return "empty"
    if "error" in response and response.get("error"):
        return f"error:{response.get('error')}"
    if _is_not_found_body(response):
        return "not_found"
    result = response.get("result")
    if isinstance(result, list):
        return f"result:list:{len(result)}"
    if isinstance(result, dict):
        return f"result:dict:{len(result)}"
    return f"result:{type(result).__name__}"


def _extract_filter(params: dict) -> dict:
    raw_filter = params.pop("filter", {})
    if isinstance(raw_filter, dict):
        return dict(raw_filter)
    return {}


def _deepcopy_jsonable(value: dict) -> dict:
    return json.loads(json.dumps(value))


def _int_id(value: Any) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _result_records(result: Any) -> list[dict]:
    if isinstance(result, list):
        return [record for record in result if isinstance(record, dict)]
    if isinstance(result, dict) and isinstance(result.get("items"), list):
        return [record for record in result["items"] if isinstance(record, dict)]
    return []


def _flatten_params(params: dict[str, Any], prefix: str | None = None) -> list[tuple[str, Any]]:
    pairs: list[tuple[str, Any]] = []
    for key, value in params.items():
        full_key = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            pairs.extend(_flatten_params(value, full_key))
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, dict):
                    pairs.extend(_flatten_params(item, f"{full_key}[]"))
                else:
                    pairs.append((f"{full_key}[]", item))
        else:
            pairs.append((full_key, value))
    return pairs
