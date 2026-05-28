#!/usr/bin/env python3
"""
Read-only probe of Bitrix24 via shared OAuth state.

Не делает refresh токена — если access_token истёк, выходит с ошибкой
и просит пользователя пересинхронизировать state с VPS. Это сознательное
ограничение: state файл общий с cloudbot/VPS, и параллельный refresh
с двух машин может десинхронизировать refresh_token.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

STATE_PATH = Path(
    os.environ.get(
        "BITRIX_APP_STATE_DIR",
        "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state",
    )
) / "install.latest.json"


def load_state() -> dict:
    if not STATE_PATH.exists():
        sys.exit(f"state-файл не найден: {STATE_PATH}")
    return json.loads(STATE_PATH.read_text())


def call(method: str, params: dict | None = None) -> dict:
    state = load_state()
    auth = state["payload"]
    endpoint = auth["auth[client_endpoint]"].rstrip("/")
    token = auth["auth[access_token]"]
    url = f"{endpoint}/{method}"
    data = urllib.parse.urlencode(
        {"auth": token, **(params or {})}, doseq=True
    ).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
    if "error" in body:
        if body.get("error") == "expired_token":
            sys.exit(
                "⚠ access_token истёк. На маке refresh делать НЕ будем "
                "(shared state с VPS). Пересинхронизируй state с сервера."
            )
        sys.exit(f"API error: {body}")
    return body


def probe_smart_processes() -> None:
    print("=== Смарт-процессы (crm.type.list) ===")
    r = call("crm.type.list")
    types = r.get("result", {}).get("types", [])
    if not types:
        print("(смарт-процессов в портале нет)")
        return
    for t in types:
        print(
            f"  entityTypeId={t.get('entityTypeId')}  "
            f"title={t.get('title')!r}  "
            f"isUseInUserfieldEnabled={t.get('isUseInUserfieldEnabled')}"
        )
    matches = [
        t for t in types
        if "проект" in (t.get("title") or "").lower()
        or "project" in (t.get("title") or "").lower()
        or "сайт" in (t.get("title") or "").lower()
    ]
    print(
        f"  → совпадений по 'Проект/Project/Сайт': "
        f"{len(matches)} ({[m.get('title') for m in matches]})"
    )


def probe_companies(limit: int = 5) -> None:
    print(f"\n=== Последние {limit} компаний (crm.company.list) ===")
    r = call(
        "crm.company.list",
        {
            "order[ID]": "DESC",
            "select[]": ["ID", "TITLE", "DATE_CREATE"],
            "start": 0,
        },
    )
    for c in (r.get("result") or [])[:limit]:
        print(
            f"  ID={c.get('ID'):>6}  TITLE={c.get('TITLE')!r}  "
            f"created={c.get('DATE_CREATE')}"
        )
    print(f"  total в портале: {r.get('total', '?')}")


def probe_test_company() -> None:
    print("\n=== Поиск тестовой компании (TITLE LIKE TEST/тест) ===")
    r = call(
        "crm.company.list",
        {
            "filter[%TITLE]": "TEST",
            "select[]": ["ID", "TITLE"],
        },
    )
    found = r.get("result") or []
    r2 = call(
        "crm.company.list",
        {
            "filter[%TITLE]": "тест",
            "select[]": ["ID", "TITLE"],
        },
    )
    found += r2.get("result") or []
    if not found:
        print("  (тестовых компаний не найдено)")
        return
    for c in found[:10]:
        print(f"  ID={c.get('ID')}  TITLE={c.get('TITLE')!r}")


if __name__ == "__main__":
    state = load_state()
    auth = state["payload"]
    print(f"endpoint: {auth['auth[client_endpoint]']}")
    print(f"scope:    {auth['auth[scope]']}")
    probe_smart_processes()
    probe_companies()
    probe_test_company()
