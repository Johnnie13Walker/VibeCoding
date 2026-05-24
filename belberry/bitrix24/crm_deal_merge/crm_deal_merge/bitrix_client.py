"""Bitrix REST client для crm_deal_merge.

Форкнут из crm_company_merge с убранными requisite/bank/lead методами
и добавленными deal-merge-specific (cross-funnel, smart-process relink).
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

from .config import OWNER_TYPE_DEAL, RATE_LIMIT_SLEEP_S, SP_PARENT_FIELD, SYNC_SCRIPT

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
        self._sp_types_cache: list[dict] | None = None
        self._last_sync_at_monotonic = 0.0
        self._last_call_at_monotonic = 0.0
        self._slow_empty_sp_type_ids: set[int] = set()

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

    # ------------------------------ deals: list/get/update ------------------------------

    def list_deals_in_funnel(
        self,
        category_id: str,
        select: list[str] | None = None,
    ) -> list[dict]:
        select = select or ["ID", "COMPANY_ID", "TITLE", "STAGE_ID", "DATE_MODIFY",
                            "DATE_CREATE", "CLOSED", "ASSIGNED_BY_ID"]
        return list(
            self.paginate(
                "crm.deal.list",
                {"filter": {"CATEGORY_ID": category_id}, "select": select},
            )
        )

    def get_deal(self, deal_id: str) -> dict | None:
        return self._get_or_none("crm.deal.get", {"id": deal_id})

    def get_company(self, company_id: str) -> dict | None:
        return self._get_or_none("crm.company.get", {"id": company_id})

    def list_company_requisites(self, company_id: str) -> list[dict]:
        return list(
            self.paginate(
                "crm.requisite.list",
                {"filter": {"ENTITY_TYPE_ID": 4, "ENTITY_ID": company_id}},
            )
        )

    def update_deal(self, deal_id: str, fields: dict) -> bool:
        return self._bool_result("crm.deal.update", {"id": deal_id, "fields": fields})

    def close_deal_as_lose(self, deal_id: str, lose_stage: str, comment_to_append: str) -> bool:
        """Закрыть LOSER: переставить STAGE_ID и дополнить COMMENTS."""
        cur = self.get_deal(deal_id) or {}
        existing = cur.get("COMMENTS") or ""
        new_comments = (existing + "\n" + comment_to_append).strip()
        return self.update_deal(deal_id, {
            "STAGE_ID": lose_stage,
            "COMMENTS": new_comments,
        })

    # ------------------------------ activities ------------------------------

    def list_deal_activities(self, deal_id: str) -> list[dict]:
        return list(
            self.paginate(
                "crm.activity.list",
                {
                    "filter": {"OWNER_TYPE_ID": OWNER_TYPE_DEAL, "OWNER_ID": deal_id},
                    "select": ["ID", "TYPE_ID", "PROVIDER_ID", "SUBJECT", "COMPLETED",
                               "OWNER_TYPE_ID", "OWNER_ID"],
                },
            )
        )

    def reassign_activity(self, activity_id: str, new_owner_deal_id: str) -> bool:
        """Перенос активности на новую сделку. False для VOXIMPLANT_CALL (некритично)."""
        return self._bool_result("crm.activity.update", {
            "id": activity_id,
            "fields": {"OWNER_TYPE_ID": OWNER_TYPE_DEAL, "OWNER_ID": new_owner_deal_id},
        })

    def get_activity(self, activity_id: str) -> dict | None:
        return self._get_or_none("crm.activity.get", {"id": activity_id})

    def reassign_task_activity(
        self,
        activity_id: str,
        old_owner_deal_id: str,
        new_owner_deal_id: str,
    ) -> bool:
        activity = self.get_activity(activity_id) or {}
        task_id = activity.get("ASSOCIATED_ENTITY_ID")
        if not task_id or str(task_id) == "0":
            return False
        task_body = self.call("tasks.task.get", {"taskId": task_id, "select": ["UF_CRM_TASK"]})
        task = task_body.get("result", {}).get("task", {})
        crm_links = task.get("ufCrmTask") or []
        old_link = f"D_{old_owner_deal_id}"
        new_link = f"D_{new_owner_deal_id}"
        updated_links = [new_link if link == old_link else link for link in crm_links]
        if new_link not in updated_links:
            updated_links.append(new_link)
        body = self.call("tasks.task.update", {
            "taskId": task_id,
            "fields": {"UF_CRM_TASK": updated_links},
        })
        return bool(body.get("result"))

    # ------------------------------ timeline ------------------------------

    def list_deal_timeline_comments(self, deal_id: str) -> list[dict]:
        """timeline.comment.list НЕ поддерживает filter[>ID] — пагинация через start."""
        out: list[dict] = []
        start: int | None = 0
        seen: set[int] = set()
        while start is not None:
            if start in seen:
                raise BitrixError("Bitrix timeline pagination repeated start")
            seen.add(start)
            body = self.call("crm.timeline.comment.list", {
                "filter": {"ENTITY_TYPE": "deal", "ENTITY_ID": deal_id},
                "order": {"ID": "ASC"},
                "start": start,
            })
            out.extend(_records(body.get("result")))
            raw_next = body.get("next")
            start = int(raw_next) if raw_next is not None else None
        return out

    def add_deal_timeline_comment(self, deal_id: str, text: str) -> str:
        body = self.call("crm.timeline.comment.add", {
            "fields": {"ENTITY_TYPE": "deal", "ENTITY_ID": deal_id, "COMMENT": text},
        })
        return str(body.get("result", ""))

    def delete_timeline_comment(self, comment_id: str) -> bool:
        return self._bool_result("crm.timeline.comment.delete", {"id": comment_id})

    # ------------------------------ contacts ------------------------------

    def list_deal_contacts(self, deal_id: str) -> list[dict]:
        body = self.call("crm.deal.contact.items.get", {"id": deal_id})
        result = body.get("result")
        return result if isinstance(result, list) else []

    def add_deal_contact(self, deal_id: str, contact_id: str) -> bool:
        return self._bool_result("crm.deal.contact.add", {
            "id": deal_id,
            "fields": {"CONTACT_ID": contact_id},
        })

    # ------------------------------ smart processes ------------------------------

    def smart_process_types(self) -> list[dict]:
        if self._sp_types_cache is None:
            body = self.call("crm.type.list")
            types = body.get("result", {})
            if isinstance(types, dict):
                self._sp_types_cache = types.get("types", []) or []
            else:
                self._sp_types_cache = []
        return self._sp_types_cache

    def list_smart_items_for_deal(self, deal_id: str) -> list[tuple[int, list[dict]]]:
        """Возвращает [(entityTypeId, items_list)] — только SP-типы с непустыми элементами."""
        found: list[tuple[int, list[dict]]] = []
        for t in self.smart_process_types():
            etid = t.get("entityTypeId")
            if etid is None:
                continue
            entity_type_id = int(etid)
            if entity_type_id in self._slow_empty_sp_type_ids:
                continue
            started = time.monotonic()
            try:
                items = list(
                    self.paginate(
                        "crm.item.list",
                        {"entityTypeId": entity_type_id, "filter": {SP_PARENT_FIELD: deal_id}},
                        id_field="id",
                    )
                )
            except BitrixError:
                # некоторые SP не поддерживают parentId2 → игнорируем
                self._slow_empty_sp_type_ids.add(entity_type_id)
                continue
            duration_s = time.monotonic() - started
            if not items and duration_s > 10:
                # В Bitrix некоторые SP-типы с parentId2 отвечают пусто только после
                # сетевого timeout. Не повторяем такой дорогой пустой probe для
                # каждого LOSER в текущем процессе inventory.
                self._slow_empty_sp_type_ids.add(entity_type_id)
                continue
            if items:
                found.append((entity_type_id, items))
        return found

    def relink_smart_item(self, entity_type_id: int, item_id: str, new_parent_deal_id: str) -> bool:
        return self._bool_result("crm.item.update", {
            "entityTypeId": entity_type_id,
            "id": item_id,
            "fields": {SP_PARENT_FIELD: new_parent_deal_id},
        })

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
        self._throttle_call()
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

    def _throttle_call(self) -> None:
        wait = RATE_LIMIT_SLEEP_S - (time.monotonic() - self._last_call_at_monotonic)
        if wait > 0:
            time.sleep(wait)
        self._last_call_at_monotonic = time.monotonic()

    def _ensure_fresh_state(self) -> None:
        # auth[expires] в state-файле может не отражать реальное время жизни токена
        # (поле обновляется на сервере, а не при каждом sync). Если sync проходит без
        # ошибок, токен почти наверняка живой. Pre-check ослаблен — sync делаем только
        # если действительно прошло много времени с saved_at.
        if self._expires() >= int(time.time()) + 300:
            return
        if self._last_sync_at_monotonic and time.monotonic() - self._last_sync_at_monotonic < 3600:
            return
        if not SYNC_SCRIPT.exists():
            raise BitrixTokenExpired(f"Sync-скрипт не найден: {SYNC_SCRIPT}")
        subprocess.run([str(SYNC_SCRIPT)], check=True)
        self._state = self._read_state()
        self._last_sync_at_monotonic = time.monotonic()
        # Не падаем если expires остался "плохим" — sync прошёл успешно (sync script
        # сам проверяет токен через /profile). Если REST в реальности 401 — retry-логика
        # в _call_with_retries обработает это как обычную HTTPError.
        return

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
