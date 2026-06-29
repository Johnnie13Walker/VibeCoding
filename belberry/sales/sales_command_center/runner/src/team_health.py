"""Дневной снимок «Команда · эффективность и просрочки» для /alerts/tasks.

По каждому действующему сотруднику ОП+РОП считаем:
  • КПД (наш): доля задач, закрытых ВОВРЕМЯ, среди закрытых за 30 дней с дедлайном.
    Родной «Эффективности» Bitrix в REST нет (проверено) — считаем сами.
  • overdue_tasks: просроченные задачи (tasks.task.list, дедлайн в прошлом, не завершена).
  • overdue_activities: просроченные CRM-дела (crm.activity.list, COMPLETED=N, END_TIME в прошлом).

Списки самих просрочек НЕ храним — detail-страница тянет их живьём из Bitrix.
Запуск: python -m src.team_health [--date YYYY-MM-DD] [--dry-run]
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta

from .bx_client import call
from .db import connect, upsert
from .timeutil import MSK, now_msk

TABLE = "team_task_health"
EFF_WINDOW_DAYS = 30
TASK_STATUS_DONE = 5  # Завершена


def is_sales_rop(position: str | None) -> bool:
    """ОП + РОП по должности, телемаркетинг исключаем. РОП в Bitrix записан буквально
    «РОП» (не содержит «продаж»), поэтому ловим и его."""
    low = (position or "").strip().lower()
    if "телемарк" in low:
        return False
    return "продаж" in low or low == "роп"


def is_telemarketing(position: str | None) -> bool:
    """Телемаркетолог по должности."""
    return "телемарк" in (position or "").lower()


def in_team(position: str | None) -> bool:
    """Весь отдел продаж: ОП + РОП + телемаркетинг (группируем на стороне веба по dept)."""
    return is_sales_rop(position) or is_telemarketing(position)


def _g(item: dict, *keys):
    """Достаёт значение по любому из вариантов написания ключа (REST задач отдаёт
    camelCase: deadline/closedDate, CRM — UPPER: END_TIME)."""
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return None


def _user_get_all(bx_call=call) -> list[dict]:
    """Все активные пользователи (user.get пагинируется по 50 через next)."""
    out: list[dict] = []
    start = 0
    while True:
        resp = bx_call("user.get", {"filter": {"ACTIVE": "Y"}, "start": start})
        res = resp.get("result", []) if isinstance(resp, dict) else (resp or [])
        if not res:
            break
        out.extend(res)
        nxt = resp.get("next") if isinstance(resp, dict) else None
        if nxt is None:
            break
        start = nxt
    return out


def _roster(bx_call=call) -> list[dict]:
    """Действующие ОП+РОП из Bitrix (ACTIVE=Y), отфильтрованные по должности."""
    out = []
    for u in _user_get_all(bx_call):
        pos = u.get("WORK_POSITION")
        if not in_team(pos):
            continue
        name = " ".join(p for p in (u.get("LAST_NAME"), u.get("NAME")) if p).strip()
        out.append({
            "manager_id": int(u["ID"]),
            "name": name or f"#{u['ID']}",
            "dept": pos,
        })
    return out


def _list_total(method: str, flt: dict, bx_call=call) -> int:
    """Кол-во записей по фильтру (берём total из одного вызова, без выкачки списка)."""
    resp = bx_call(method, {"filter": flt, "select": ["ID"], "start": 0})
    if isinstance(resp, dict) and resp.get("error") and "result" not in resp:
        raise RuntimeError(f"Bitrix {method} failed: {resp.get('error')}")
    return int(resp.get("total") or 0) if isinstance(resp, dict) else 0


def _tasks_all(flt: dict, select: list[str], bx_call=call, cap: int = 2000) -> list[dict]:
    """Пагинация tasks.task.list (result.tasks, offset через start)."""
    out: list[dict] = []
    start = 0
    while len(out) < cap:
        resp = bx_call("tasks.task.list", {"filter": flt, "select": select, "start": start})
        if isinstance(resp, dict) and resp.get("error") and "result" not in resp:
            raise RuntimeError(f"Bitrix tasks.task.list failed: {resp.get('error')}")
        result = resp.get("result", {}) if isinstance(resp, dict) else {}
        tasks = result.get("tasks", []) if isinstance(result, dict) else (result or [])
        if not tasks:
            break
        out.extend(tasks)
        if len(tasks) < 50:
            break
        start += 50
    return out[:cap]


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def compute_efficiency(closed_tasks: list[dict]) -> tuple[int, int, float | None]:
    """(закрытых_с_дедлайном, закрытых_вовремя, КПД %). Без дедлайна не учитываем —
    нарушить срок нельзя. Нет закрытых с дедлайном → КПД=None («—»)."""
    with_dl = 0
    ontime = 0
    for t in closed_tasks:
        deadline = _parse_dt(_g(t, "deadline", "DEADLINE"))
        if not deadline:
            continue
        with_dl += 1
        closed = _parse_dt(_g(t, "closedDate", "CLOSED_DATE", "dateFinish"))
        if closed and closed <= deadline:
            ontime += 1
    pct = round(ontime / with_dl * 100, 2) if with_dl else None
    return with_dl, ontime, pct


def collect_member(manager_id: int, now: datetime, bx_call=call) -> dict:
    now_iso = now.replace(microsecond=0).isoformat()
    since_iso = (now - timedelta(days=EFF_WINDOW_DAYS)).replace(microsecond=0).isoformat()

    overdue_tasks = _list_total(
        "tasks.task.list",
        {"RESPONSIBLE_ID": manager_id, "<DEADLINE": now_iso, "!STATUS": str(TASK_STATUS_DONE)},
        bx_call,
    )
    overdue_activities = _list_total(
        "crm.activity.list",
        {"RESPONSIBLE_ID": manager_id, "COMPLETED": "N", "<END_TIME": now_iso},
        bx_call,
    )
    closed = _tasks_all(
        {"RESPONSIBLE_ID": manager_id, "STATUS": str(TASK_STATUS_DONE), ">=CLOSED_DATE": since_iso},
        ["ID", "DEADLINE", "CLOSED_DATE"],
        bx_call,
    )
    with_dl, ontime, pct = compute_efficiency(closed)
    return {
        "overdue_tasks": overdue_tasks,
        "overdue_activities": overdue_activities,
        "closed_with_deadline": with_dl,
        "closed_ontime": ontime,
        "efficiency_pct": pct,
    }


def build_rows(report_date: date, now: datetime, bx_call=call) -> list[dict]:
    rows = []
    for m in _roster(bx_call):
        metrics = collect_member(m["manager_id"], now, bx_call)
        rows.append({
            "report_date": report_date,
            "manager_id": m["manager_id"],
            "name": m["name"],
            "dept": m["dept"],
            "is_active": True,
            **metrics,
            "collected_at": now,
        })
    return rows


def write_snapshot(conn, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    update_cols = [c for c in cols if c not in ("report_date", "manager_id")]
    return upsert(conn, TABLE, rows, ["report_date", "manager_id"], update_cols)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Снимок эффективности и просрочек команды ОП")
    parser.add_argument("--date", help="report_date YYYY-MM-DD (по умолчанию сегодня МСК)")
    parser.add_argument("--dry-run", action="store_true", help="не писать в БД, только показать")
    args = parser.parse_args(argv)

    now = now_msk()
    report_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else now.date()
    rows = build_rows(report_date, now)

    print(f"[team_health] {report_date}: сотрудников ОП+РОП = {len(rows)}", flush=True)
    for r in rows:
        print(
            f"  {r['name']:<28} КПД={r['efficiency_pct']}  "
            f"задачи_просроч={r['overdue_tasks']}  дела_просроч={r['overdue_activities']}  "
            f"(закрыто с дедлайном {r['closed_ontime']}/{r['closed_with_deadline']})",
            flush=True,
        )
    if args.dry_run:
        print("[team_health] DRY-RUN — в БД не пишу", flush=True)
        return

    with connect() as conn:
        n = write_snapshot(conn, rows)
        conn.commit()
    print(f"[team_health] записано строк: {n}", flush=True)


if __name__ == "__main__":
    main()
