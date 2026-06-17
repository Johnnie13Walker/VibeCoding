"""HTML side-by-side comparison отчёт по двум менеджерам.

Запуск:
    python3 belberry/sales/scripts/manager_compare_html.py 2822 2806 \\
        --from 2026-03-12 \\
        --out /Users/pro2kuror/Desktop/VibeCoding/tmp/reports/compare_smirnov_vs_degovtsova.html
"""
from __future__ import annotations

import argparse
import html
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "belberry" / "bitrix24" / "sales_dashboard"))
sys.path.insert(0, str(REPO_ROOT / "belberry" / "sales" / "scripts"))

import manager_deep_stats as mds  # noqa: E402

from sales_dashboard.bitrix_client import BitrixClient  # noqa: E402
from sales_dashboard import config  # noqa: E402

MSK = config.MOSCOW_TZ
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def collect_all(bx, uid, since, until):
    u = mds.get_user(bx, uid)
    return {
        "user": u,
        "uid": uid,
        "calls": mds.collect_calls(bx, uid, since, until),
        "meets": mds.collect_smart(bx, 1048, 24, uid, since, until),
        "briefs": mds.collect_smart(bx, 1056, 28, uid, since, until),
        "deals": mds.collect_deals(bx, uid, since, until),
    }


def compute_summary(d, since, until, uid):
    """Свёрнутая структура для рендера."""
    days = (until - since).days
    workdays = sum(1 for i in range(days) if (since + timedelta(days=i)).weekday() < 5)
    c = d["calls"]
    by_stage_m = Counter(m["stageId"] for m in d["meets"])
    by_stage_b = Counter(b["stageId"] for b in d["briefs"])
    accepted = by_stage_b.get(mds.BRIEF_DONE, 0)
    rejected = by_stage_b.get(mds.BRIEF_FAIL, 0)
    ar = accepted / (accepted + rejected) * 100 if (accepted + rejected) else 0
    own_meets = sum(1 for m in d["meets"] if int(m.get("createdBy") or 0) == uid)
    own_briefs = sum(1 for b in d["briefs"] if int(b.get("createdBy") or 0) == uid)
    own_deals = sum(1 for x in d["deals"]["created"]
                    if int(x.get("CREATED_BY_ID") or 0) == uid)
    nab = c["nab"]
    doz = c["doz"]
    doz30 = c["doz30"]
    return {
        "name": f"{d['user'].get('LAST_NAME', '')} {d['user'].get('NAME', '')}".strip(),
        "uid": uid,
        "reg": d["user"].get("DATE_REGISTER"),
        "dept": d["user"].get("UF_DEPARTMENT"),
        "pos": d["user"].get("WORK_POSITION"),
        "last_login": d["user"].get("LAST_LOGIN"),
        "workdays": workdays,
        "nab": nab,
        "nab_per_day": nab / max(workdays, 1),
        "doz": doz,
        "conv": (doz / nab * 100) if nab else 0,
        "doz30": doz30,
        "conv30": (doz30 / nab * 100) if nab else 0,
        "talk_h": c["talk_total_sec"] / 3600,
        "med_talk": c["median_talk"],
        "in": c["in"],
        "miss": c["miss"],
        "miss_pct": (c["miss"] / max(c["in"], 1) * 100),
        "meets_total": len(d["meets"]),
        "meets_done": by_stage_m.get(mds.MEETING_DONE, 0),
        "meets_fail": by_stage_m.get(mds.MEETING_FAIL, 0),
        "meets_own": own_meets,
        "briefs_total": len(d["briefs"]),
        "briefs_done": accepted,
        "briefs_fail": rejected,
        "briefs_own": own_briefs,
        "ar": ar,
        "deals_created": len(d["deals"]["created"]),
        "deals_own": own_deals,
        "deals_won": len(d["deals"]["closed_won"]),
        "deals_won_amt": sum(float(x.get("OPPORTUNITY") or 0)
                             for x in d["deals"]["closed_won"]),
        "deals_lost": len(d["deals"]["closed_lost"]),
        "deals_lost_amt": sum(float(x.get("OPPORTUNITY") or 0)
                              for x in d["deals"]["closed_lost"]),
        "deals_active": len(d["deals"]["active"]),
        "deals_active_amt": sum(float(x.get("OPPORTUNITY") or 0)
                                for x in d["deals"]["active"]),
        "bymonth": c["bymonth"],
        "by_dow": c["by_dow"],
        "by_hour": c["by_hour"],
        "raw": d,
        "by_stage_m": by_stage_m,
        "by_stage_b": by_stage_b,
    }


