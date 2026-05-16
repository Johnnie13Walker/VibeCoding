"""Bitrix REST client для crm_company_enrich.

Форк из crm_deal_merge.bitrix_client. Низкоуровневые retries/paginate/batch
оставлены как-есть; deal-merge-специфичные методы (smart-process relink,
deal activities/timeline reassign) удалены — здесь они не нужны.

Добавлены company/requisite-обёртки:
- list_companies         — пагинация crm.company.list
- list_requisites        — crm.requisite.list
- get_company            — crm.company.get
- list_company_requisites
- search_requisite_by_inn — поиск дубликатов по ИНН
- get_company_deals_count
- get_company_contacts
"""
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

from .config import ENTITY_TYPE_COMPANY, SYNC_SCRIPT

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


class BitrixError(RuntimeError):
    pass


class BitrixNotFound(BitrixError):
    pass


class BitrixTokenExpired(BitrixError):
    pass


class BitrixRateLimited(BitrixError):
    pass


class BitrixClient:
    def __init__(self, state_path: Path, log_path: Path | None = None):
        self.state_path = state_path
        self.log_path = log_path
        self._state = self._read_state()
        self._last_sync_at_monotonic = 0.0

    # ------------------------------ low-level ------------------------------

    def call(self, method: str, params: dict | None = None) -> dict:
        self._ensure_fresh_state()
        normalized = params or {}
        started = time.monotonic()
        body: dict[str, Any] = {}
        ok = False
        try:
            body = self._call_with_retries(method, normalized)
            ok = "error" not in body or body.get("error") in (None, "")
            if body.get("error") and not _is_not_found(body):
                raise BitrixError(
                    f"Bitrix method {method} failed: {body.get('error')} "
                    f"{body.get('error_description','')}".strip()
                )
            return body
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            self._log_call(method, normalized, body, ok, duration_ms)

    def paginate(self, method: str, params: dict, id_field: str = "ID") -> Iterator[dict]:
        last = 0
        while True:
            p = _deep(params)
            f = _extract_filter(p)
            f[f">{id_field}"] = last
            p["filter"] = f
            p["order"] = {id_field: "ASC"}
            p["start"] = -1
            body = self.call(method, p)
            records = _records(body.get("result"))
            if not records:
                break
            for r in records:
                yield r
            nxt = max(_int_id(r.get(id_field)) for r in records)
            if nxt <= last:
                raise BitrixError(
                    f"Bitrix pagination did not advance for {method} by {id_field}"
                )
            last = nxt
            if len(records) < 50:
                break

    def batch(self, commands: dict[str, tuple[str, dict]]) -> dict:
        merged: dict[str, Any] = {}
        items = list(commands.items())
        for off in range(0, len(items), 50):
            chunk = dict(items[off : off + 50])
            cmd = {name: self._build_batch_command(m, p) for name, (m, p) in chunk.items()}
            body = self.call("batch", {"cmd": cmd})
            result = body.get("result", {})
            if isinstance(result, dict):
                inner = result.get("result")
                if isinstance(inner, dict):
                    merged.update(inner)
                else:
                    merged.update(result)
        return merged

    # ------------------------------ companies ------------------------------

    DEFAULT_COMPANY_SELECT = [
        "ID", "TITLE", "DATE_CREATE", "DATE_MODIFY",
        "ASSIGNED_BY_ID", "COMPANY_TYPE", "INDUSTRY",
        "WEB", "PHONE", "EMAIL", "COMMENTS",
        # UF_* поля приходят автоматически если запросить "UF_*" в select.
        # Bitrix select не поддерживает wildcards — каждый портал имеет свой
        # список UF; здесь оставляем базовые системные поля, а UF_* discover
        # вытащит отдельно через crm.company.fields().
    ]

    def list_companies(
        self,
        select: list[str] | None = None,
        filter_: dict | None = None,
    ) -> list[dict]:
        """Все компании портала постранично через filter[>ID]."""
        return list(
            self.paginate(
                "crm.company.list",
                {
                    "filter": dict(filter_ or {}),
                    "select": select or self.DEFAULT_COMPANY_SELECT,
                },
            )
        )

    def get_company(self, company_id: str) -> dict | None:
        return self._get_or_none("crm.company.get", {"id": company_id})

    def get_company_user_fields(self) -> list[dict]:
        """Список UF_* полей компании (для discover — какие UF могут содержать ИНН)."""
        body = self.call("crm.company.userfield.list", {"order": {"ID": "ASC"}})
        result = body.get("result")
        return result if isinstance(result, list) else []

    def get_company_deals_count(self, company_id: str) -> int:
        """Количество сделок у компании. Минимальный select для скорости."""
        body = self.call(
            "crm.deal.list",
            {
                "filter": {"COMPANY_ID": company_id},
                "select": ["ID"],
                "start": -1,
            },
        )
        result = body.get("result")
        if isinstance(result, list):
            return len(result)
        return 0

    def get_company_contacts(self, company_id: str) -> list[str]:
        """Список contact_id, привязанных к компании."""
        body = self.call("crm.company.contact.items.get", {"id": company_id})
        result = body.get("result")
        if not isinstance(result, list):
            return []
        return [str(item.get("CONTACT_ID")) for item in result if isinstance(item, dict)]

    # ------------------------------ requisites ------------------------------

    def list_requisites(
        self,
        entity_type_id: int = ENTITY_TYPE_COMPANY,
        filter_: dict | None = None,
        select: list[str] | None = None,
    ) -> list[dict]:
        """Все реквизиты данного entity_type. Пагинация через filter[>ID]."""
        merged_filter = {"ENTITY_TYPE_ID": entity_type_id}
        if filter_:
            merged_filter.update(filter_)
        return list(
            self.paginate(
                "crm.requisite.list",
                {
                    "filter": merged_filter,
                    "select": select or [
                        "ID",
                        "ENTITY_ID",
                        "RQ_INN",
                        "RQ_KPP",
                        "RQ_OGRN",
                        "RQ_OGRNIP",
                        "NAME",
                        "RQ_COMPANY_NAME",
                        "RQ_COMPANY_FULL_NAME",
                    ],
                },
            )
        )

    def list_company_requisites(self, company_id: str) -> list[dict]:
        return self.list_requisites(filter_={"ENTITY_ID": company_id})

    def search_requisite_by_inn(self, inn: str) -> list[dict]:
        """Найти все реквизиты компаний с данным RQ_INN.

        Возвращает [] если ничего не найдено. Используется в classify-стадии
        для определения target_action (CREATE_REQ / MERGE_INTO / SKIP_ALREADY).
        """
        if not inn:
            return []
        body = self.call(
            "crm.requisite.list",
            {
                "filter": {"ENTITY_TYPE_ID": ENTITY_TYPE_COMPANY, "RQ_INN": inn},
                "select": ["ID", "ENTITY_ID", "RQ_INN", "RQ_KPP"],
                "start": -1,
            },
        )
        result = body.get("result")
        return result if isinstance(result, list) else []

    # ------------------------------ write methods (apply) ------------------------------

    def add_requisite(self, fields: dict) -> str:
        """crm.requisite.add — создать новый реквизит. Возвращает строковый ID.

        Минимальный набор fields: ENTITY_TYPE_ID, ENTITY_ID, PRESET_ID, NAME,
        RQ_INN, опционально RQ_COMPANY_NAME_FULL. Низкоуровневые retries
        полностью наследуются от self.call (которая дёргает _call_with_retries).

        Bitrix REST возвращает result либо int (id), либо dict {"ID": "...", ...}.
        Нормализуем к str.
        """
        body = self.call("crm.requisite.add", {"fields": fields})
        result = body.get("result")
        if isinstance(result, dict):
            rid = result.get("ID") or result.get("id")
        else:
            rid = result
        if rid in (None, "", 0, "0"):
            raise BitrixError(
                f"crm.requisite.add returned empty id: {body!r}"
            )
        return str(rid)

    def update_company(self, company_id: str, fields: dict) -> bool:
        """crm.company.update — обновить произвольные поля компании.

        Используется apply-стадией в гибридном режиме для «touch»: трогаем
        COMMENTS (добавляем trailing space) чтобы обновить DATE_MODIFY и
        триггернуть AUTO_EXECUTE=2 bizproc'ы (в том числе обогащение по ИНН).
        """
        body = self.call(
            "crm.company.update",
            {"id": company_id, "fields": fields},
        )
        return bool(body.get("result"))

    def start_workflow(self, template_id: int, document_type: list) -> dict:
        """bizproc.workflow.start — best-effort, не подавляем сетевые retries,
        но 4xx-ошибки (403/400) пробрасываем как BitrixError для caller-side handle.

        Возвращает {"workflow_id": "..."} при успехе.
        """
        body = self.call(
            "bizproc.workflow.start",
            {
                "TEMPLATE_ID": template_id,
                "DOCUMENT_ID": document_type,
            },
        )
        result = body.get("result")
        if isinstance(result, dict):
            wf_id = result.get("ID") or result.get("WORKFLOW_ID") or result.get("id")
        else:
            wf_id = result
        if wf_id in (None, "", 0, "0"):
            raise BitrixError(
                f"bizproc.workflow.start returned empty workflow id: {body!r}"
            )
        return {"workflow_id": str(wf_id)}

    def delete_requisite(self, requisite_id: str) -> bool:
        """crm.requisite.delete — для rollback-стадии. Возвращает True/False."""
        body = self.call("crm.requisite.delete", {"id": requisite_id})
        return bool(body.get("result"))

    # ------------------------------ helpers ------------------------------

    def _get_or_none(self, method: str, params: dict) -> dict | None:
        body = self.call(method, params)
        if _is_not_found(body):
            return None
        r = body.get("result")
        return r if isinstance(r, dict) else None

    def _bool_result(self, method: str, params: dict) -> bool:
        body = self.call(method, params)
        return bool(body.get("result"))

    def _call_with_retries(self, method: str, params: dict) -> dict:
        delays = (1, 2, 4, 8, 16)
        attempts = len(delays) + 1
        last_body: dict | None = None
        last_err: Exception | None = None

        for attempt in range(attempts):
            try:
                body = self._post(method, params)
            except HTTPError as exc:
                last_err = exc
                eb = _http_err_body(exc)
                if eb is not None and _is_not_found(eb):
                    return eb
                if exc.code == 401:
                    self._refresh_state()
                    if attempt == attempts - 1:
                        raise BitrixError(f"HTTP {exc.code} on {method}") from exc
                    time.sleep(delays[attempt])
                    continue
                if exc.code < 500 and exc.code != 429:
                    if attempt == attempts - 1:
                        raise BitrixError(f"HTTP {exc.code} on {method}") from exc
                if attempt == attempts - 1:
                    raise BitrixRateLimited(
                        f"Bitrix HTTP {exc.code} after {attempt+1} attempts on {method}"
                    ) from exc
                time.sleep(delays[attempt])
                continue
            except URLError as exc:
                last_err = exc
                if attempt == attempts - 1:
                    raise BitrixError(f"Network error on {method}: {exc}") from exc
                time.sleep(delays[attempt])
                continue

            last_body = body
            if body.get("error") == "QUERY_LIMIT_EXCEEDED":
                if attempt == attempts - 1:
                    raise BitrixRateLimited(f"Rate limit after {attempts} on {method}")
                time.sleep(delays[attempt])
                continue
            return body

        if last_body and last_body.get("error") == "QUERY_LIMIT_EXCEEDED":
            raise BitrixRateLimited(f"Rate limit after {attempts} on {method}")
        if last_err:
            raise BitrixRateLimited(f"Retry exhausted on {method}") from last_err
        raise BitrixError(f"{method} failed without response")

    def _post(self, method: str, params: dict) -> dict:
        payload = {"auth": self._access_token()}
        payload.update(params)
        data = urllib.parse.urlencode(_flatten(payload), doseq=True).encode("utf-8")
        req = urllib.request.Request(
            self._endpoint() + f"/{method}.json",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))

    def _ensure_fresh_state(self) -> None:
        if self._expires() >= int(time.time()) + 300:
            return
        if self._last_sync_at_monotonic and time.monotonic() - self._last_sync_at_monotonic < 3600:
            return
        self._refresh_state()
        return

    def _refresh_state(self) -> None:
        if not SYNC_SCRIPT.exists():
            raise BitrixTokenExpired(f"Sync-скрипт не найден: {SYNC_SCRIPT}")
        subprocess.run([str(SYNC_SCRIPT)], check=True)
        self._state = self._read_state()
        self._last_sync_at_monotonic = time.monotonic()

    def _read_state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise BitrixTokenExpired(f"State-файл не найден: {self.state_path}") from exc

    def _payload(self) -> dict[str, Any]:
        p = self._state.get("payload", {})
        if not isinstance(p, dict):
            raise BitrixTokenExpired("state не содержит payload")
        return p

    def _access_token(self) -> str:
        p = self._payload()
        t = p.get("auth[access_token]") or p.get("AUTH_ID")
        if not t:
            raise BitrixTokenExpired("Нет access_token")
        return str(t)

    def _endpoint(self) -> str:
        p = self._payload()
        e = p.get("auth[client_endpoint]") or p.get("client_endpoint")
        if not e:
            raise BitrixTokenExpired("Нет client_endpoint")
        return str(e).rstrip("/")

    def _expires(self) -> int:
        raw = self._payload().get("auth[expires]") or 0
        try:
            return int(float(str(raw)))
        except ValueError:
            return 0

    def _build_batch_command(self, method: str, params: dict) -> str:
        q = urllib.parse.urlencode(_flatten(params), doseq=True)
        return f"{method}?{q}" if q else method

    def _log_call(self, method, params, response, ok, duration_ms):
        row = [
            datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
            method,
            _params_hash(params),
            _resp_summary(response),
            "1" if ok else "0",
            str(duration_ms),
        ]
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8", newline="") as h:
                csv.writer(h).writerow(row)
        else:
            print(" ".join(row), file=sys.stderr)


