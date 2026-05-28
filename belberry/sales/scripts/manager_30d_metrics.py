"""Per-manager 30-day metrics in Lev-Petrovich row format.

Тянет через локальный bitrix-state (тот же, что использует sales_dashboard).
Выводит строку формата `Статус Менеджер Роль Наб Дзв Конв Чаты Встр Опер`
и блок диагностики по сделкам за окно.

Запуск:
    python3 belberry/sales/scripts/manager_30d_metrics.py 2846   # Семенихин Егор
    python3 belberry/sales/scripts/manager_30d_metrics.py 2822   # Смирнов Илья
    python3 belberry/sales/scripts/manager_30d_metrics.py 2846 2822
    python3 belberry/sales/scripts/manager_30d_metrics.py --days 30 2846

Ограничения:
  * Чаты считаются по crm.activity.list (PROVIDER_ID IMOPENLINES_SESSION /
    IMOL / WHATSAPP / etc), а не из Wazzup-архива (тот лежит на VPS).
    Дельта против отчёта Льва Петровича возможна.
  * Опер — НЕ оригинальная формула Льва Петровича (она не в локальном репо).
    Тут считается прозрачный прокси: см. comments в `compute_oper`.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "belberry" / "bitrix24" / "sales_dashboard"))

from sales_dashboard.bitrix_client import BitrixClient  # noqa: E402
from sales_dashboard import config  # noqa: E402

MSK = config.MOSCOW_TZ

MEETING_DONE_STAGE = "DT1048_24:SUCCESS"
BRIEF_DONE_STAGE = "DT1056_28:SUCCESS"

CHAT_PROVIDERS = {
    "IMOPENLINES_SESSION",
    "IMOL",
    "CRM_WHATSAPP",
    "WAZZUP",
    "WAZZUP24",
}


def fmt_dt(dt: datetime) -> str:
    return dt.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S")


def get_user(bx: BitrixClient, user_id: int) -> dict:
    body = bx.call("user.get", {"FILTER": {"ID": user_id}, "ADMIN_MODE": "Y"})
    rows = body.get("result") or []
    return rows[0] if rows else {}


def get_calls(bx: BitrixClient, user_id: int, since: datetime, until: datetime) -> dict:
    """Возвращает {nabor, dozvon, missed_in, in_total, total}."""
    flt = {
        ">=CALL_START_DATE": fmt_dt(since),
        "<CALL_START_DATE": fmt_dt(until),
        "PORTAL_USER_ID": user_id,
    }
    nab = 0          # CALL_TYPE=1 (исходящие) — попытки
    doz = 0          # исходящие с CALL_FAILED_CODE=200 и duration>0
    in_total = 0     # CALL_TYPE in (2,4)
    in_missed = 0    # CALL_TYPE=3 ИЛИ (входящие c FAILED_CODE != 200)
    total = 0
    for c in bx.paginate_by_start(
        "voximplant.statistic.get",
        {"filter": flt, "sort": "CALL_START_DATE", "order": "ASC"},
    ):
        total += 1
        ct = str(c.get("CALL_TYPE") or "")
        dur = int(c.get("CALL_DURATION") or 0)
        code = str(c.get("CALL_FAILED_CODE") or "")
        if ct == "1":
            nab += 1
            if code == "200" and dur > 0:
                doz += 1
        elif ct in ("2", "4"):
            in_total += 1
            if code != "200" or dur <= 0:
                in_missed += 1
        elif ct == "3":
            in_total += 1
            in_missed += 1
    return {
        "nabor": nab,
        "dozvon": doz,
        "incoming": in_total,
        "missed_in": in_missed,
        "total": total,
    }


def count_smart_items_done(
    bx: BitrixClient,
    entity_type_id: int,
    category_id: int,
    done_stage: str,
    user_id: int,
    since: datetime,
    until: datetime,
) -> int:
    """Считаем item-ы, переведённые в done-стадию в окне.

    Берём по дате updatedTime ≥ since, stageId=done, assignedById=user.
    Это упрощение: settled deals в крайних случаях могли быть перетащены
    в DONE раньше окна и потом отредактированы. Для МСК-окна 30 дней
    погрешность мизерная.
    """
    flt = {
        "entityTypeId": entity_type_id,
        "filter": {
            "categoryId": category_id,
            "stageId": done_stage,
            "assignedById": user_id,
            ">=updatedTime": fmt_dt(since),
            "<updatedTime": fmt_dt(until),
        },
        "select": ["id"],
    }
    n = 0
    start = 0
    while True:
        p = dict(flt)
        p["start"] = start
        body = bx.call("crm.item.list", p)
        result = body.get("result") or {}
        items = result.get("items") or []
        n += len(items)
        nxt = body.get("next")
        if nxt is None or not items:
            return n
        start = int(nxt)


def get_chat_activities(
    bx: BitrixClient,
    user_id: int,
    since: datetime,
    until: datetime,
) -> int:
    """crm.activity.list по чат-провайдерам, RESPONSIBLE_ID = user_id."""
    flt = {
        "RESPONSIBLE_ID": user_id,
        ">=CREATED": fmt_dt(since),
        "<CREATED": fmt_dt(until),
    }
    n = 0
    for a in bx.paginate(
        "crm.activity.list",
        {"filter": flt, "select": ["ID", "PROVIDER_ID", "PROVIDER_TYPE_ID", "CREATED"]},
    ):
        if (a.get("PROVIDER_ID") or "") in CHAT_PROVIDERS:
            n += 1
    return n


def get_deal_metrics(
    bx: BitrixClient,
    user_id: int,
    since: datetime,
    until: datetime,
) -> dict:
    """Сделки менеджера: создано, выиграно, проиграно, текущие активные.

    CATEGORY_ID=10 (sales-воронка по контракту Льва Петровича).
    """
    created = won = lost = 0
    won_amount = 0.0
    lost_amount = 0.0
    won_currencies = set()
    # created in window
    for d in bx.paginate(
        "crm.deal.list",
        {
            "filter": {
                "ASSIGNED_BY_ID": user_id,
                "CATEGORY_ID": 10,
                ">=DATE_CREATE": fmt_dt(since),
                "<DATE_CREATE": fmt_dt(until),
            },
            "select": ["ID", "STAGE_SEMANTIC_ID", "OPPORTUNITY", "CURRENCY_ID"],
        },
    ):
        created += 1

    # closed in window
    for d in bx.paginate(
        "crm.deal.list",
        {
            "filter": {
                "ASSIGNED_BY_ID": user_id,
                "CATEGORY_ID": 10,
                "CLOSED": "Y",
                ">=CLOSEDATE": fmt_dt(since),
                "<CLOSEDATE": fmt_dt(until),
            },
            "select": ["ID", "STAGE_SEMANTIC_ID", "OPPORTUNITY", "CURRENCY_ID"],
        },
    ):
        sem = d.get("STAGE_SEMANTIC_ID")
        amt = float(d.get("OPPORTUNITY") or 0)
        cur = d.get("CURRENCY_ID") or "RUB"
        if sem == "S":
            won += 1
            won_amount += amt
            won_currencies.add(cur)
        elif sem == "F":
            lost += 1
            lost_amount += amt

    # active right now
    active = 0
    active_amount = 0.0
    for d in bx.paginate(
        "crm.deal.list",
        {
            "filter": {
                "ASSIGNED_BY_ID": user_id,
                "CATEGORY_ID": 10,
                "CLOSED": "N",
            },
            "select": ["ID", "OPPORTUNITY", "CURRENCY_ID"],
        },
    ):
        active += 1
        active_amount += float(d.get("OPPORTUNITY") or 0)

    return {
        "created": created,
        "won": won,
        "won_amount": won_amount,
        "lost": lost,
        "lost_amount": lost_amount,
        "active": active,
        "active_amount": active_amount,
    }


def compute_oper(calls: dict, chats: int, meetings: int, briefs: int, deals: dict) -> float:
    """Прозрачный прокси «Опер» (НЕ оригинальная формула Льва Петровича).

    Шкала 0..10. Веса подобраны под смысл sales-роли:
      * call activity (нормировано к 30-дневной норме 200 наборов): 0..3.0
      * conversion (доля дозвонов от наборов, потолок 50%): 0..2.0
      * чаты (норма 100 за 30 дней): 0..1.5
      * встречи (норма 20 за 30 дней): 0..1.5
      * брифы принятые (норма 8): 0..1.0
      * выигранные сделки (норма 4): 0..1.0

    Это инструмент для сравнения внутри списка, а не KPI на премию.
    """
    nab, doz = calls["nabor"], calls["dozvon"]
    conv = (doz / nab) if nab else 0.0
    s_calls = min(nab / 200.0, 1.0) * 3.0
    s_conv = min(conv / 0.5, 1.0) * 2.0
    s_chats = min(chats / 100.0, 1.0) * 1.5
    s_meet = min(meetings / 20.0, 1.0) * 1.5
    s_brief = min(briefs / 8.0, 1.0) * 1.0
    s_won = min(deals["won"] / 4.0, 1.0) * 1.0
    return round(s_calls + s_conv + s_chats + s_meet + s_brief + s_won, 1)


def status_label(oper: float) -> str:
    if oper >= 6.5:
        return "НОРМ"
    if oper >= 4.0:
        return "РИСК"
    return "СТОП"


def short_name(user: dict) -> str:
    return f"{user.get('LAST_NAME', '')} {user.get('NAME', '')}".strip()


def aggregate(bx: BitrixClient, user_id: int, since: datetime, until: datetime) -> dict:
    u = get_user(bx, user_id)
    calls = get_calls(bx, user_id, since, until)
    chats = get_chat_activities(bx, user_id, since, until)
    meetings = count_smart_items_done(bx, 1048, 24, MEETING_DONE_STAGE, user_id, since, until)
    briefs = count_smart_items_done(bx, 1056, 28, BRIEF_DONE_STAGE, user_id, since, until)
    deals = get_deal_metrics(bx, user_id, since, until)
    oper = compute_oper(calls, chats, meetings, briefs, deals)
    return {
        "user": u,
        "user_id": user_id,
        "name": short_name(u),
        "calls": calls,
        "chats": chats,
        "meetings": meetings,
        "briefs": briefs,
        "deals": deals,
        "oper": oper,
        "status": status_label(oper),
    }


def print_row(r: dict) -> None:
    c = r["calls"]
    conv = (c["dozvon"] / c["nabor"] * 100) if c["nabor"] else 0
    print(
        f"{r['status']:<6}{r['name']:<22}SM   "
        f"{c['nabor']:>4} {c['dozvon']:>4} {conv:>4.0f}% "
        f"{r['chats']:>4} {r['meetings']:>4} {r['oper']:>4.1f}"
    )


def print_diag(r: dict, since: datetime, until: datetime) -> None:
    c = r["calls"]
    d = r["deals"]
    print(f"\n--- {r['name']} (ID={r['user_id']}) — окно {since.date()}..{until.date()} ---")
    print(f"Звонки     : наб {c['nabor']} | дозвон {c['dozvon']} | "
          f"входящие {c['incoming']} (пропущено {c['missed_in']}) | всего {c['total']}")
    print(f"Чаты       : {r['chats']} активностей через open-channels")
    print(f"Встречи    : проведено {r['meetings']} (стадия SUCCESS smart 1048/24)")
    print(f"Брифы      : принято производством {r['briefs']} (smart 1056/28 SUCCESS)")
    print(f"Сделки (cat 10):")
    print(f"  создано в окне : {d['created']}")
    print(f"  выиграно       : {d['won']} / {d['won_amount']:,.0f} ₽")
    print(f"  проиграно      : {d['lost']} / {d['lost_amount']:,.0f} ₽")
    print(f"  активных сейчас: {d['active']} / {d['active_amount']:,.0f} ₽")
    print(f"Опер (прокси): {r['oper']} → статус {r['status']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("user_ids", nargs="+", type=int, help="Bitrix user IDs")
    ap.add_argument("--days", type=int, default=30, help="окно в днях (default 30)")
    args = ap.parse_args()

    until = datetime.now(MSK).replace(microsecond=0)
    since = until - timedelta(days=args.days)

    bx = BitrixClient(log_path=config.LOG_PATH)

    print(f"\nОкно: последние {args.days} дн. {since.date()} .. {until.date()} (MSK)\n")
    print(f"{'Статус':<6}{'Менеджер':<22}{'Роль':<5}{'Наб':>4} {'Дзв':>4} {'Конв':>5} "
          f"{'Чаты':>4} {'Встр':>4} {'Опер':>4}")
    results = []
    for uid in args.user_ids:
        r = aggregate(bx, uid, since, until)
        results.append(r)
        print_row(r)
    for r in results:
        print_diag(r, since, until)
    return 0


if __name__ == "__main__":
    sys.exit(main())