def fmt_amt(v):
    try:
        return f"{float(v):,.0f}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def esc(s):
    return html.escape(str(s) if s is not None else "")


def cmp_class(a, b, higher_better=True):
    """Return CSS class for the better/worse cell."""
    if a == b:
        return "", ""
    if higher_better:
        return ("pos", "neg") if a > b else ("neg", "pos")
    return ("neg", "pos") if a > b else ("pos", "neg")


def render(s1, s2, since, until, stage_names) -> str:
    days = (until - since).days

    css = """
    :root {
      --bg: #0f1419; --panel: #1a2332; --border: #2a3a52;
      --fg: #e6e8eb; --muted: #8a9aae; --accent: #5eb3ff;
      --good: #4ade80; --warn: #fbbf24; --bad: #f87171;
      --bar: #5eb3ff; --bar-bg: #243248;
      --col-a: #5eb3ff; --col-b: #c084fc;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg);
                 font: 14px/1.45 -apple-system, BlinkMacSystemFont, "SF Pro Text", Segoe UI, system-ui, sans-serif; }
    .wrap { max-width: 1200px; margin: 0 auto; padding: 24px; }
    h1 { font-size: 24px; margin: 0 0 4px 0; font-weight: 600; }
    h2 { font-size: 16px; margin: 28px 0 12px 0; font-weight: 600; color: var(--accent);
         border-bottom: 1px solid var(--border); padding-bottom: 6px; letter-spacing: 0.3px; }
    h3 { font-size: 13px; margin: 16px 0 8px 0; font-weight: 600; color: var(--muted);
         text-transform: uppercase; letter-spacing: 0.5px; }
    .meta { color: var(--muted); font-size: 13px; margin-bottom: 4px; }
    .meta b { color: var(--fg); }
    .headers { display: grid; grid-template-columns: 280px 1fr 1fr; gap: 8px;
               margin: 16px 0; align-items: end; }
    .head-cell { padding: 10px 14px; border-radius: 6px; }
    .head-cell.a { background: rgba(94,179,255,0.08); border: 1px solid rgba(94,179,255,0.3); }
    .head-cell.b { background: rgba(192,132,252,0.08); border: 1px solid rgba(192,132,252,0.3); }
    .head-cell .name { font-size: 16px; font-weight: 600; }
    .head-cell.a .name { color: var(--col-a); }
    .head-cell.b .name { color: var(--col-b); }
    .head-cell .sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
    .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
            padding: 16px 18px; margin: 8px 0; }
    table { border-collapse: collapse; width: 100%; font-size: 13px; }
    th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); }
    th { font-weight: 600; font-size: 11px; color: var(--muted); text-transform: uppercase;
         letter-spacing: 0.4px; }
    td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
    th.col-a, td.col-a { background: rgba(94,179,255,0.04); }
    th.col-b, td.col-b { background: rgba(192,132,252,0.04); }
    .pos { color: var(--good); font-weight: 600; }
    .neg { color: var(--bad); font-weight: 600; }
    .warn { color: var(--warn); }
    .small { font-size: 12px; color: var(--muted); }
    .bar-row { display: grid; grid-template-columns: 45px 45px 1fr 1fr 45px;
               align-items: center; gap: 6px; margin: 3px 0;
               font-variant-numeric: tabular-nums; font-size: 12px; }
    .bar-row .lbl { color: var(--muted); }
    .bar-row .val { text-align: right; }
    .bar { height: 14px; background: var(--bar-bg); border-radius: 3px; overflow: hidden; }
    .bar.a > div { background: var(--col-a); height: 100%; }
    .bar.b > div { background: var(--col-b); height: 100%; }
    .footer { color: var(--muted); font-size: 11px; margin-top: 32px;
              border-top: 1px solid var(--border); padding-top: 12px; }
    code { background: var(--bar-bg); padding: 1px 6px; border-radius: 3px; font-size: 12px; }
    .badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 10px;
             font-weight: 600; letter-spacing: 0.3px; }
    .badge.norm { background: rgba(74,222,128,0.15); color: var(--good); }
    .badge.risk { background: rgba(251,191,36,0.15); color: var(--warn); }
    .badge.stop { background: rgba(248,113,113,0.15); color: var(--bad); }
    """

    parts = [f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Сравнение менеджеров — {esc(s1['name'])} vs {esc(s2['name'])}</title>
<style>{css}</style>
</head><body><div class="wrap">"""]

    parts.append(f"""
    <h1>Сравнение менеджеров</h1>
    <div class="meta">Окно: <b>{since.date()} — {until.date()}</b>
      ({days} календ. / ~{s1['workdays']} рабочих дней)</div>
    <div class="meta small">Окно выбрано так, чтобы оба менеджера были активны весь период (привязка к дате выхода новичка — Смирнова Ильи).</div>

    <div class="headers">
      <div></div>
      <div class="head-cell a">
        <div class="name">{esc(s1['name'])}</div>
        <div class="sub">ID {s1['uid']} · {esc(s1['pos'])} · dept {esc(s1['dept'])} · reg {esc(s1['reg'][:10] if s1['reg'] else '')}</div>
      </div>
      <div class="head-cell b">
        <div class="name">{esc(s2['name'])}</div>
        <div class="sub">ID {s2['uid']} · {esc(s2['pos'])} · dept {esc(s2['dept'])} · reg {esc(s2['reg'][:10] if s2['reg'] else '')}</div>
      </div>
    </div>
    """)

    # Big compare table
    rows = [
        ("Звонки",       None, None, None, True),
        ("  Наборов всего",          s1['nab'],          s2['nab'],          'int', True),
        ("  Наборов / раб. день",    s1['nab_per_day'],  s2['nab_per_day'],  'f1',  True),
        ("  Дозвонов",                s1['doz'],          s2['doz'],          'int', True),
        ("  Конверсия дозвона",       s1['conv'],         s2['conv'],         'pct', True),
        ("  Разговоров ≥30 сек",      s1['doz30'],        s2['doz30'],        'int', True),
        ("  % реальных разговоров",   s1['conv30'],       s2['conv30'],       'pct', True),
        ("  Talk-time, ч",            s1['talk_h'],       s2['talk_h'],       'f1',  True),
        ("  Медиана разговора, сек",  s1['med_talk'],     s2['med_talk'],     'int', True),
        ("Входящие",     None, None, None, True),
        ("  Всего входящих",          s1['in'],           s2['in'],           'int', True),
        ("  Пропущено",                s1['miss'],         s2['miss'],         'int', False),
        ("  % пропусков",              s1['miss_pct'],     s2['miss_pct'],     'pct', False),
        ("Встречи (smart 1048/24)",     None, None, None, True),
        ("  Всего активностей",       s1['meets_total'],  s2['meets_total'],  'int', True),
        ("  Проведено (SUCCESS)",      s1['meets_done'],   s2['meets_done'],   'int', True),
        ("  Отменено (FAIL)",          s1['meets_fail'],   s2['meets_fail'],   'int', False),
        ("  Создал сам",               s1['meets_own'],    s2['meets_own'],    'int', True),
        ("Брифы (smart 1056/28)",       None, None, None, True),
        ("  Всего активностей",       s1['briefs_total'], s2['briefs_total'], 'int', True),
        ("  Принято производством",   s1['briefs_done'],  s2['briefs_done'],  'int', True),
        ("  Отклонено",                s1['briefs_fail'],  s2['briefs_fail'],  'int', False),
        ("  Accept-rate",              s1['ar'],           s2['ar'],           'pct', True),
        ("  Создал сам",               s1['briefs_own'],   s2['briefs_own'],   'int', True),
        ("Сделки (cat 10)",             None, None, None, True),
        ("  Создано в окне",           s1['deals_created'],s2['deals_created'],'int', True),
        ("  Из них он автор",          s1['deals_own'],    s2['deals_own'],    'int', True),
        ("  WON, шт",                  s1['deals_won'],    s2['deals_won'],    'int', True),
        ("  WON, ₽",                   s1['deals_won_amt'],s2['deals_won_amt'],'rub', True),
        ("  LOST, шт",                 s1['deals_lost'],   s2['deals_lost'],   'int', False),
        ("  LOST, ₽",                  s1['deals_lost_amt'],s2['deals_lost_amt'],'rub', False),
        ("  Активных сейчас, шт",      s1['deals_active'], s2['deals_active'], 'int', True),
        ("  Активных сейчас, ₽",       s1['deals_active_amt'],s2['deals_active_amt'],'rub', True),
    ]

    parts.append('<h2>Сводная таблица</h2>')
    parts.append('<div class="card"><table><thead><tr>'
                 '<th>Метрика</th>'
                 f'<th class="num col-a">{esc(s1["name"].split()[0])}</th>'
                 f'<th class="num col-b">{esc(s2["name"].split()[0])}</th>'
                 '<th class="num">Δ (% разница)</th>'
                 '</tr></thead><tbody>')
    for row in rows:
        if row[1] is None and row[2] is None:
            parts.append(f'<tr style="background:rgba(94,179,255,0.03)"><td colspan="4">'
                         f'<b>{esc(row[0])}</b></td></tr>')
            continue
        label, v1, v2, kind, higher_better = row
        ca, cb = cmp_class(v1, v2, higher_better)

        if kind == 'int':
            d1 = f"{int(v1)}"
            d2 = f"{int(v2)}"
        elif kind == 'f1':
            d1 = f"{v1:.1f}"
            d2 = f"{v2:.1f}"
        elif kind == 'pct':
            d1 = f"{v1:.0f}%"
            d2 = f"{v2:.0f}%"
        elif kind == 'rub':
            d1 = f"{fmt_amt(v1)} ₽"
            d2 = f"{fmt_amt(v2)} ₽"
        else:
            d1, d2 = str(v1), str(v2)

        # Δ % (relative)
        if v1 == 0 and v2 == 0:
            delta_s = "—"
        elif v1 == 0:
            delta_s = "∞"
        else:
            delta = (v2 - v1) / abs(v1) * 100
            sign = "+" if delta >= 0 else ""
            delta_s = f"{sign}{delta:.0f}%"
        parts.append(f'<tr><td>{esc(label)}</td>'
                     f'<td class="num col-a {ca}">{d1}</td>'
                     f'<td class="num col-b {cb}">{d2}</td>'
                     f'<td class="num small">{delta_s}</td></tr>')
    parts.append('</tbody></table></div>')

    # By-month
    parts.append('<h2>Помесячная динамика звонков</h2>')
    months = sorted(set(list(s1['bymonth'].keys()) + list(s2['bymonth'].keys())))
    parts.append('<div class="card"><table><thead><tr>'
                 '<th>Месяц</th>'
                 f'<th class="num col-a" colspan="3">{esc(s1["name"].split()[0])}: Наб / Дзв / Конв</th>'
                 f'<th class="num col-b" colspan="3">{esc(s2["name"].split()[0])}: Наб / Дзв / Конв</th>'
                 '</tr></thead><tbody>')
    for k in months:
        m1 = s1['bymonth'].get(k, {"nab": 0, "doz": 0, "doz30s": 0, "in": 0, "miss": 0})
        m2 = s2['bymonth'].get(k, {"nab": 0, "doz": 0, "doz30s": 0, "in": 0, "miss": 0})
        c1 = m1['doz'] / m1['nab'] * 100 if m1['nab'] else 0
        c2 = m2['doz'] / m2['nab'] * 100 if m2['nab'] else 0
        parts.append(f'<tr><td>{k}</td>'
                     f'<td class="num col-a">{m1["nab"]}</td>'
                     f'<td class="num col-a">{m1["doz"]}</td>'
                     f'<td class="num col-a">{c1:.0f}%</td>'
                     f'<td class="num col-b">{m2["nab"]}</td>'
                     f'<td class="num col-b">{m2["doz"]}</td>'
                     f'<td class="num col-b">{c2:.0f}%</td>'
                     '</tr>')
    parts.append('</tbody></table></div>')

    # By DOW
    dow_max = max([s["nab"] for s in s1['by_dow'].values()] +
                  [s["nab"] for s in s2['by_dow'].values()] + [1])
    parts.append('<h2>Рабочий ритм</h2>')
    parts.append('<div class="card"><h3>Наборы по дням недели</h3>')
    for d in range(7):
        s1d = s1['by_dow'].get(d, {"nab": 0})
        s2d = s2['by_dow'].get(d, {"nab": 0})
        p1 = s1d['nab'] / dow_max * 100
        p2 = s2d['nab'] / dow_max * 100
        parts.append(f'<div class="bar-row">'
                     f'<div class="lbl">{WEEKDAYS[d]}</div>'
                     f'<div class="val">{s1d["nab"]}</div>'
                     f'<div class="bar a"><div style="width: {p1:.1f}%"></div></div>'
                     f'<div class="bar b"><div style="width: {p2:.1f}%"></div></div>'
                     f'<div class="val">{s2d["nab"]}</div>'
                     f'</div>')
    parts.append('</div>')

    # By hour
    hour_max = max(list(s1['by_hour'].values()) + list(s2['by_hour'].values()) + [1])
    all_hours = sorted(set(list(s1['by_hour'].keys()) + list(s2['by_hour'].keys())))
    parts.append('<div class="card"><h3>Наборы по часам (МСК)</h3>')
    for h in all_hours:
        n1 = s1['by_hour'].get(h, 0)
        n2 = s2['by_hour'].get(h, 0)
        p1 = n1 / hour_max * 100
        p2 = n2 / hour_max * 100
        parts.append(f'<div class="bar-row">'
                     f'<div class="lbl">{h:02d}:00</div>'
                     f'<div class="val">{n1}</div>'
                     f'<div class="bar a"><div style="width: {p1:.1f}%"></div></div>'
                     f'<div class="bar b"><div style="width: {p2:.1f}%"></div></div>'
                     f'<div class="val">{n2}</div>'
                     f'</div>')
    parts.append('</div>')

    # Top losses for each
    parts.append('<h2>Топ потерь по чеку (LOST в окне)</h2>')
    parts.append('<div class="card"><table><thead><tr><th>Кто</th><th>ID</th>'
                 '<th class="num">Сумма</th><th>Стадия</th><th>Клиент</th>'
                 '</tr></thead><tbody>')
    losses = []
    for s, klass in [(s1, 'col-a'), (s2, 'col-b')]:
        for d in s['raw']['deals']['closed_lost']:
            losses.append((klass, s['name'].split()[0], d))
    losses.sort(key=lambda x: -float(x[2].get('OPPORTUNITY') or 0))
    for klass, who, d in losses[:20]:
        st = d.get('STAGE_ID', '')
        stage_lbl = stage_names.get(st, st)
        cls = 'neg' if 'ОТВАЛ' in stage_lbl.upper() else 'warn'
        parts.append(f'<tr><td class="{klass}">{esc(who)}</td>'
                     f'<td>{esc(d["ID"])}</td>'
                     f'<td class="num">{fmt_amt(d.get("OPPORTUNITY"))} ₽</td>'
                     f'<td class="{cls}">{esc(stage_lbl)}</td>'
                     f'<td>{esc((d.get("TITLE") or "")[:55])}</td></tr>')
    parts.append('</tbody></table></div>')

    # Interpretation block
    parts.append('<h2>Что говорит сравнение</h2>')
    parts.append('<div class="card">')
    parts.append(_render_interpretation(s1, s2))
    parts.append('</div>')

    parts.append(f"""
    <div class="footer">
      Сгенерировано {datetime.now(MSK).strftime("%Y-%m-%d %H:%M:%S")} МСК ·
      Источник: Bitrix24 ({config.PORTAL_DOMAIN}) ·
      <code>belberry/sales/scripts/manager_compare_html.py</code>
    </div>
    """)
    parts.append('</div></body></html>')
    return "".join(parts)


def _render_interpretation(s1, s2):
    """Авто-генерируем текстовый разбор по ключевым метрикам."""
    n1, n2 = s1['name'].split()[0], s2['name'].split()[0]
    out = ["<ul>"]

    # Volume
    if s1['nab'] > s2['nab']:
        ratio = s1['nab'] / max(s2['nab'], 1)
        out.append(f"<li><b>Объём обзвона:</b> {n1} превосходит {n2} в {ratio:.1f}x "
                   f"({s1['nab']} vs {s2['nab']} наборов). "
                   f"В пересчёте на рабочий день: {s1['nab_per_day']:.1f} vs {s2['nab_per_day']:.1f}.</li>")
    else:
        ratio = s2['nab'] / max(s1['nab'], 1)
        out.append(f"<li><b>Объём обзвона:</b> {n2} превосходит {n1} в {ratio:.1f}x "
                   f"({s2['nab']} vs {s1['nab']} наборов). "
                   f"В пересчёте на день: {s2['nab_per_day']:.1f} vs {s1['nab_per_day']:.1f}.</li>")

    # Conversion quality
    diff_conv = s1['conv'] - s2['conv']
    if abs(diff_conv) > 5:
        better = n1 if diff_conv > 0 else n2
        out.append(f"<li><b>Качество дозвона:</b> у {better} конверсия выше на "
                   f"{abs(diff_conv):.0f} п.п. ({s1['conv']:.0f}% vs {s2['conv']:.0f}%). "
                   f"Но смотреть нужно на «реальные разговоры ≥30 сек»: "
                   f"{s1['conv30']:.0f}% vs {s2['conv30']:.0f}%.</li>")

    # Missed incoming
    if s1['miss_pct'] > 40 or s2['miss_pct'] > 40:
        worst = n1 if s1['miss_pct'] > s2['miss_pct'] else n2
        worst_pct = max(s1['miss_pct'], s2['miss_pct'])
        out.append(f"<li><span class='badge stop'>КРИТ</span> <b>Входящие:</b> "
                   f"{worst} теряет {worst_pct:.0f}% входящих "
                   f"({n1}: {s1['miss']}/{s1['in']}, {n2}: {s2['miss']}/{s2['in']}). "
                   f"Это потерянные горячие лиды.</li>")

    # Briefs (production-accepted)
    if s1['briefs_done'] != s2['briefs_done']:
        better = n1 if s1['briefs_done'] > s2['briefs_done'] else n2
        out.append(f"<li><b>Воронка брифов:</b> у {better} больше принятых "
                   f"производством ({s1['briefs_done']} vs {s2['briefs_done']}). "
                   f"Accept-rate: {s1['ar']:.0f}% vs {s2['ar']:.0f}% — это говорит о "
                   f"качестве квалификации клиента.</li>")

    # Wins
    if s1['deals_won'] == 0 and s2['deals_won'] == 0:
        out.append(f"<li><span class='badge stop'>0 WIN</span> <b>Сделки cat.10:</b> "
                   f"у обоих 0 побед при {s1['deals_lost']} и {s2['deals_lost']} "
                   f"потерях. Closer-навыки не работают у обоих, либо «победы» "
                   f"уходят через smart-процесс брифов, а cat.10 это «черновики».</li>")
    elif s1['deals_won'] > s2['deals_won']:
        out.append(f"<li><b>WIN-сделки:</b> {n1} закрыл {s1['deals_won']} на "
                   f"{fmt_amt(s1['deals_won_amt'])} ₽, {n2} — {s2['deals_won']} на "
                   f"{fmt_amt(s2['deals_won_amt'])} ₽.</li>")
    else:
        out.append(f"<li><b>WIN-сделки:</b> {n2} закрыл {s2['deals_won']} на "
                   f"{fmt_amt(s2['deals_won_amt'])} ₽, {n1} — {s1['deals_won']} на "
                   f"{fmt_amt(s1['deals_won_amt'])} ₽.</li>")

    # Losses
    if s1['deals_lost_amt'] > s2['deals_lost_amt']:
        out.append(f"<li><b>Объём потерь:</b> {n1} потерял на {fmt_amt(s1['deals_lost_amt'])} ₽ "
                   f"({s1['deals_lost']} сделок) против {fmt_amt(s2['deals_lost_amt'])} ₽ "
                   f"({s2['deals_lost']}) у {n2}. У {n1} цикл интенсивнее, но «протекает».</li>")
    elif s2['deals_lost_amt'] > s1['deals_lost_amt']:
        out.append(f"<li><b>Объём потерь:</b> {n2} потерял на {fmt_amt(s2['deals_lost_amt'])} ₽ "
                   f"({s2['deals_lost']} сделок) против {fmt_amt(s1['deals_lost_amt'])} ₽ "
                   f"({s1['deals_lost']}) у {n1}.</li>")

    # Active pipeline
    if s1['deals_active_amt'] > s2['deals_active_amt']:
        out.append(f"<li><b>Активный пайплайн:</b> у {n1} больше потенциала "
                   f"({fmt_amt(s1['deals_active_amt'])} ₽ vs {fmt_amt(s2['deals_active_amt'])} ₽).</li>")
    elif s2['deals_active_amt'] > s1['deals_active_amt']:
        out.append(f"<li><b>Активный пайплайн:</b> у {n2} больше потенциала "
                   f"({fmt_amt(s2['deals_active_amt'])} ₽ vs {fmt_amt(s1['deals_active_amt'])} ₽).</li>")

    # Self-authored work
    if s1['briefs_total']:
        s1_self_ratio = s1['briefs_own'] / s1['briefs_total'] * 100
    else:
        s1_self_ratio = 0
    if s2['briefs_total']:
        s2_self_ratio = s2['briefs_own'] / s2['briefs_total'] * 100
    else:
        s2_self_ratio = 0
    out.append(f"<li><b>Свой vs переданный поток брифов:</b> "
               f"{n1} сам автор {s1_self_ratio:.0f}% ({s1['briefs_own']}/{s1['briefs_total']}), "
               f"{n2} — {s2_self_ratio:.0f}% ({s2['briefs_own']}/{s2['briefs_total']}). "
               f"Чем выше доля «своих», тем чище метрика воронки.</li>")

    out.append("</ul>")
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uid_a", type=int)
    ap.add_argument("uid_b", type=int)
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    bx = BitrixClient(log_path=config.LOG_PATH)
    since = datetime.fromisoformat(args.start).replace(tzinfo=MSK)
    until = datetime.now(MSK).replace(microsecond=0)

    da = collect_all(bx, args.uid_a, since, until)
    db = collect_all(bx, args.uid_b, since, until)
    sa = compute_summary(da, since, until, args.uid_a)
    sb = compute_summary(db, since, until, args.uid_b)
    stage_names = mds.collect_stages(bx)

    out = render(sa, sb, since, until, stage_names)
    Path(args.out).write_text(out, encoding="utf-8")
    print(f"Written: {args.out}  ({len(out):,} bytes)")


if __name__ == "__main__":
    main()
