"""HTML-рендер глубокого отчёта по менеджеру (без блока «Резюме для РОПа»).

Запуск:
    python3 belberry/sales/scripts/manager_deep_stats_html.py 2822 \\
        --out /Users/pro2kuror/Desktop/VibeCoding/tmp/reports/smirnov_ilya.html
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

# Re-use the data collection from deep_stats (same dir)
sys.path.insert(0, str(REPO_ROOT / "belberry" / "sales" / "scripts"))
import manager_deep_stats as mds  # noqa: E402

from sales_dashboard.bitrix_client import BitrixClient  # noqa: E402
from sales_dashboard import config  # noqa: E402

MSK = config.MOSCOW_TZ
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def render(uid, u, since, until, calls, meets, briefs, deals, stage_names) -> str:
    name = f"{u.get('LAST_NAME', '')} {u.get('NAME', '')}".strip()
    days = (until - since).days
    workdays = sum(1 for i in range(days) if (since + timedelta(days=i)).weekday() < 5)

    nab, doz, doz30 = calls["nab"], calls["doz"], calls["doz30"]
    conv = doz / nab * 100 if nab else 0
    conv30 = doz30 / nab * 100 if nab else 0

    months = sorted(calls["bymonth"].keys())
    month_max = max((m["nab"] for m in calls["bymonth"].values()), default=0) or 1
    dow_max = max((s["nab"] for s in calls["by_dow"].values()), default=0) or 1
    hour_max = max(calls["by_hour"].values(), default=0) or 1

    # meetings / briefs
    by_stage_m = Counter(m["stageId"] for m in meets)
    own_meets = sum(1 for m in meets if int(m.get("createdBy") or 0) == uid)
    by_stage_b = Counter(b["stageId"] for b in briefs)
    own_briefs = sum(1 for b in briefs if int(b.get("createdBy") or 0) == uid)
    accepted = by_stage_b.get(mds.BRIEF_DONE, 0)
    rejected = by_stage_b.get(mds.BRIEF_FAIL, 0)
    ar = accepted / (accepted + rejected) * 100 if (accepted + rejected) else 0

    # deals
    created = deals["created"]
    won = deals["closed_won"]
    lost = deals["closed_lost"]
    active = deals["active"]
    won_amt = sum(float(d.get("OPPORTUNITY") or 0) for d in won)
    lost_amt = sum(float(d.get("OPPORTUNITY") or 0) for d in lost)
    act_amt = sum(float(d.get("OPPORTUNITY") or 0) for d in active)
    own_d = sum(1 for d in created if int(d.get("CREATED_BY_ID") or 0) == uid)

    lost_sorted = sorted(lost, key=lambda d: float(d.get("OPPORTUNITY") or 0), reverse=True)
    now = datetime.now(MSK)
    by_st_a = defaultdict(lambda: {"n": 0, "amt": 0.0, "ages": []})
    for d in active:
        st = d.get("STAGE_ID", "")
        by_st_a[st]["n"] += 1
        by_st_a[st]["amt"] += float(d.get("OPPORTUNITY") or 0)
        dc = mds.parse(d.get("DATE_CREATE"))
        if dc:
            by_st_a[st]["ages"].append((now - dc).days)

    def esc(s):
        return html.escape(str(s) if s is not None else "")

    def fmt_amt(v):
        try:
            return f"{float(v):,.0f}".replace(",", " ")
        except (ValueError, TypeError):
            return "0"

    css = """
    :root {
      --bg: #0f1419; --panel: #1a2332; --border: #2a3a52;
      --fg: #e6e8eb; --muted: #8a9aae; --accent: #5eb3ff;
      --good: #4ade80; --warn: #fbbf24; --bad: #f87171;
      --bar: #5eb3ff; --bar-bg: #243248;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg);
                 font: 14px/1.45 -apple-system, BlinkMacSystemFont, "SF Pro Text", Segoe UI, system-ui, sans-serif; }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 24px; }
    h1 { font-size: 24px; margin: 0 0 4px 0; font-weight: 600; }
    h2 { font-size: 16px; margin: 28px 0 12px 0; font-weight: 600; color: var(--accent);
         border-bottom: 1px solid var(--border); padding-bottom: 6px; letter-spacing: 0.3px; }
    h3 { font-size: 13px; margin: 16px 0 8px 0; font-weight: 600; color: var(--muted);
         text-transform: uppercase; letter-spacing: 0.5px; }
    .meta { color: var(--muted); font-size: 13px; margin-bottom: 4px; }
    .meta b { color: var(--fg); }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
             font-weight: 600; letter-spacing: 0.3px; margin-right: 6px; }
    .badge.norm { background: rgba(74,222,128,0.15); color: var(--good); }
    .badge.risk { background: rgba(251,191,36,0.15); color: var(--warn); }
    .badge.stop { background: rgba(248,113,113,0.15); color: var(--bad); }
    .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
            padding: 16px 18px; margin: 8px 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px; }
    .kpi { background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
           padding: 10px 12px; }
    .kpi .label { font-size: 11px; color: var(--muted); text-transform: uppercase;
                  letter-spacing: 0.4px; }
    .kpi .value { font-size: 22px; font-weight: 600; margin-top: 2px; }
    .kpi .sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
    table { border-collapse: collapse; width: 100%; font-size: 13px; }
    th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); }
    th { font-weight: 600; font-size: 11px; color: var(--muted); text-transform: uppercase;
         letter-spacing: 0.4px; }
    td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
    .bar-row { display: grid; grid-template-columns: 50px 70px 1fr; align-items: center;
               gap: 10px; margin: 4px 0; font-variant-numeric: tabular-nums; }
    .bar-row .lbl { color: var(--muted); font-size: 12px; }
    .bar-row .val { text-align: right; font-size: 12px; }
    .bar { height: 14px; background: var(--bar-bg); border-radius: 3px; overflow: hidden; }
    .bar > div { height: 100%; background: var(--bar); }
    .small { font-size: 12px; color: var(--muted); }
    .pos { color: var(--good); }
    .neg { color: var(--bad); }
    .warn { color: var(--warn); }
    .footer { color: var(--muted); font-size: 11px; margin-top: 32px;
              border-top: 1px solid var(--border); padding-top: 12px; }
    code { background: var(--bar-bg); padding: 1px 6px; border-radius: 3px; font-size: 12px; }
    """

    parts = []
    parts.append(f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Профиль — {esc(name)}</title>
<style>{css}</style>
</head><body><div class="wrap">""")

    parts.append(f"""
    <h1>Глубокий профиль менеджера</h1>
    <div class="meta">{esc(name)} <span class="small">· ID {uid}</span></div>
    <div class="meta">Период: <b>{since.date()} — {until.date()}</b>
      ({days} календ. / ~{workdays} рабочих дней)</div>
    <div class="meta">Реги в Bitrix: <b>{esc(u.get('DATE_REGISTER'))}</b> ·
      Должность: <b>{esc(u.get('WORK_POSITION'))}</b> · dept {esc(u.get('UF_DEPARTMENT'))}</div>
    <div class="meta">Email: <b>{esc(u.get('EMAIL'))}</b> · Последний логин:
      <b>{esc(u.get('LAST_LOGIN'))}</b></div>
    """)

    parts.append('<h2>Ключевые метрики за весь период</h2>')
    parts.append('<div class="grid">')
    kpis = [
        ("Наборов", nab, f"~{nab / max(workdays, 1):.1f} / раб. день"),
        ("Дозвонов", f"{doz}", f"{conv:.0f}% от наборов"),
        ("Разговоров ≥30 сек", f"{doz30}", f"{conv30:.0f}% от наборов"),
        ("Talk-time", f"{calls['talk_total_sec'] / 3600:.1f} ч",
         f"медиана {calls['median_talk']} сек"),
        ("Входящие", f"{calls['in']}",
         f"пропущено {calls['miss']} ({calls['miss'] / max(calls['in'], 1) * 100:.0f}%)"),
        ("Встречи проведены", f"{by_stage_m.get(mds.MEETING_DONE, 0)}",
         f"всего {len(meets)} (создал сам {own_meets})"),
        ("Брифы приняты", f"{accepted}",
         f"accept-rate {ar:.0f}% · он автор {own_briefs}"),
        ("Сделки cat.10", f"won {len(won)} · lost {len(lost)}",
         f"проиграно {fmt_amt(lost_amt)} ₽"),
    ]
    for lbl, v, sub in kpis:
        parts.append(f'<div class="kpi"><div class="label">{esc(lbl)}</div>'
                     f'<div class="value">{esc(v)}</div>'
                     f'<div class="sub">{esc(sub)}</div></div>')
    parts.append('</div>')

    # Помесячная динамика
    parts.append('<h2>Помесячная динамика звонков</h2>')
    parts.append('<div class="card"><table>'
                 '<thead><tr><th>Месяц</th><th class="num">Наб</th>'
                 '<th class="num">Дзв</th><th class="num">Конв</th>'
                 '<th class="num">Дзв ≥30с</th><th class="num">% реал.</th>'
                 '<th class="num">Вход.</th><th class="num">Пропущ</th>'
                 '</tr></thead><tbody>')
    for k in months:
        m = calls["bymonth"][k]
        c = m["doz"] / m["nab"] * 100 if m["nab"] else 0
        r30 = m["doz30s"] / m["nab"] * 100 if m["nab"] else 0
        miss_pct = m["miss"] / max(m["in"], 1) * 100
        miss_cls = "neg" if miss_pct >= 40 else ""
        parts.append(f'<tr><td>{k}</td>'
                     f'<td class="num">{m["nab"]}</td>'
                     f'<td class="num">{m["doz"]}</td>'
                     f'<td class="num">{c:.0f}%</td>'
                     f'<td class="num">{m["doz30s"]}</td>'
                     f'<td class="num">{r30:.0f}%</td>'
                     f'<td class="num">{m["in"]}</td>'
                     f'<td class="num {miss_cls}">{m["miss"]}</td></tr>')
    parts.append('</tbody></table></div>')

    # Графики bars
    parts.append('<div class="grid" style="grid-template-columns: 1fr 1fr;">')
    # by DOW
    parts.append('<div class="card"><h3>Наборы по дням недели</h3>')
    for d in range(7):
        s = calls["by_dow"].get(d, {"nab": 0, "doz": 0})
        pct = s["nab"] / dow_max * 100
        parts.append(f'<div class="bar-row"><div class="lbl">{WEEKDAYS[d]}</div>'
                     f'<div class="val">{s["nab"]}</div>'
                     f'<div class="bar"><div style="width: {pct:.1f}%"></div></div></div>')
    parts.append('</div>')

    # by hour
    parts.append('<div class="card"><h3>Наборы по часам (МСК)</h3>')
    for h in sorted(calls["by_hour"].keys()):
        n = calls["by_hour"][h]
        pct = n / hour_max * 100
        parts.append(f'<div class="bar-row"><div class="lbl">{h:02d}:00</div>'
                     f'<div class="val">{n}</div>'
                     f'<div class="bar"><div style="width: {pct:.1f}%"></div></div></div>')
    parts.append('</div>')
    parts.append('</div>')

    # Встречи / Брифы
    parts.append('<h2>Встречи и брифы</h2>')
    parts.append('<div class="grid" style="grid-template-columns: 1fr 1fr;">')
    parts.append('<div class="card"><h3>Встречи (smart-process 1048 / cat 24)</h3>')
    parts.append(f'<div class="small">Всего: <b>{len(meets)}</b> · '
                 f'создал сам: <b>{own_meets}</b> · передали ему: <b>{len(meets) - own_meets}</b></div>')
    parts.append('<table style="margin-top: 8px;"><thead><tr><th>Стадия</th>'
                 '<th class="num">Кол-во</th></tr></thead><tbody>')
    for st, n in by_stage_m.most_common():
        parts.append(f'<tr><td>{esc(st)}</td><td class="num">{n}</td></tr>')
    parts.append('</tbody></table></div>')

    parts.append('<div class="card"><h3>Брифы (smart-process 1056 / cat 28)</h3>')
    parts.append(f'<div class="small">Всего: <b>{len(briefs)}</b> · '
                 f'создал сам: <b>{own_briefs}</b> · передали ему: <b>{len(briefs) - own_briefs}</b><br>'
                 f'Accept-rate (S vs F): <b class="pos">{ar:.0f}%</b> '
                 f'({accepted} / {accepted + rejected})</div>')
    parts.append('<table style="margin-top: 8px;"><thead><tr><th>Стадия</th>'
                 '<th class="num">Кол-во</th></tr></thead><tbody>')
    for st, n in by_stage_b.most_common():
        parts.append(f'<tr><td>{esc(st)}</td><td class="num">{n}</td></tr>')
    parts.append('</tbody></table></div>')
    parts.append('</div>')

    # Сделки
    parts.append('<h2>Сделки (cat 10, sales-воронка)</h2>')
    parts.append('<div class="grid">')
    for lbl, v, sub in [
        ("Создано в окне", len(created), f"он автор: {own_d} / {len(created)}"),
        ("WON", f"{len(won)}", f"{fmt_amt(won_amt)} ₽"),
        ("LOST", f"{len(lost)}", f"{fmt_amt(lost_amt)} ₽"),
        ("Активный пайплайн", f"{len(active)}", f"{fmt_amt(act_amt)} ₽"),
    ]:
        parts.append(f'<div class="kpi"><div class="label">{esc(lbl)}</div>'
                     f'<div class="value">{esc(v)}</div>'
                     f'<div class="sub">{esc(sub)}</div></div>')
    parts.append('</div>')

    # Топ потерь
    if lost_sorted:
        parts.append('<h3>Топ потерь по чеку</h3>')
        parts.append('<div class="card"><table><thead><tr>'
                     '<th>ID</th><th class="num">Сумма</th><th>Стадия</th>'
                     '<th>Клиент</th></tr></thead><tbody>')
        for d in lost_sorted[:15]:
            st = d.get("STAGE_ID", "")
            stage_lbl = stage_names.get(st, st)
            cls = "neg" if "ОТВАЛ" in stage_lbl.upper() else "warn"
            parts.append(f'<tr><td>{esc(d["ID"])}</td>'
                         f'<td class="num">{fmt_amt(d.get("OPPORTUNITY"))} ₽</td>'
                         f'<td class="{cls}">{esc(stage_lbl)}</td>'
                         f'<td>{esc(d.get("TITLE") or "")[:60]}</td></tr>')
        parts.append('</tbody></table></div>')

    # Активные
    if by_st_a:
        parts.append('<h3>Активный пайплайн — по стадиям и возрасту</h3>')
        parts.append('<div class="card"><table><thead><tr>'
                     '<th>Стадия</th><th class="num">Кол-во</th>'
                     '<th class="num">Сумма</th><th class="num">Ср. возраст, дн</th>'
                     '</tr></thead><tbody>')
        for st, v in sorted(by_st_a.items(), key=lambda kv: -kv[1]["amt"]):
            avg_age = sum(v["ages"]) / max(len(v["ages"]), 1)
            age_cls = "neg" if avg_age >= 60 else ("warn" if avg_age >= 30 else "")
            stage_lbl = stage_names.get(st, st)
            parts.append(f'<tr><td>{esc(stage_lbl)}</td>'
                         f'<td class="num">{v["n"]}</td>'
                         f'<td class="num">{fmt_amt(v["amt"])} ₽</td>'
                         f'<td class="num {age_cls}">{avg_age:.0f}</td></tr>')
        parts.append('</tbody></table></div>')

    # Плюсы / Минусы
    parts.append('<h2>Плюсы — на что опираться</h2>')
    parts.append("""
    <div class="card"><ol>
      <li><b>Дисциплина обзвона.</b> 13.7 наборов в день — на верхней границе нормы SM (норма 12–15). За 9 недель не было «провального» периода.</li>
      <li><b>Качество квалификации (брифы accept-rate 89%).</b> Из брифов, дошедших до приёмки, производство принимает 62 из 70. Не «гонит мусор» в производство.</li>
      <li><b>Старт «по верху».</b> Март: 71% конверсия дозвона, медиана разговора держалась. Базовые навыки коммуникации есть.</li>
      <li><b>Проактивность.</b> 25 из 43 встреч он создал сам (58%) — не просто ведёт «висяки», а формирует поток.</li>
      <li><b>Зрелое распределение по дням.</b> Пн-Вт максимум — раннее в неделе цикл лучше «нагружается».</li>
      <li><b>Хорошо подбирает «наследство».</b> Половина брифов и сделок ему передали — он их не сливает, доводит до приёмки.</li>
    </ol></div>
    """)

    parts.append('<h2>Слабые стороны — что чинить (приоритет сверху вниз)</h2>')
    parts.append("""
    <div class="card"><ol>
      <li><span class="badge stop">КРИТ</span> <b>Пропущенные входящие — 76%.</b> 29 из 38 входящих не отвечены. Это самый дорогой провал: входящие — уже тёплые лиды. Лечится правилом «исходящий ставим на паузу при входящем» + Telegram-уведомлением.</li>
      <li><span class="badge risk">РИСК</span> <b>Падающая глубина разговора.</b> Медиана 39 сек по всему периоду. Только 58% дозвонов идут в разговор ≥30 сек. Тренд: 43% → 36% → 31%. Скрипты «не сорваться в первые 30 секунд» нужны срочно.</li>
      <li><span class="badge stop">КРИТ</span> <b>0 побед при 26 потерях на 5M ₽.</b> Хантер-навыки хорошие, closer-навыки нерабочие. Не «не умеет продавать», а «не умеет закрывать».</li>
      <li><span class="badge risk">РИСК</span> <b>Зависшие в «Подготовке КП»</b> — 10 шт, средний возраст 90 дней, чеки 6.6k каждый. Нужно поднять и закрыть отвалом или дожать.</li>
      <li><span class="badge risk">РИСК</span> <b>Майский спад конверсии.</b> С 71% до 52% за 2 месяца. Если в июне продолжит — сигнал на интервью.</li>
      <li><span class="badge risk">РИСК</span> <b>Не работает «вечерний хвост».</b> После 18:00 МСК — только 12 звонков. Для B2B-клиник это потерянное окно (главврачи освобождаются после приёма).</li>
      <li><span class="badge risk">РИСК</span> <b>Скрытый риск переоценки результатов.</b> Только 5 из 30 сделок — его авторство, 33 из 76 брифов. На «своих» данных статистики мало. Нужно 1–2 месяца на чистые когорты.</li>
    </ol></div>
    """)

    parts.append(f"""
    <div class="footer">
      Сгенерировано {datetime.now(MSK).strftime("%Y-%m-%d %H:%M:%S")} МСК ·
      Источник: Bitrix24 ({config.PORTAL_DOMAIN}) ·
      Скрипты: <code>belberry/sales/scripts/manager_deep_stats.py</code> ·
      <code>belberry/sales/scripts/manager_deep_stats_html.py</code>
    </div>
    """)
    parts.append('</div></body></html>')
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("user_id", type=int)
    ap.add_argument("--out", required=True)
    ap.add_argument("--from", dest="start", help="override start (YYYY-MM-DD)")
    args = ap.parse_args()

    bx = BitrixClient(log_path=config.LOG_PATH)
    u = mds.get_user(bx, args.user_id)
    until = datetime.now(MSK).replace(microsecond=0)
    if args.start:
        since = datetime.fromisoformat(args.start).replace(tzinfo=MSK)
    else:
        since = mds.parse(u.get("DATE_REGISTER")) or (until - timedelta(days=365))

    calls = mds.collect_calls(bx, args.user_id, since, until)
    meets = mds.collect_smart(bx, 1048, 24, args.user_id, since, until)
    briefs = mds.collect_smart(bx, 1056, 28, args.user_id, since, until)
    deals = mds.collect_deals(bx, args.user_id, since, until)
    stage_names = mds.collect_stages(bx)

    html_str = render(args.user_id, u, since, until, calls, meets, briefs, deals, stage_names)
    Path(args.out).write_text(html_str, encoding="utf-8")
    print(f"Written: {args.out}  ({len(html_str):,} bytes)")


if __name__ == "__main__":
    main()
