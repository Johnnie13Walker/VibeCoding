"""Тонкий клиент Bitrix REST: OAuth из state-файла + retry на 429/5xx + пагинация."""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterator

# Предохранитель: физическое удаление CRM-сущностей запрещено по умолчанию.
# Снять блок можно только явным BITRIX_ALLOW_DELETE=1. Unbind-методы
# (crm.*.company.delete, crm.deal.contact.delete и т.п.) — это разрыв связи,
# не удаление сущности, и под блок НЕ попадают.
_DESTRUCTIVE_METHODS = frozenset(
    {"crm.company.delete", "crm.contact.delete", "crm.deal.delete", "crm.lead.delete"}
)


def _delete_allowed() -> bool:
    return os.environ.get("BITRIX_ALLOW_DELETE", "0") == "1"


class BitrixClient:
    def __init__(self, state_path: Path):
        payload = json.loads(state_path.read_text())["payload"]
        self.endpoint = payload["auth[client_endpoint]"].rstrip("/")
        self.token = payload["auth[access_token]"]

    def call(self, method: str, params: list[tuple[str, str]], max_tries: int = 6) -> dict:
        if method in _DESTRUCTIVE_METHODS and not _delete_allowed():
            return {
                "result": False,
                "error": "DELETE_BLOCKED",
                "error_description": (
                    f"Удаление {method} заблокировано предохранителем "
                    "(BITRIX_ALLOW_DELETE!=1) — ничего не удаляем."
                ),
            }
        url = f"{self.endpoint}/{method}"
        data = urllib.parse.urlencode([("auth", self.token), *params]).encode()
        last_err = None
        for attempt in range(max_tries):
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(url, data=data), timeout=90
                ) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                last_err = e
                code = e.code
                # Bitrix отдаёт "ожидаемые" ошибки (Not found / ERROR_BATCH_LENGTH_EXCEEDED
                # и т.п.) через HTTP 400 с JSON-телом — это не сбой транспорта, это бизнес-
                # ответ, и обрабатываться должен в caller, а не как exception.
                if code == 400:
                    try:
                        body = e.read().decode()
                        return json.loads(body)
                    except (ValueError, json.JSONDecodeError):
                        raise
                if code in (429, 500, 502, 503, 504) and attempt < max_tries - 1:
                    time.sleep(min(60, 2 ** attempt + 1))
                    continue
                raise
            except urllib.error.URLError as e:
                last_err = e
                if attempt < max_tries - 1:
                    time.sleep(min(60, 2 ** attempt + 1))
                    continue
                raise
        raise last_err  # type: ignore[misc]

    def paginate(
        self,
        method: str,
        select: list[str],
        extra_filters: list[tuple[str, str]] | None = None,
    ) -> Iterator[dict]:
        """Стандартный paginator `filter[>ID] + order[ID]=ASC + start=-1`."""
        last_id = 0
        while True:
            params: list[tuple[str, str]] = [
                ("filter[>ID]", str(last_id)),
                ("order[ID]", "ASC"),
                ("start", "-1"),
            ]
            for f in select:
                params.append(("select[]", f))
            if extra_filters:
                params.extend(extra_filters)
            resp = self.call(method, params)
            batch = resp.get("result", [])
            if not batch:
                return
            for item in batch:
                yield item
            last_id = int(batch[-1]["ID"])
            if len(batch) < 50:
                return
