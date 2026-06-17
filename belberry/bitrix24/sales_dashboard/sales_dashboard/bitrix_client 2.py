"""Лёгкий Bitrix REST-клиент для ETL.

Форкнут из crm_deal_merge.bitrix_client, но без write-операций и smart-process
специфики — нам нужны только list/get для чтения.
"""
from __future__ import annotations

import csv
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

from .config import MOSCOW_TZ, RATE_LIMIT_SLEEP_S, STATE_PATH, SYNC_SCRIPT


class BitrixError(RuntimeError):
    pass


class BitrixRateLimited(BitrixError):
    pass


class BitrixTokenExpired(BitrixError):
    pass


class BitrixClient:
    """Read-only Bitrix REST клиент.

    Auth берётся из STATE_PATH (общий с cloudbot на VPS). Перед первой
    операцией дёргает bitrix-sync-state.sh, если state старше часа.
    """

    def __init__(self, state_path: Path = STATE_PATH, log_path: Path | None = None):
        self.state_path = state_path
        self.log_path = log_path
        self._state = self._read_state()
        self._last_sync_check = 0.0

    # ---------------- low level ----------------

    def call(self, method: str, params: dict | None = None) -> dict:
        self._ensure_fresh_state()
        params = params or {}
        started = time.monotonic()
        body: dict[str, Any] = {}
        ok = False
        try:
            body = self._call_with_retries(method, params)
            ok = not body.get("error")
            if body.get("error"):
                err = body.get("error")
                desc = body.get("error_description", "")
                if err in ("expired_token", "invalid_token", "NO_AUTH_FOUND"):
                    raise BitrixTokenExpired(f"{err}: {desc}")
                raise BitrixError(f"{method} → {err}: {desc}")
            return body
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            self._log_call(method, params, body, ok, duration_ms)

    def paginate(self, method: str, params: dict, id_field: str = "ID") -> Iterator[dict]:
        """Безопасная пагинация через filter[>ID]+start=-1.

        Bitrix-овский start/next ломается на больших объёмах, поэтому
        тянем по нарастающему ID до пустого ответа.
        """
        last_id = 0
        while True:
            p = _deep(params)
            f = p.setdefault("filter", {})
            f[f">{id_field}"] = last_id
            p["order"] = {id_field: "ASC"}
            p["start"] = -1
            body = self.call(method, p)
            rows = body.get("result") or []
            if not rows:
                return
            for row in rows:
                yield row
                try:
                    last_id = max(last_id, int(row.get(id_field) or 0))
                except (TypeError, ValueError):
                    pass
            time.sleep(RATE_LIMIT_SLEEP_S)

    def paginate_by_start(
        self, method: str, params: dict, page_size: int = 50
    ) -> Iterator[dict]:
        """Пагинация через `start`/`next` для методов без ID-фильтра
        (например, voximplant.statistic.get).
        """
        start = 0
        while True:
            p = _deep(params)
            p["start"] = start
            body = self.call(method, p)
            rows = body.get("result") or []
            for row in rows:
                yield row
            nxt = body.get("next")
            if nxt is None or not rows:
                return
            start = int(nxt)
            time.sleep(RATE_LIMIT_SLEEP_S)

    # ---------------- state ----------------

    def _read_state(self) -> dict:
        raw = json.loads(self.state_path.read_text())
        return raw.get("payload") or raw

    def _ensure_fresh_state(self) -> None:
        now = time.time()
        if now - self._last_sync_check < 60:
            return
        self._last_sync_check = now
        try:
            expires = int(self._state.get("auth[expires]") or 0)
        except (TypeError, ValueError):
            expires = 0
        # обновим state если до истечения <5 мин
        if expires - now > 300:
            return
        self._sync_state_from_vps()

    def _sync_state_from_vps(self) -> None:
        if not SYNC_SCRIPT.exists():
            return
        try:
            subprocess.run(
                ["bash", str(SYNC_SCRIPT)],
                check=True,
                timeout=30,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            sys.stderr.write(f"[bitrix-sync] failed: {e}\n")
        self._state = self._read_state()

    # ---------------- transport ----------------

    def _call_with_retries(self, method: str, params: dict, max_retries: int = 5) -> dict:
        endpoint = self._state["auth[client_endpoint]"].rstrip("/")
        token = self._state["auth[access_token]"]
        url = f"{endpoint}/{method}"
        data = urllib.parse.urlencode(
            _flatten(params) + [("auth", token)],
            doseq=False,
        ).encode()
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, data=data, method="POST")
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    return json.loads(raw)
            except HTTPError as e:
                last_exc = e
                if e.code == 429 or e.code >= 500:
                    backoff = min(2 ** attempt, 16)
                    time.sleep(backoff)
                    continue
                # пробуем разобрать тело ошибки от Bitrix
                try:
                    return json.loads(e.read().decode("utf-8", errors="replace"))
                except Exception:
                    raise BitrixError(f"HTTP {e.code} on {method}") from e
            except (URLError, TimeoutError) as e:
                last_exc = e
                time.sleep(min(2 ** attempt, 16))
        raise BitrixError(f"{method} failed after {max_retries} retries: {last_exc}")

    # ---------------- logging ----------------

    def _log_call(
        self,
        method: str,
        params: dict,
        body: dict,
        ok: bool,
        duration_ms: int,
    ) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        row = [
            datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
            method,
            "ok" if ok else "err",
            duration_ms,
            len((body or {}).get("result") or []) if isinstance(body, dict) else 0,
            (body or {}).get("error") or "",
            json.dumps(params, ensure_ascii=False)[:500],
        ]
        write_header = not self.log_path.exists()
        with self.log_path.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(
                    ["ts", "method", "status", "duration_ms", "rows", "error", "params"]
                )
            w.writerow(row)


# ---------------- helpers ----------------


def _deep(x):
    if isinstance(x, dict):
        return {k: _deep(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_deep(v) for v in x]
    return x


def _flatten(params: dict, prefix: str = "") -> list[tuple[str, str]]:
    """Bitrix REST принимает nested dict как `filter[FIELD]=VAL`."""
    out: list[tuple[str, str]] = []
    for k, v in params.items():
        key = f"{prefix}[{k}]" if prefix else str(k)
        if isinstance(v, dict):
            out.extend(_flatten(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out.extend(_flatten(item, f"{key}[{i}]"))
                else:
                    out.append((f"{key}[{i}]", _stringify(item)))
        else:
            out.append((key, _stringify(v)))
    return out


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Y" if v else "N"
    return str(v)
