import argparse
from datetime import date

from src import bx_client
from src.config import load_config
from src.db import connect
from src.collect import collect_day
from src.render import extract_rejections, render_report
from src.transform import build_db_rows, compute_stale_deals, resolve_target_date
from src.timeutil import now_msk
from src.writer import write_day


def build_extras(raw: dict, now) -> dict:
    return {
        "raw": raw,
        "report_date": raw.get("report_date"),
        "stale": compute_stale_deals(raw.get("deals_open", []), now, raw.get("wazzup")),
        "users": raw.get("users", {}),
        "photos": raw.get("photos", {}),
        "rejections": extract_rejections(raw, raw.get("users", {})),
    }


def already_done(conn, target: date) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM reports WHERE report_date = %s",
            (target.isoformat(),),
        )
        row = cursor.fetchone()
    return bool(row and row[0] == "done")


def run(
    target: date | None = None,
    *,
    force: bool = False,
    bx=None,
    connect_fn=connect,
    now_fn=now_msk,
):
    load_config(["DATABASE_URL"])
    target = target or resolve_target_date(None)
    conn = connect_fn()

    if not force and already_done(conn, target):
        return {"status": "skipped", "report_date": target.isoformat()}

    bx_client.ensure_token_fresh()
    now = now_fn()
    raw = collect_day(target, bx=bx)
    raw.setdefault("report_date", target.isoformat())
    rows = build_db_rows(raw, target, now)
    extras = build_extras(raw, now)
    html = render_report(rows, extras)
    summary = {
        "generated_at": now.isoformat(),
        "report_date": target.isoformat(),
        "counts": {key: len(value) for key, value in rows.items()},
    }
    counts = write_day(conn, target, rows, html, summary)
    conn.commit()
    return {"status": "done", "report_date": target.isoformat(), "counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Дата отчёта YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Перегенерировать готовый день")
    args = parser.parse_args()
    target = resolve_target_date(args.date)
    result = run(target, force=args.force)
    print(result)


if __name__ == "__main__":
    main()
