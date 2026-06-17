"""Дни отсутствия (отпуск/больничный/отгул) из «Графика отсутствий» Bitrix →
manager_absences. Для матрицы «Опер»: помечаем дни «Отпуск» и исключаем их из
среднего балла (отпуск не должен занижать оценку). Окно по умолчанию — текущий
месяц МСК. Идемпотентно (DELETE окна + переинзерт). На cron (run_refresh) + разово.

    python -m src.sync_absences
    python -m src.sync_absences 2026-06-01 2026-06-30
    python -m src.sync_absences --dry-run
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta

from . import bx_client
from .collect import ABSENCE_NAME_HINTS
from .db import connect
from .timeutil import MSK


def _date_head(dt) -> date | None:
    """«05.06.2026 ...» или «2026-06-05» → date."""
    parts0 = str(dt or "").split()
    if not parts0:
        return None
    head = parts0[0]
    if "." in head:
        p = head.split(".")
        if len(p) >= 3:
            try:
                return date(int(p[2]), int(p[1]), int(p[0]))
            except ValueError:
                return None
        return None
    try:
        return date.fromisoformat(head)
    except ValueError:
        return None


def _kind(name: str) -> str:
    n = name.lower()
    if "больнич" in n:
        return "больничный"
    if "отгул" in n:
        return "отгул"
    if "командир" in n:
        return "командировка"
    return "отпуск"


def fetch_absence_days(start: date, end: date, user_ids, bx=None) -> dict[tuple[int, str], str]:
    """{(manager_id, isodate): kind} — будние дни отсутствия в окне [start, end]."""
    call = bx.call if bx is not None else bx_client.call
    ids = [str(u) for u in user_ids if u not in (None, "", "0", 0)]
    out: dict[tuple[int, str], str] = {}
    for i in range(0, len(ids), 100):
        part = ids[i : i + 100]
        resp = call("calendar.accessibility.get", {"users": part, "from": start.isoformat(), "to": end.isoformat()})
        result = resp.get("result") if isinstance(resp, dict) else None
        if not isinstance(result, dict):
            continue
        for uid, events in result.items():
            try:
                mid = int(uid)
            except (TypeError, ValueError):
                continue
            for ev in events or []:
                from_hr = ev.get("FROM_HR") in (True, "true", "True", "1", 1)
                acc = str(ev.get("ACCESSIBILITY") or "").lower()
                name = str(ev.get("NAME") or "")
                if not (from_hr or acc == "absent" or any(h in name.lower() for h in ABSENCE_NAME_HINTS)):
                    continue
                d0 = _date_head(ev.get("DT_FROM") or ev.get("DATE_FROM"))
                d1 = _date_head(ev.get("DT_TO") or ev.get("DATE_TO"))
                if not d0 or not d1:
                    continue
                kind = _kind(name)
                cur = max(d0, start)
                last = min(d1, end)
                while cur <= last:
                    if cur.weekday() < 5:  # heatmap по будням
                        out[(mid, cur.isoformat())] = kind
                    cur += timedelta(days=1)
    return out


def sync(start: date, end: date, conn, bx=None, dry_run: bool = False) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT bitrix_id FROM users")
        uids = [r[0] for r in cur.fetchall()]
    days = fetch_absence_days(start, end, uids, bx)
    if not dry_run:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM manager_absences WHERE absence_date BETWEEN %s AND %s", (start, end))
            for (mid, d), kind in days.items():
                cur.execute(
                    "INSERT INTO manager_absences (manager_id, absence_date, kind) VALUES (%s,%s,%s) "
                    "ON CONFLICT (manager_id, absence_date) DO UPDATE SET kind = EXCLUDED.kind",
                    (mid, d, kind),
                )
        conn.commit()
    return {"days": len(days)}


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry-run" in argv
    pos = [a for a in argv if not a.startswith("--")]
    today = datetime.now(MSK).date()
    start = date.fromisoformat(pos[0]) if pos else today.replace(day=1)
    end = date.fromisoformat(pos[1]) if len(pos) > 1 else today
    bx_client.ensure_token_fresh()
    conn = connect()
    try:
        res = sync(start, end, conn=conn, dry_run=dry)
    finally:
        conn.close()
    print(f"[{'DRY-RUN' if dry else 'WRITTEN'}] manager_absences {start}..{end}: {res}", flush=True)


if __name__ == "__main__":
    main()
