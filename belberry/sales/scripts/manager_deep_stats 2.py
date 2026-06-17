"""Глубокая аналитика по одному менеджеру за весь период работы.

Берёт DATE_REGISTER как старт и тянет:
  * звонки помесячно/понедельно: объём, конверсия, среднее за день
  * входящие: пропущено vs принято
  * рабочий ритм: распределение по часам и дням недели
  * встречи проведены / брифы принято — кумулятивно и помесячно
  * деалы: создано (КЕМ — он сам или назначили), выиграно/проиграно, причины
  * брифы: кем созданы (CREATED_BY vs ASSIGNED_BY), accept-rate
  * активный пайплайн: возраст сделок, распределение по стадиям

Запуск:
    python3 belberry/sales/scripts/manager_deep_stats.py 2822
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "belberry" / "bitrix24" / "sales_dashboard"))

from sales_dashboard.bitrix_client import BitrixClient  # noqa: E402
from sales_dashboard import config  # noqa: E402

MSK = config.MOSCOW_TZ
MEETING_DONE = "DT1048_24:SUCCESS"
MEETING_FAIL = "DT1048_24:FAIL"
BRIEF_DONE = "DT1056_28:SUCCESS"
BRIEF_FAIL = "DT1056_28:FAIL"

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def fmt(dt: datetime) -> str:
    return dt.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S")


def parse(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(MSK)
    except (ValueError, AttributeError):
        return None


def get_user(bx: BitrixClient, uid: int) -> dict:
    body = bx.call("user.get", {"FILTER": {"ID": uid}, "ADMIN_MODE": "Y"})
    return (body.get("result") or [{}])[0]


def collect_calls(bx, uid, since, until):
    bymonth = defaultdict(lambda: {"nab": 0, "doz": 0, "doz30s": 0, "in": 0, "miss": 0})
    by_dow = defaultdict(lambda: {"nab": 0, "doz": 0})
    by_hour = defaultdict(int)
    talk_total = 0
    durations = []
    out_nab = out_doz = out_doz30 = 0
    in_total = in_miss = 0
    for c in bx.paginate_by_start(
        "voximplant.statistic.get",
        {"filter": {">=CALL_START_DATE": fmt(since), "<CALL_START_DATE": fmt(until),
                    "PORTAL_USER_ID": uid},
         "sort": "CALL_START_DATE", "order": "ASC"},
    ):
        ct = str(c.get("CALL_TYPE") or "")
        dur = int(c.get("CALL_DURATION") or 0)
        code = str(c.get("CALL_FAILED_CODE") or "")
        dt = parse(c.get("CALL_START_DATE"))
        if dt is None:
            continue
        m_key = dt.strftime("%Y-%m")
        if ct == "1":
            bymonth[m_key]["nab"] += 1
            by_dow[dt.weekday()]["nab"] += 1
            by_hour[dt.hour] += 1
            out_nab += 1
            if code == "200" and dur > 0:
                out_doz += 1
                bymonth[m_key]["doz"] += 1
                by_dow[dt.weekday()]["doz"] += 1
                durations.append(dur)
                talk_total += dur
                if dur >= 30:
                    out_doz30 += 1
                    bymonth[m_key]["doz30s"] += 1
        elif ct in ("2", "4"):
            in_total += 1
            bymonth[m_key]["in"] += 1
            if code != "200" or dur <= 0:
                in_miss += 1
                bymonth[m_key]["miss"] += 1
        elif ct == "3":
            in_total += 1
            in_miss += 1
            bymonth[m_key]["in"] += 1
            bymonth[m_key]["miss"] += 1
    durations.sort()
    median = durations[len(durations) // 2] if durations else 0
    return {
        "nab": out_nab, "doz": out_doz, "doz30": out_doz30,
        "in": in_total, "miss": in_miss,
        "talk_total_sec": talk_total, "median_talk": median,
        "bymonth": dict(bymonth), "by_dow": dict(by_dow), "by_hour": dict(by_hour),
    }


def collect_smart(bx, entity_type_id, category_id, uid, since, until):
    """Все item-ы по менеджеру: смотрим стадии, кто создал, обновления."""
    items = []
    start = 0
    flt = {
        "entityTypeId": entity_type_id,
        "filter": {
            "categoryId": category_id,
            "@assignedById": [uid],
            ">=createdTime": fmt(since),
            "<createdTime": fmt(until),
        },
        "select": ["id", "title", "stageId", "createdBy", "assignedById",
                   "createdTime", "updatedTime"],
    }
    while True:
        p = dict(flt)
        p["start"] = start
        body = bx.call("crm.item.list", p)
        result = body.get("result") or {}
        chunk = result.get("items") or []
        items.extend(chunk)
        nxt = body.get("next")
        if nxt is None or not chunk:
            break
        start = int(nxt)
    # also items assigned to him but created elsewhere & updated in window
    start = 0
    flt2 = {
        "entityTypeId": entity_type_id,
        "filter": {
            "categoryId": category_id,
            "@assignedById": [uid],
            ">=updatedTime": fmt(since),
            "<updatedTime": fmt(until),
        },
        "select": ["id", "title", "stageId", "createdBy", "assignedById",
                   "createdTime", "updatedTime"],
    }
    seen = {it["id"] for it in items}
    while True:
        p = dict(flt2)
        p["start"] = start
        body = bx.call("crm.item.list", p)
        result = body.get("result") or {}
        chunk = result.get("items") or []
        for it in chunk:
            if it["id"] not in seen:
                items.append(it)
                seen.add(it["id"])
        nxt = body.get("next")
        if nxt is None or not chunk:
            break
        start = int(nxt)
    return items


def collect_deals(bx, uid, since, until):
    """Сделки cat 10, привязанные к менеджеру (created in window OR closed in window)."""
    out = {"created": [], "closed_won": [], "closed_lost": [], "active": []}
    seen = set()
    for d in bx.paginate(
        "crm.deal.list",
        {"filter": {"ASSIGNED_BY_ID": uid, "CATEGORY_ID": 10,
                    ">=DATE_CREATE": fmt(since), "<DATE_CREATE": fmt(until)},
         "select": ["ID", "TITLE", "STAGE_ID", "STAGE_SEMANTIC_ID", "OPPORTUNITY",
                    "CURRENCY_ID", "DATE_CREATE", "CLOSEDATE", "CLOSED", "CREATED_BY_ID"]},
    ):
        if d["ID"] in seen:
            continue
        seen.add(d["ID"])
        out["created"].append(d)
    for d in bx.paginate(
        "crm.deal.list",
        {"filter": {"ASSIGNED_BY_ID": uid, "CATEGORY_ID": 10, "CLOSED": "Y",
                    ">=CLOSEDATE": fmt(since), "<CLOSEDATE": fmt(until)},
         "select": ["ID", "TITLE", "STAGE_ID", "STAGE_SEMANTIC_ID", "OPPORTUNITY",
                    "CURRENCY_ID", "DATE_CREATE", "CLOSEDATE", "CLOSED", "CREATED_BY_ID"]},
    ):
        if d["ID"] in seen:
            continue
        seen.add(d["ID"])
        sem = d.get("STAGE_SEMANTIC_ID")
        if sem == "S":
            out["closed_won"].append(d)
        elif sem == "F":
            out["closed_lost"].append(d)
    # current active
    for d in bx.paginate(
        "crm.deal.list",
        {"filter": {"ASSIGNED_BY_ID": uid, "CATEGORY_ID": 10, "CLOSED": "N"},
         "select": ["ID", "TITLE", "STAGE_ID", "STAGE_SEMANTIC_ID", "OPPORTUNITY",
                    "CURRENCY_ID", "DATE_CREATE", "DATE_MODIFY", "CREATED_BY_ID"]},
    ):
        out["active"].append(d)
    return out


def collect_stages(bx):
    body = bx.call("crm.dealcategory.stage.list", {"id": 10})
    return {s["STATUS_ID"]: s.get("NAME", "") for s in body.get("result") or []}


def print_report(uid, u, since, until, calls, meets, briefs, deals, stage_names):
    name = f"{u.get('LAST_NAME', '')} {u.get('NAME', '')}".strip()
    days = (until - since).days
    workdays = sum(1 for i in range(days) if (since + timedelta(days=i)).weekday() < 5)

    print(f"\n{'='*70}")
    print(f"  ГЛУБОКИЙ ОТЧЁТ — {name} (ID={uid})")
    print(f"  Период: {since.date()} .. {until.date()}  ({days} календ. / ~{workdays} рабочих дней)")
    print(f"  Реги в Bitrix: {u.get('DATE_REGISTER')}")
    print(f"  Должность: {u.get('WORK_POSITION')} | dept {u.get('UF_DEPARTMENT')}")
    print(f"  Последний логин: {u.get('LAST_LOGIN')}")
    print(f"{'='*70}\n")

    # Звонки
    nab, doz, doz30 = calls["nab"], calls["doz"], calls["doz30"]
    conv = doz / nab * 100 if nab else 0
    conv30 = doz30 / nab * 100 if nab else 0
    print("ЗВОНКИ (исходящие)")
    print(f"  Набрано     : {nab}  (~{nab / max(workdays, 1):.1f} / раб. день)")
    print(f"  Дозвонились : {doz} ({conv:.0f}%)")
    print(f"  Реальный разговор ≥30 сек : {doz30} ({conv30:.0f}% от наборов)")
    print(f"  Суммарный talk-time : {calls['talk_total_sec'] / 3600:.1f} ч  | медианная длительность: {calls['median_talk']} сек")

    print("\nВХОДЯЩИЕ")
    print(f"  Всего входящих: {calls['in']} | пропущено: {calls['miss']} "
          f"({calls['miss'] / max(calls['in'], 1) * 100:.0f}%)")

    print("\nПОМЕСЯЧНАЯ ДИНАМИКА")
    print(f"  {'Месяц':<10}{'Наб':>5}{'Дзв':>5}{'Конв':>6}{'Дзв30':>7}{'ВхВ':>5}{'Пропущ':>8}")
    for k in sorted(calls["bymonth"].keys()):
        m = calls["bymonth"][k]
        c = m["doz"] / m["nab"] * 100 if m["nab"] else 0
        print(f"  {k:<10}{m['nab']:>5}{m['doz']:>5}{c:>5.0f}%{m['doz30s']:>7}{m['in']:>5}{m['miss']:>8}")

    print("\nРАБОЧИЙ РИТМ — наборы по дням недели")
    for d in range(7):
        s = calls["by_dow"].get(d, {"nab": 0, "doz": 0})
        bar = "█" * min(s["nab"] // 10, 30)
        print(f"  {WEEKDAYS[d]:<3} {s['nab']:>4}  {bar}")

    print("\nРАБОЧИЙ РИТМ — наборы по часам (МСК)")
    peak_hours = sorted(calls["by_hour"].items())
    for h, n in peak_hours:
        bar = "█" * min(n // 5, 40)
        print(f"  {h:02d}:00  {n:>4}  {bar}")

    # Встречи
    print("\nВСТРЕЧИ (smart-process 1048 / cat 24)")
    print(f"  всего активностей: {len(meets)}")
    by_stage_m = Counter(m["stageId"] for m in meets)
    for st, n in by_stage_m.most_common():
        print(f"  {st:<25} {n}")
    own_meets = sum(1 for m in meets if int(m.get("createdBy") or 0) == uid)
    print(f"  созданы им самим : {own_meets}  | переданы ему: {len(meets) - own_meets}")

    # Брифы
    print("\nБРИФЫ (smart-process 1056 / cat 28)")
    print(f"  всего активностей: {len(briefs)}")
    by_stage_b = Counter(b["stageId"] for b in briefs)
    for st, n in by_stage_b.most_common():
        print(f"  {st:<25} {n}")
    accepted = by_stage_b.get(BRIEF_DONE, 0)
    rejected = by_stage_b.get(BRIEF_FAIL, 0)
    if accepted + rejected:
        ar = accepted / (accepted + rejected) * 100
        print(f"  accept-rate (S vs F): {ar:.0f}%  ({accepted} / {accepted + rejected})")
    own_briefs = sum(1 for b in briefs if int(b.get("createdBy") or 0) == uid)
    print(f"  созданы им самим : {own_briefs}  | переданы ему: {len(briefs) - own_briefs}")

    # Сделки
    print("\nСДЕЛКИ (cat 10, sales-воронка)")
    created = deals["created"]
    won = deals["closed_won"]
    lost = deals["closed_lost"]
    active = deals["active"]

    won_amt = sum(float(d.get("OPPORTUNITY") or 0) for d in won)
    lost_amt = sum(float(d.get("OPPORTUNITY") or 0) for d in lost)
    act_amt = sum(float(d.get("OPPORTUNITY") or 0) for d in active)

    print(f"  Создано в окне: {len(created)}")
    print(f"  Закрыто WON  : {len(won)}  / {won_amt:,.0f} ₽")
    print(f"  Закрыто LOST : {len(lost)} / {lost_amt:,.0f} ₽")
    print(f"  Активных сейчас: {len(active)} / {act_amt:,.0f} ₽")
    if created:
        own_d = sum(1 for d in created if int(d.get("CREATED_BY_ID") or 0) == uid)
        print(f"  Из созданных в окне — он сам автор: {own_d} / {len(created)}")

    if lost:
        print("\n  ТОП потерь по чеку:")
        lost_sorted = sorted(lost, key=lambda d: float(d.get("OPPORTUNITY") or 0), reverse=True)
        for d in lost_sorted[:10]:
            stage_id = d.get("STAGE_ID", "")
            stage_lbl = stage_names.get(stage_id, stage_id)
            print(f"    {d['ID']:>6}  {float(d.get('OPPORTUNITY') or 0):>12,.0f} ₽  "
                  f"[{stage_lbl[:30]:<30}]  {(d.get('TITLE') or '')[:40]}")

    if active:
        now = datetime.now(MSK)
        print("\n  АКТИВНЫЕ — распределение по стадиям и возраст:")
        by_st_a = defaultdict(lambda: {"n": 0, "amt": 0.0, "ages": []})
        for d in active:
            st = d.get("STAGE_ID", "")
            by_st_a[st]["n"] += 1
            by_st_a[st]["amt"] += float(d.get("OPPORTUNITY") or 0)
            dc = parse(d.get("DATE_CREATE"))
            if dc:
                by_st_a[st]["ages"].append((now - dc).days)
        for st, v in sorted(by_st_a.items(), key=lambda kv: -kv[1]["amt"]):
            avg_age = sum(v["ages"]) / max(len(v["ages"]), 1)
            stage_lbl = stage_names.get(st, st)
            print(f"    [{stage_lbl[:30]:<30}] {v['n']:>3} шт  {v['amt']:>12,.0f} ₽  "
                  f"ср.возраст {avg_age:.0f} дн")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("user_id", type=int)
    ap.add_argument("--from", dest="start", help="override start (YYYY-MM-DD)")
    args = ap.parse_args()

    bx = BitrixClient(log_path=config.LOG_PATH)
    u = get_user(bx, args.user_id)
    until = datetime.now(MSK).replace(microsecond=0)
    if args.start:
        since = datetime.fromisoformat(args.start).replace(tzinfo=MSK)
    else:
        # take DATE_REGISTER
        ds = u.get("DATE_REGISTER")
        since = parse(ds) or (until - timedelta(days=365))

    calls = collect_calls(bx, args.user_id, since, until)
    meets = collect_smart(bx, 1048, 24, args.user_id, since, until)
    briefs = collect_smart(bx, 1056, 28, args.user_id, since, until)
    deals = collect_deals(bx, args.user_id, since, until)
    stage_names = collect_stages(bx)

    print_report(args.user_id, u, since, until, calls, meets, briefs, deals, stage_names)


if __name__ == "__main__":
    main()
