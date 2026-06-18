"""Синк когорты воронки Продажи [10] в таблицу funnel_cohort — СОБЫТИЙНО по входу.

Когорта = сделки, ВОШЕДШИЕ в воронку [10] за период (переход в C10:NEW в
stagehistory). НЕ по дате создания сделки: сделки живут в Телемаркетинге [50]
давно, а в Продажи переходят позже — «вход» воронки = момент перехода в [10],
а не создание карточки. cohort_date = дата входа (первый C10:NEW).

Для каждой считаем самую дальнюю достигнутую стадию (из stagehistory + текущая),
чтобы дашборд честно показывал «из вошедших за месяц сколько ДОШЛО до этапа X» —
по ОДНИМ И ТЕМ ЖЕ сделкам (а не distinct-события КП/защиты, которые могли быть по
сделкам, вошедшим в прошлые месяцы — старый гибрид).

Почему furthest-stage, а не текущая: сделка, дошедшая до «Защиты» и затем
отвалившаяся, сейчас на C10:LOSE — по текущей стадии она бы недосчиталась в
середине. История ловит максимум достигнутого.

Идемпотентно (upsert по deal_id). Один прогон с начала года = бэкафилл + свежесть
на cron. НЕ трогает дневной пайплайн.

    python -m src.sync_funnel_cohort
    python -m src.sync_funnel_cohort --dry-run
    python -m src.sync_funnel_cohort --since 2026-01-01
"""

import sys
from datetime import date
from typing import Any

from . import bx_client
from .collect import _fetch_all
from .db import connect, upsert
from .funnel_stages import LOST_STAGES_10, WON_STAGE_10, furthest_order, stage_order
from .transform import parse_dt

SALES_CATEGORY = 10
ENTRY_STAGE = "C10:NEW"  # вход в воронку Продажи
REASON_FIELD_10 = "UF_CRM_1771495464"  # причина отвала (8588 = СПАМ)


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(value):
    """Поле причины может прийти списком (enumeration) — берём первый код."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def fetch_stage_history(bx, since: str) -> dict[int, list[dict[str, Any]]]:
    """Из stagehistory cat10: по сделке — список переходов {stage, ct} с since."""
    rows = _fetch_all(
        bx,
        "crm.stagehistory.list",
        {
            "entityTypeId": 2,
            "filter": {"CATEGORY_ID": SALES_CATEGORY, ">=CREATED_TIME": f"{since}T00:00:00"},
            "select": ["OWNER_ID", "STAGE_ID", "CREATED_TIME", "CATEGORY_ID"],
        },
    )
    hist: dict[int, list[dict[str, Any]]] = {}
    for h in rows:
        did = _to_int(h.get("OWNER_ID"))
        st = h.get("STAGE_ID")
        if did is None or not st:
            continue
        hist.setdefault(did, []).append({"stage": st, "ct": h.get("CREATED_TIME")})
    return hist


def fetch_deals_by_ids(bx, ids: list[int]) -> dict[int, dict[str, Any]]:
    """Текущие поля сделок по ID (стадия/владелец/сумма), пакетами по 50."""
    out: dict[int, dict[str, Any]] = {}
    for chunk in _chunks(list(ids), 50):
        for d in _fetch_all(
            bx,
            "crm.deal.list",
            {"filter": {"@ID": chunk}, "select": ["ID", "ASSIGNED_BY_ID", "STAGE_ID", "OPPORTUNITY", "CATEGORY_ID", REASON_FIELD_10]},
        ):
            did = _to_int(d.get("ID"))
            if did is not None:
                out[did] = d
    return out


def _entered_at(events: list[dict[str, Any]]) -> str | None:
    """Дата входа в [10] = самый ранний переход в C10:NEW. None — входа в окне нет."""
    news = [e["ct"] for e in events if e.get("stage") == ENTRY_STAGE and e.get("ct")]
    return min(news) if news else None


def build_cohort_rows(
    deals_by_id: dict[int, dict[str, Any]], history: dict[int, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """История переходов + текущие поля → строки funnel_cohort. Чистая функция.
    В когорту попадают только сделки с входом (C10:NEW) в окне."""
    rows: list[dict[str, Any]] = []
    for did, events in history.items():
        entered = _entered_at(events)
        if not entered:
            continue  # вошла в [10] раньше окна — не наша когорта периода
        ent_dt = parse_dt(entered)
        d = deals_by_id.get(did, {})
        current = d.get("STAGE_ID")
        stages: set[str] = {e["stage"] for e in events if e.get("stage")}
        if current:
            stages.add(current)
        order = furthest_order(stages)
        fstage = next((s for s in stages if stage_order(s) == order), None) if order else None
        rows.append(
            {
                "deal_id": did,
                "category_id": SALES_CATEGORY,
                "cohort_date": ent_dt.date() if ent_dt else None,
                "manager_id": _to_int(d.get("ASSIGNED_BY_ID")),
                "current_stage": current,
                "furthest_stage": fstage,
                "furthest_order": order,
                "is_won": WON_STAGE_10 in stages,
                "is_lost": bool(stages & LOST_STAGES_10),
                "opportunity": _to_float(d.get("OPPORTUNITY")),
                "reason_id": _to_int(_first(d.get(REASON_FIELD_10))),
            }
        )
    return rows


def sync(conn=None, bx=None, dry_run: bool = False, since: str | None = None) -> dict[str, int]:
    since = since or f"{date.today().year}-01-01"
    history = fetch_stage_history(bx, since)
    deals_by_id = fetch_deals_by_ids(bx, list(history.keys())) if history else {}
    rows = build_cohort_rows(deals_by_id, history)

    written = 0
    if not dry_run and conn is not None and rows:
        update_cols = [c for c in rows[0] if c != "deal_id"]
        written = upsert(conn, "funnel_cohort", rows, ["deal_id"], update_cols)
        conn.commit()
    return {
        "history_deals": len(history),
        "fetched_deals": len(deals_by_id),
        "rows": len(rows),
        "written": written,
    }


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    since = None
    if "--since" in argv:
        idx = argv.index("--since")
        if idx + 1 < len(argv):
            since = argv[idx + 1]
    bx_client.ensure_token_fresh()
    conn = None if dry_run else connect()
    try:
        res = sync(conn=conn, dry_run=dry_run, since=since)
    finally:
        if conn is not None:
            conn.close()
    print(f"[{'DRY-RUN' if dry_run else 'WRITTEN'}] funnel_cohort: {res}", flush=True)


if __name__ == "__main__":
    main()
