"""Обновление users.is_active из Bitrix (ACTIVE) для существующих сотрудников.

Справочник логина (users) наполняется провижинингом и НЕ обновляет статус —
уволенные остаются is_active=true (напр. Погосян, Гудинова). Дашборды (отказы,
ТМ-воронка) помечают «уволен» по статусу, поэтому держим is_active актуальным.

UPDATE по bitrix_id только для уже существующих строк (новых не создаём — нужен
email/identity). Идемпотентно. На cron (run_refresh) + разово.

    python -m src.sync_users_active
    python -m src.sync_users_active --dry-run
"""

import sys

from . import bx_client
from .db import connect


def _is_active(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "y", "yes")


def fetch_active(bx=None, max_pages: int = 80) -> dict[int, dict]:
    """Полный справочник Bitrix: {bitrix_id: {"active": bool, "hired": "YYYY-MM-DD"|None}}.
    hired — дата регистрации в Bitrix (DATE_REGISTER) как прокси даты найма."""
    call = bx.call if bx is not None else bx_client.call
    out: dict[int, dict] = {}
    start = 0
    for _ in range(max_pages):
        resp = call("user.get", {"start": start, "ADMIN_MODE": "Y"})
        result = resp.get("result") or []
        for u in result:
            uid = u.get("ID")
            if uid is None:
                continue
            try:
                key = int(uid)
            except (TypeError, ValueError):
                continue
            reg = u.get("DATE_REGISTER") or ""
            out[key] = {"active": _is_active(u.get("ACTIVE")), "hired": reg[:10] or None}
        nxt = resp.get("next")
        if not result or nxt is None:
            break
        start = nxt
    return out


def sync(conn=None, bx=None, dry_run: bool = False) -> dict[str, int]:
    info = fetch_active(bx)
    updated = 0
    if not dry_run and conn is not None and info:
        with conn.cursor() as cur:
            for uid, rec in info.items():
                # hired_at — только если ещё пусто (не перетираем ручную правку даты найма).
                cur.execute(
                    "UPDATE users SET is_active = %s, hired_at = COALESCE(hired_at, %s) WHERE bitrix_id = %s",
                    (rec["active"], rec["hired"], uid),
                )
                updated += cur.rowcount
        conn.commit()
    return {"fetched": len(info), "updated": updated}


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    bx_client.ensure_token_fresh()
    conn = None if dry_run else connect()
    try:
        res = sync(conn=conn, dry_run=dry_run)
    finally:
        if conn is not None:
            conn.close()
    print(f"[{'DRY-RUN' if dry_run else 'WRITTEN'}] users.is_active: {res}", flush=True)


if __name__ == "__main__":
    main()
