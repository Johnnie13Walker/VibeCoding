"""Разовый backfill чатов Wazzup (messenger_dialogs) в manager_activity за историю.

Чаты раньше не сохранялись (агрегат был 0 за весь период). Сырьё — в Bitrix
timeline (источник правды, не дублируем). Скрипт один раз проходит по всем сделкам
cat10/50, собирает комментарии, атрибутирует диалоги по подписи отправителя
(chat_attribution) и проставляет messenger_dialogs по дням/менеджерам в уже
существующие строки manager_activity. Идемпотентно (UPDATE, не вставка).

Запуск:
    python -m src.backfill_messenger            # dry-run (только показать)
    python -m src.backfill_messenger --apply    # запись в БД
"""

from __future__ import annotations

import argparse
from typing import Any

from . import bx_client
from .chat_attribution import attribute_dialogs_by_day
from .collect import _client, collect_employees
from .db import connect


def _fetch_deal_ids(bx=None) -> list[Any]:
    """Все сделки воронок Продажи/Телемаркетинг (open + closed)."""
    client = _client(bx)
    ids: list[Any] = []
    start = 0
    while True:
        resp = client.call(
            "crm.deal.list",
            {"filter": {"@CATEGORY_ID": [10, 50]}, "select": ["ID"], "start": start},
        )
        result = resp.get("result") or []
        ids.extend(d.get("ID") for d in result if d.get("ID"))
        nxt = resp.get("next")
        if not result or nxt is None:
            break
        start = nxt
    return ids


def _fetch_all_comments(deal_id: Any, bx=None, max_pages: int = 40) -> list[dict[str, Any]]:
    """Все timeline-комментарии сделки (постранично — длинные переписки >50)."""
    client = _client(bx)
    out: list[dict[str, Any]] = []
    start = 0
    for _ in range(max_pages):
        resp = client.call(
            "crm.timeline.comment.list",
            {"filter": {"ENTITY_ID": deal_id, "ENTITY_TYPE": "deal"}, "order": {"ID": "DESC"}, "start": start},
        )
        result = resp.get("result") or []
        out.extend(result)
        nxt = resp.get("next")
        if not result or nxt is None:
            break
        start = nxt
    return out


def collect_all_comments(bx=None, progress_every: int = 200) -> dict[Any, list[dict[str, Any]]]:
    deal_ids = _fetch_deal_ids(bx)
    print(f"deals to scan: {len(deal_ids)}", flush=True)
    wazzup: dict[Any, list[dict[str, Any]]] = {}
    for i, did in enumerate(deal_ids):
        comments = _fetch_all_comments(did, bx)
        if comments:
            wazzup[did] = comments
        if i % progress_every == 0:
            print(f"... {i}/{len(deal_ids)} deals scanned", flush=True)
    return wazzup


def run(dry_run: bool = True, bx=None, conn=None) -> dict[str, int]:
    bx_client.ensure_token_fresh()
    employees = collect_employees(bx)
    print(f"employees: {len(employees)}", flush=True)
    wazzup = collect_all_comments(bx)
    by_day = attribute_dialogs_by_day(wazzup, employees)
    total_dialogs = sum(sum(m.values()) for m in by_day.values())
    print(f"chat days: {len(by_day)} | total dialogs: {total_dialogs}", flush=True)

    own_conn = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT report_date, manager_id FROM manager_activity")
            existing = {(str(d), int(m)) for d, m in cur.fetchall()}

        updated = 0
        skipped_no_row = 0
        for day, mgrs in by_day.items():
            for mid, n in mgrs.items():
                if (day, int(mid)) not in existing:
                    skipped_no_row += 1  # менеджер чатился, но строки активности за день нет
                    continue
                if dry_run:
                    updated += 1
                    continue
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE manager_activity SET messenger_dialogs = %s "
                        "WHERE report_date = %s AND manager_id = %s",
                        (n, day, int(mid)),
                    )
                    updated += cur.rowcount
        if not dry_run:
            conn.commit()
    finally:
        if own_conn:
            conn.close()

    stats = {"days": len(by_day), "updated": updated, "skipped_no_row": skipped_no_row, "dry_run": int(dry_run)}
    print(f"RESULT {stats}", flush=True)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill messenger_dialogs (Wazzup chats)")
    parser.add_argument("--apply", action="store_true", help="записать в БД (по умолчанию dry-run)")
    args = parser.parse_args()
    run(dry_run=not args.apply)