# ---- module helpers ----

def _is_not_found(body: dict) -> bool:
    return body.get("error_description") == "Not found"


def _http_err_body(exc: HTTPError) -> dict | None:
    try:
        raw = exc.read()
    except Exception:
        return None
    if not raw:
        return None
    try:
        b = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return b if isinstance(b, dict) else None


def _params_hash(params: dict) -> str:
    return hashlib.sha256(
        json.dumps(params, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


def _resp_summary(r: dict) -> str:
    if not r:
        return "empty"
    if r.get("error"):
        return f"error:{r.get('error')}"
    if _is_not_found(r):
        return "not_found"
    result = r.get("result")
    if isinstance(result, list):
        return f"list:{len(result)}"
    if isinstance(result, dict):
        return f"dict:{len(result)}"
    return f"{type(result).__name__}"


def _extract_filter(params: dict) -> dict:
    f = params.pop("filter", {})
    return dict(f) if isinstance(f, dict) else {}


def _deep(v: dict) -> dict:
    return json.loads(json.dumps(v))


def _int_id(v: Any) -> int:
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return 0


def _records(result: Any) -> list[dict]:
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict) and isinstance(result.get("items"), list):
        return [r for r in result["items"] if isinstance(r, dict)]
    return []


def _flatten(params: dict, prefix: str | None = None) -> list[tuple[str, Any]]:
    pairs: list[tuple[str, Any]] = []
    for k, v in params.items():
        fk = f"{prefix}[{k}]" if prefix else str(k)
        if isinstance(v, dict):
            pairs.extend(_flatten(v, fk))
        elif isinstance(v, (list, tuple)):
            for item in v:
                if isinstance(item, dict):
                    pairs.extend(_flatten(item, f"{fk}[]"))
                else:
                    pairs.append((f"{fk}[]", item))
        else:
            pairs.append((fk, v))
    return pairs
