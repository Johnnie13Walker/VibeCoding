#!/usr/bin/env python3
"""KP-пайплайн MVP: сделка → данные аудитов → заготовка КП (SEO-Belberry).

Оркестрирует существующие скрипты движка (bitrix_audit / build_kp / metrika_audit /
prodoctorov_audit) в папке клиента, ведёт состояние стадий в kp_job.json
(идемпотентно: готовые стадии пропускаются), собирает kp_data.json — свод фактов
строго с источниками — и копирует эталон деки. Цены НЕ считает (зона сметчика),
в Bitrix НЕ пишет. Спека: KP-ENGINE-MVP-SPEC.md.

    python3 kp_pipeline.py <deal_id> [--client имя] [--competitors d1 d2 ...]
                           [--days 90] [--prodoctorov url ...]
                           [--skip-metrika] [--skip-prodoctorov]
                           [--status] [--force стадия|all]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

KP_DIR = Path(__file__).resolve().parent

# enum «Список услуг» брифа СП1056 → пресет сметы kp_smeta (тарифы матрицы)
BRIEF_SVC_TO_PRESET = {
    2730: "seo", 2726: "ppc", 2732: "orm", 2738: "program",
    2740: "lp", 2742: "branding", 2736: "tv",
}


def pick_template(brand: str = "belberry") -> Path:
    """Золотой шаблон деки по бренду; запасной вариант — клиентский эталон."""
    tpl = KP_DIR / "templates" / f"seo-{brand}"
    if (tpl / "kp.html").exists():
        return tpl
    return KP_DIR / "clients" / "med-shushary"


def preset_for_brief(brief_services: list | None, default: str = "seo") -> str:
    """Пресет сметы по услугам брифа: первая знакомая услуга, иначе default."""
    for svc in brief_services or []:
        if svc in BRIEF_SVC_TO_PRESET:
            return BRIEF_SVC_TO_PRESET[svc]
    return default


def brief_pick(facts: dict, *prefixes: str):
    """Значение бриф-факта по ПРЕФИКСУ подписи — подписи полей гуляют между
    брифами («Приоритетные товары/услуги…» vs «Приоритетные услуги или направления»)."""
    for key, val in facts.items():
        if not key.startswith("brief:"):
            continue
        label = key[len("brief:"):]
        if any(label.startswith(p) for p in prefixes) and val:
            return val
    return None


def benchmark_substitutions(audit: dict | None) -> dict[str, str]:
    """Заголовок и вывод бенчмарк-слайда — ПО ДАННЫМ, а не из шаблона.

    Шаблонный заголовок «вы отстаёте» врал лидерам ниши (crystal-sound: ИКС 270
    против 170 у лучшего конкурента) — теперь формулировка следует фактам.
    """
    cl = (audit or {}).get("client") or {}
    comps = [c for c in (audit or {}).get("competitors", []) if c.get("sqi")]
    sqi = cl.get("sqi")
    if not sqi or not comps:
        return {}
    best = max(comps, key=lambda c: c["sqi"])
    if sqi >= best["sqi"]:
        return {
            "{{БЕНЧМАРК_ЗАГОЛОВОК}}": "По авторитету вы впереди — закрепляем отрыв",
            "{{БЕНЧМАРК_ПОДЗАГОЛОВОК}}": "Видимость — вы впереди",
            "{{БЕНЧМАРК_ВЫВОД}}": (
                f"По <strong>авторитету сайта (ИКС {sqi})</strong> вы впереди конкурентов "
                f"(лучший — {best['domain']}, ИКС {best['sqi']}). "
                f'<strong style="color:#0a8f5f;">Авторитет уже есть — задача конвертировать '
                f"его в позиции и заявки, пока конкуренты не догнали.</strong>"),
        }
    return {
        "{{БЕНЧМАРК_ЗАГОЛОВОК}}": "В поиске вас находят реже, чем конкурентов",
        "{{БЕНЧМАРК_ПОДЗАГОЛОВОК}}": "Видимость — вы отстаёте",
        "{{БЕНЧМАРК_ВЫВОД}}": (
            f"По <strong>авторитету сайта (ИКС {sqi})</strong> вы отстаёте от лидера ниши "
            f"({best['domain']}, ИКС {best['sqi']}). "
            f'<strong style="color:#0a8f5f;">Дело не в продукте — вас просто '
            f"не находят в поиске.</strong>"),
    }


SLIDE_SECTION_RE = re.compile(r'<section class="slide[^"]*"[^>]*>.*?</section>', re.S)


def renumber_pagenums(html: str) -> str:
    """Нумерация слайдов ПО ФАКТУ после всех вставок: «NN / total».

    Вставные data-слайды ломали статическую нумерацию («07 / 12» на 9-м из 14).
    """
    total = len(SLIDE_SECTION_RE.findall(html))
    if not total:
        return html
    counter = {"n": 0}

    def slide_sub(m):
        counter["n"] += 1
        return re.sub(r'(class="pagenum">)[^<]*(<)',
                      rf"\g<1>{counter['n']:02d} / {total}\g<2>", m.group(0))

    return SLIDE_SECTION_RE.sub(slide_sub, html)


def render_trend_svg(metrika: dict | None, width: int = 520, height: int = 110) -> str | None:
    """Спарклайн органики по месяцам (Метрика) — единственный график деки.

    Только полные месяцы; подписи первого/последнего значения. Данных < 3 точек —
    графика нет (две точки — не тренд).
    """
    months = [m for m in (((metrika or {}).get("trend") or {}).get("organic") or {})
              .get("months", []) if not m.get("partial") and m.get("visits") is not None]
    if len(months) < 3:
        return None
    vals = [m["visits"] for m in months]
    vmax, vmin = max(vals), min(vals)
    span = (vmax - vmin) or 1
    pad, w, h = 8, width, height
    step = (w - 2 * pad) / (len(vals) - 1)
    pts = [(pad + i * step, pad + (h - 2 * pad) * (1 - (v - vmin) / span))
           for i, v in enumerate(vals)]
    poly = " ".join(f"{x:.0f},{y:.0f}" for x, y in pts)
    first, last = months[0], months[-1]
    lx, ly = pts[-1]
    return (f'<svg width="{w}" height="{h + 26}" viewBox="0 0 {w} {h + 26}" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'<polyline points="{poly}" fill="none" stroke="#3086FB" stroke-width="3" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
            + "".join(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3.5" fill="#3086FB"/>'
                      for x, y in pts)
            + f'<text x="{pad}" y="{h + 18}" font-size="11" fill="#6b6f88">'
              f'{first["month"]}: {first["visits"]}</text>'
            f'<text x="{lx:.0f}" y="{ly - 9:.0f}" font-size="12" font-weight="700" '
            f'fill="#313131" text-anchor="end">{last["visits"]}</text>'
            f'<text x="{w - pad}" y="{h + 18}" font-size="11" fill="#6b6f88" '
            f'text-anchor="end">{last["month"]} · визиты из поиска [Метрика]</text></svg>')


def render_iks_bars(audit: dict | None, width: int = 560) -> str | None:
    """Горизонтальный бар-чарт ИКС: клиент против конкурентов (визуал бенчмарка)."""
    cl = (audit or {}).get("client") or {}
    if not cl.get("sqi"):
        return None
    rows = [(cl.get("domain", "вы"), cl["sqi"], True)] + [
        (c["domain"], c["sqi"], False)
        for c in (audit or {}).get("competitors", []) if c.get("sqi")]
    if len(rows) < 2:
        return None
    rows.sort(key=lambda r: -r[1])
    vmax = rows[0][1] or 1
    bar_h, gap, label_w = 21, 8, 150
    h = len(rows) * (bar_h + gap)
    parts = [f'<svg width="{width}" height="{h}" viewBox="0 0 {width} {h}" '
             f'xmlns="http://www.w3.org/2000/svg" font-family="Manrope,sans-serif">']
    for i, (name, val, me) in enumerate(rows):
        y = i * (bar_h + gap)
        w = (width - label_w - 60) * val / vmax
        color = "#3086FB" if me else "#C9D7EC"
        weight = "800" if me else "500"
        label = f"{name} · вы" if me else name
        parts.append(
            f'<text x="0" y="{y + bar_h - 8}" font-size="12" font-weight="{weight}" '
            f'fill="#313131">{label[:22]}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w:.0f}" height="{bar_h}" rx="6" fill="{color}"/>'
            f'<text x="{label_w + w + 8:.0f}" y="{y + bar_h - 8}" font-size="13" '
            f'font-weight="800" fill="#313131">{val}</text>')
    parts.append("</svg>")
    return "".join(parts)




def problem_paths_from_metrika(metrika: dict | None, limit: int = 2) -> list[str]:
    """Пути проблемных страниц из находок Метрики («/rent собирает 10%…»)."""
    out = []
    for p in (metrika or {}).get("problems") or []:
        m = re.search(r"(/[a-z0-9_\-/]+)", p.get("fact", ""))
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out[:limit]


def render_problem_shots(tmp_dir: Path, metrika: dict | None) -> str | None:
    """Мини-скрины проблемных страниц с подписями (слайд «проблема → решение»)."""
    import base64
    shots = []
    for p in (metrika or {}).get("problems") or []:
        m = re.search(r"(/[a-z0-9_\-/]+)", p.get("fact", ""))
        if not m:
            continue
        slug = m.group(1).strip("/").replace("/", "_") or "page"
        png = tmp_dir / f"page_{slug}.png"
        if png.exists():
            b64 = base64.b64encode(png.read_bytes()).decode()
            ev = p.get("evidence") or {}
            bounce = ev.get("page_bounce")
            cap = f"{m.group(1)} — отказы {bounce}%" if bounce else m.group(1)
            shots.append(
                f'<div style="flex:1;min-width:0;"><div style="border:1px solid #EDF1F7;'
                f'border-radius:10px;overflow:hidden;"><img src="data:image/png;base64,{b64}" '
                f'style="width:100%;display:block;"/></div>'
                f'<div style="font-size:11px;color:#a13442;font-weight:700;margin-top:6px;">'
                f'{cap} <span style="color:#717885;font-weight:500;">[Метрика]</span></div></div>')
    if not shots:
        return None
    return ('<div style="display:flex;gap:14px;margin-top:14px;">' + "".join(shots) + "</div>")


def render_sources_svg(metrika: dict | None, width: int = 520) -> str | None:
    """Источники трафика: визиты барами + конверсия подписью (топ-5)."""
    rows = [(s.get("source", "")[:28], s.get("visits") or 0, s.get("conversion"))
            for s in (metrika or {}).get("source_conversion") or [] if s.get("visits")]
    if len(rows) < 2:
        return None
    rows = sorted(rows, key=lambda r: -r[1])[:5]
    vmax = rows[0][1] or 1
    bar_h, gap, label_w = 20, 9, 190
    h = len(rows) * (bar_h + gap)
    parts = [f'<svg width="{width}" height="{h}" viewBox="0 0 {width} {h}" '
             f'xmlns="http://www.w3.org/2000/svg" font-family="Manrope,sans-serif">']
    for i, (name, visits, conv) in enumerate(rows):
        y = i * (bar_h + gap)
        w = (width - label_w - 120) * visits / vmax
        is_search = "поиск" in name.lower()
        color = "#3086FB" if is_search else "#C9D7EC"
        conv_txt = f" · {conv}% в заявку" if conv else ""
        parts.append(
            f'<text x="0" y="{y + bar_h - 5}" font-size="11" '
            f'font-weight="{"800" if is_search else "500"}" fill="#313131">{name}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w:.0f}" height="{bar_h}" rx="5" fill="{color}"/>'
            f'<text x="{label_w + w + 7:.0f}" y="{y + bar_h - 5}" font-size="11" '
            f'font-weight="700" fill="#313131">{visits:,}'.replace(",", " ") + f'{conv_txt}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render_geo_svg(metrika: dict | None, width: int = 480) -> str | None:
    """География спроса: топ-5 регионов барами."""
    rows = [(g.get("region", "")[:26], g.get("visits") or 0)
            for g in (metrika or {}).get("geo") or []
            if g.get("visits") and "Не определено" not in (g.get("region") or "")]
    if len(rows) < 2:
        return None
    rows = rows[:5]
    vmax = max(v for _, v in rows) or 1
    bar_h, gap, label_w = 20, 9, 200
    h = len(rows) * (bar_h + gap)
    parts = [f'<svg width="{width}" height="{h}" viewBox="0 0 {width} {h}" '
             f'xmlns="http://www.w3.org/2000/svg" font-family="Manrope,sans-serif">']
    for i, (name, visits) in enumerate(rows):
        y = i * (bar_h + gap)
        w = (width - label_w - 70) * visits / vmax
        parts.append(
            f'<text x="0" y="{y + bar_h - 5}" font-size="11" fill="#313131">{name}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w:.0f}" height="{bar_h}" rx="5" fill="#7FB5FF"/>'
            f'<text x="{label_w + w + 7:.0f}" y="{y + bar_h - 5}" font-size="11" '
            f'font-weight="700" fill="#313131">{visits:,}'.replace(",", " ") + '</text>')
    parts.append("</svg>")
    return "".join(parts)


def offer_substitutions(metrika: dict | None, spec: dict | None) -> dict[str, str]:
    """Оффер на титул и стоимость заявки — честный расчёт из прогноза и сметы."""
    f = forecast_numbers(metrika)
    if not f:
        return {}
    subs = {"{{ОФФЕР_ЗАЯВКИ}}": f"+{f['leads_lo'] - f['leads_now']}–"
                                f"{f['leads_hi'] - f['leads_now']} заявок в месяц из поиска"}
    if spec and spec.get("items"):
        import kp_smeta
        _, subtotal = kp_smeta.build_rows(spec["items"])
        price = subtotal * (1 + kp_smeta.VAT)
        if price > 0 and f["leads_lo"]:
            lo, hi = round(price / f["leads_hi"]), round(price / f["leads_lo"])
            subs["{{ЦЕНА_ЗА_ЗАЯВКУ}}"] = (f"{lo:,}–{hi:,} ₽".replace(",", " "))
    return subs


def smeta_substitutions(spec: dict | None) -> dict[str, str]:
    """Ценовые плейсхолдеры деки из сметы (тарифы матрицы — официальные цены)."""
    if not spec or not spec.get("items"):
        return {}
    import kp_smeta
    _, subtotal = kp_smeta.build_rows(spec["items"])
    if subtotal <= 0:
        return {}
    fmt = lambda n: f"{round(n):,}".replace(",", " ") + " ₽"  # noqa: E731
    subs = {"{{ЦЕНА_БЕЗ_НДС}}": fmt(subtotal),
            "{{ЦЕНА_С_НДС}}": fmt(subtotal * (1 + kp_smeta.VAT))}
    if spec.get("deadline"):
        subs["{{ДЕДЛАЙН_ПОДАРКА}}"] = str(spec["deadline"])
    return subs


def deck_substitutions(data: dict, today: str) -> dict[str, str]:
    """Карта замен плейсхолдеров деки реальными фактами (только то, что знаем)."""
    facts = {f["key"]: f["value"] for f in data.get("facts", [])}
    subs: dict[str, str] = {}
    domain = data.get("domain") or ""
    if domain:
        subs["{{ДОМЕН}}"] = domain
        subs["{{домен}}"] = domain
        subs["{{КЛИЕНТ}}"] = str(facts.get("deal_title") or domain)
    subs["{{ДАТА}}"] = today
    region = brief_pick(facts, "Регион")
    if region:
        subs["{{ГОРОД}}"] = str(region)
        subs["{{ГЕО}}"] = str(region)
    services = brief_pick(facts, "Приоритетные")
    if services:
        subs["{{ПРИОРИТЕТНЫЕ_УСЛУГИ}}"] = str(services)
    return subs


PLACEHOLDER_RE = re.compile(r"\s*[:·—-]?\s*\{\{[А-ЯЁA-Z0-9_]+\}\}\.?")


def scrub_placeholders(html: str) -> tuple[str, int]:
    """Зачистка уцелевших {{ПЛЕЙСХОЛДЕРОВ}} — клиент не должен видеть их никогда.

    Убираем вместе с висящим разделителем («…из поиска: {{X}}.» → «…из поиска»).
    """
    left = len(PLACEHOLDER_RE.findall(html))
    return PLACEHOLDER_RE.sub("", html), left


def niche_text_from_bitrix(bx: dict) -> str:
    """Текст ниши клиента для подбора кейсов: сфера + приоритетные услуги + продукт."""
    brief = bx.get("brief") or {}
    parts = [bx.get("sfera") or "",
             brief.get("Приоритетные товары/услуги, которые нужно продвигать") or "",
             brief.get("Что представляет собой продукт (товар, услуга или компания)?") or ""]
    return " ".join(p for p in parts if p).strip()


def filter_prcy_rows(rows_html: str | None, has_metrika: bool, brand: str) -> str | None:
    """Чистка строк техаудита PR-CY: при живой Метрике — без его оценок трафика
    (отказы/визиты), для немедицинских брендов — без мед-флагов (онлайн-запись)."""
    if not rows_html:
        return rows_html
    kept = []
    for row in re.findall(r"<tr>.*?</tr>", rows_html, re.S):
        low = row.lower()
        if has_metrika and ("отказ" in low or "визит" in low):
            continue  # есть факт Метрики — оценки PR-CY не показываем
        if brand != "belberry" and "онлайн-запис" in low:
            continue  # мед-флаг неприменим вне медицины
        kept.append(row)
    return "\n".join(kept) if kept else None


def combine_problem_rows(prcy_rows: str | None, metrika_rows: str | None) -> str | None:
    """Слайд «проблема → решение»: техфлаги PR-CY + находки Метрики одним списком."""
    chunks = [c for c in (prcy_rows, metrika_rows) if c and c.strip()]
    return "\n".join(chunks) if chunks else None


def render_blockers_html(audit: dict | None, metrika: dict | None,
                         insights: dict | None) -> str | None:
    """Слайд «Что мешает» — 3 колонки ТОЛЬКО из реальных данных клиента.

    Заменяет ручную сетку с цифрами-образцами (баг: med-shushary-числа выглядели
    как аудит клиента). Пункт появляется только при наличии данных; пусто — None.
    """
    import html as _h
    cl = (audit or {}).get("client") or {}
    comps = [c for c in (audit or {}).get("competitors", []) if c.get("sqi")]

    vis: list[str] = []
    sqi = cl.get("sqi")
    if sqi and comps:
        leader = max(comps, key=lambda c: c["sqi"])
        if sqi < leader["sqi"]:
            vis.append(f"Авторитет сайта <b>ИКС {sqi}</b> — у лидера ниши "
                       f"{_h.escape(leader['domain'])} <b>{leader['sqi']}</b>")
    yi, gi = cl.get("yandex_index"), cl.get("google_index")
    if yi and gi and min(yi, gi) < max(yi, gi) * 0.7:
        worse = "Google" if gi < yi else "Яндексе"
        vis.append(f"В {worse} проиндексировано <b>{min(yi, gi)}</b> страниц "
                   f"против <b>{max(yi, gi)}</b> — дисбаланс видимости")
    donors = cl.get("donors")
    if donors is not None and donors < 30:
        vis.append(f"Внешних ссылок всего <b>{donors}</b> — ссылочный профиль "
                   f"не даёт расти в выдаче")

    tech: list[str] = []
    if cl.get("schema_org") is False:
        tech.append("<b>Нет Schema-разметки</b> — поисковики не показывают "
                    "расширенные карточки в выдаче")
    if (cl.get("load_time") or 0) > 2:
        tech.append(f"Загрузка <b>{cl['load_time']:.1f} с</b> — медленно, "
                    f"посетители уходят не дождавшись")
    for flag, name in (("robots", "robots.txt"), ("sitemap", "карта сайта")):
        if cl.get(flag) is False:
            tech.append(f"Отсутствует <b>{name}</b>")
    for issue in ((insights or {}).get("site_issues") or [])[:2]:
        tech.append(f"{_h.escape(issue.get('issue', ''))} "
                    f"<span style='opacity:.65'>({_h.escape(issue.get('evidence', '')[:60])})</span>")

    flow: list[str] = []
    for p in ((metrika or {}).get("problems") or [])[:2]:
        flow.append(_h.escape(p.get("fact", "")))
    for src in (metrika or {}).get("source_conversion") or []:
        if "рекламе" in src.get("source", "") and src.get("visits"):
            org = next((s for s in metrika["source_conversion"]
                        if "поисков" in s.get("source", "")), None)
            if org and org.get("conversion", 0) > (src.get("conversion") or 0):
                flow.append(f"Реклама даёт <b>{src['visits']}</b> визитов, но конвертит "
                            f"<b>{src['conversion']}%</b> против <b>{org['conversion']}%</b> "
                            f"у поиска — платный трафик дороже и слабее")
            break
    pains = (insights or {}).get("pains") or []
    if pains:
        flow.append(f"{_h.escape(pains[0].get('pain', ''))} "
                    f"<span style='opacity:.65'>— из разбора встречи</span>")

    cols = [("Видимость в поиске", "red", vis, "🔍 API-аудит сайта"),
            ("Сайт и техническая база", "amber", tech, "🔍 аудит + текст страниц"),
            ("Поток и аналитика", "blue", flow, "📊 Яндекс.Метрика · 🗣 встреча")]
    blocks = []
    for title, color, items, src in cols:
        if not items:
            continue
        lis = "".join(f"<li>{it}</li>" for it in items)
        blocks.append(f'<div class="pgroup bad"><span class="ph {color}">{title}</span>'
                      f'<ul>{lis}</ul><div class="src">{src}</div></div>')
    return "\n".join(blocks) if blocks else None


def forecast_numbers(metrika: dict | None) -> dict | None:
    """Прогноз ОТ ФАКТИЧЕСКОЙ конверсии клиента: визиты органики × его конверсия.

    Консервативно: конверсию НЕ повышаем, рост органики ×1,5–2 за 6–12 мес —
    диапазон, не точка. Нет Метрики (визитов или конверсии) → None, прогноза нет.
    """
    if not metrika:
        return None
    organic = ((metrika.get("trend") or {}).get("organic") or {})
    visits = organic.get("current")
    conv = next((s.get("conversion") for s in metrika.get("source_conversion") or []
                 if "поисков" in (s.get("source") or "")), None)
    if not visits or not conv:
        return None
    leads_now = visits * conv / 100
    return {"visits_now": int(visits), "conv": conv,
            "leads_now": round(leads_now),
            "visits_lo": int(visits * 1.5), "visits_hi": int(visits * 2),
            "leads_lo": round(leads_now * 1.5), "leads_hi": round(leads_now * 2),
            "goal": ((metrika.get("main_goal") or {}).get("name") or "обращение")}


FORECAST_FALLBACK_ROW = (
    '<tr><td colspan="4" style="color:#6b6f88;padding:14px 0;">Для честного прогноза '
    'нужен доступ к вашей Яндекс.Метрике — посчитаем от фактической конверсии, '
    'а не от «средних по рынку».</td></tr>')


def render_forecast_html(metrika: dict | None) -> str | None:
    """Строки прогноза для маркера AUTO:FORECAST (tbody таблицы
    «Показатель | Сейчас | 6 мес | 12 мес» в шаблонах).

    6 мес = рост органики ×1,5, 12 мес = ×2; конверсия клиента не повышается.
    """
    f = forecast_numbers(metrika)
    if not f:
        return None
    fmt = lambda n: f"{n:,}".replace(",", " ")  # noqa: E731
    return f'''          <tr><td>Визиты из поиска / мес</td>
            <td class="right num now">~{fmt(f["visits_now"])}</td>
            <td class="right num">{fmt(f["visits_lo"])}</td>
            <td class="right num future">{fmt(f["visits_hi"])}</td></tr>
          <tr><td>Конверсия в заявку — ваша, цель «{f["goal"]}» (не повышаем)</td>
            <td class="right num">{f["conv"]}%</td>
            <td class="right num">{f["conv"]}%</td>
            <td class="right num">{f["conv"]}%</td></tr>
          <tr class="totalrow"><td>Обращений из поиска / мес</td>
            <td class="right num">~{f["leads_now"]}</td>
            <td class="right num">{f["leads_lo"]} <span style="font-weight:400">(+{f["leads_lo"] - f["leads_now"]})</span></td>
            <td class="right num">{f["leads_hi"]} <span style="font-weight:400">(+{f["leads_hi"] - f["leads_now"]})</span></td></tr>'''


def render_traffic_drop(data: dict, metrika: dict | None = None) -> str | None:
    """Баннер боли (маркер AUTO:TRAFFIC_DROP). ПРАВИЛО ЗАКАЗЧИКА 11.06:
    есть Метрика — ориентируемся ТОЛЬКО на Метрику; PR-CY — лишь запасной.

    Метрика-тренд падает → красный баннер из её чисел. Стабилен/растёт —
    про просадку НЕ врём: баннер про недоинвестированный поиск (конверсии
    из Метрики). Метрики нет → старый PR-CY-вариант с явной пометкой [оценка].
    """
    organic = ((metrika or {}).get("trend") or {}).get("organic") or {}
    if organic.get("current"):
        if organic.get("direction") == "падение":
            peak, cur = organic.get("peak"), organic.get("current")
            pct = organic.get("change_pct")
            return (f'<div class="pb-num">{pct}%</div>\n'
                    f'<div class="pb-txt"><b>Органика падает.</b> '
                    f'{peak} визитов ({organic.get("peak_month", "")}) → {cur} '
                    f'({organic.get("current_month", "")}). Без работ тренд продолжится. '
                    f'<span style="opacity:.7">[Яндекс.Метрика]</span></div>')
        # органика не падает — честный баннер про главный рычаг из конверсий
        src = {s.get("source"): s for s in (metrika or {}).get("source_conversion") or []}
        ads = next((v for k, v in src.items() if k and "рекламе" in k), None)
        org = next((v for k, v in src.items() if k and "поисков" in k), None)
        if ads and org and org.get("conversion", 0) > (ads.get("conversion") or 0):
            total = sum(v.get("visits") or 0 for v in src.values()) or 1
            share = round((ads.get("visits") or 0) * 100 / total)
            return (f'<div class="pb-num">×{org["conversion"] / max(ads["conversion"], 0.01):.1f}</div>\n'
                    f'<div class="pb-txt"><b>Поиск конвертит лучше рекламы.</b> '
                    f'Органика даёт заявку с {org["conversion"]}% визитов против '
                    f'{ads["conversion"]}% у рекламы ({share}% трафика — платный). '
                    f'Каждый визит из поиска ценнее — и этот канал недоинвестирован. '
                    f'<span style="opacity:.7">[Яндекс.Метрика]</span></div>')
        return None  # Метрика есть, но боли по трафику нет — баннер не показываем
    # Метрики нет — внешняя оценка с явной пометкой
    fact = next((f for f in data.get("facts", []) if f["key"] == "traffic_drop"), None)
    if not fact:
        return None
    txt = str(fact["value"])
    pct = txt.split("=")[-1].strip() if "=" in txt else ""
    return (f'<div class="pb-num">{pct}</div>\n'
            f'<div class="pb-txt"><b>Трафик из поиска просел.</b> {txt}. '
            f'<span style="opacity:.7">[оценка PR-CY — для точных цифр нужна '
            f'ваша Метрика]</span></div>')
# smeta ДО scaffold: ценовые плейсхолдеры деки заполняются из сметы (тарифы матрицы)
# polish — финальный LLM-редактор текстов (механические гарды в kp_polish)
STAGES = ["bitrix", "audit", "metrika", "webmaster", "prodoctorov", "insights",
          "screenshot", "assemble", "smeta", "scaffold", "polish", "pdf"]

# Маркеры в kp.html эталона для автовставки (если их нет — оставляем файлы рядом)
MARK_BENCH = "<!--AUTO:SEO_BENCHMARK-->"
MARK_PROBLEMS = "<!--AUTO:PROBLEM_SOLUTION-->"
MARK_TRAFFIC = "<!--AUTO:TRAFFIC_DROP-->"
MARK_PAINS = "<!--AUTO:PAINS-->"
MARK_BLOCKERS = "<!--AUTO:BLOCKERS-->"
MARK_FORECAST = "<!--AUTO:FORECAST-->"
MARK_TREND = "<!--AUTO:TREND_SVG-->"
MARK_IKS = "<!--AUTO:IKS_BARS-->"
MARK_SHOT = "<!--AUTO:SITE_SHOT-->"
MARK_PSHOTS = "<!--AUTO:PROBLEM_SHOTS-->"
MARK_SOURCES = "<!--AUTO:SOURCES_SVG-->"
MARK_GEO = "<!--AUTO:GEO_SVG-->"

CHROME_CANDIDATES = [
    os.environ.get("CHROME_BIN"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
]


def find_chrome():
    for c in CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    return None


def embed_screenshot_html(png_b64: str, domain: str) -> str:
    """Скрин сайта в браузер-рамке (титул): «мы смотрели именно ваш сайт»."""
    return (
        '<div style="background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.3);'
        'border-radius:14px;padding:10px 10px 8px;box-shadow:0 18px 50px rgba(0,0,0,.25);">'
        '<div style="display:flex;gap:5px;align-items:center;margin:0 2px 8px;">'
        '<span style="width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.5);"></span>'
        '<span style="width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.35);"></span>'
        '<span style="width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.25);"></span>'
        f'<span style="font-size:10px;color:rgba(255,255,255,.75);margin-left:8px;">{domain}</span></div>'
        f'<img src="data:image/png;base64,{png_b64}" style="width:100%;border-radius:7px;display:block;"/></div>')

DOMAIN_RE = re.compile(r"\b((?:[a-zа-я0-9-]+\.)+(?:ru|com|net|org|рф|su|online|site|clinic|moscow|спб))\b",
                       re.IGNORECASE)


# ── pure-функции (покрыты тестами) ────────────────────────────────────────────

def domain_from_bitrix(bx: dict) -> str:
    """Домен клиента из bitrix.json: поле site сделки, затем бриф, затем TITLE."""
    cands = [bx.get("site") or "",
             (bx.get("brief") or {}).get("Адрес вашего сайта (SEO)") or "",
             bx.get("title") or ""]
    for c in cands:
        c = c.strip().lower()
        c = re.sub(r"^https?://", "", c)
        c = re.sub(r"^www\.", "", c).split("/")[0].strip()
        if "." in c and " " not in c:
            return c
    return ""


def competitors_from_brief(bx: dict, limit: int = 5) -> list[str]:
    """Домены конкурентов из текста брифа (поле со словом «конкурент»).

    Берём только то, что похоже на домен; «мир семьи, веда» текстом — не берём
    (сейлс передаст --competitors). Свой домен исключаем.
    """
    own = domain_from_bitrix(bx)
    text = " ".join(v for k, v in (bx.get("brief") or {}).items()
                    if "конкурент" in k.lower() and isinstance(v, str))
    seen, out = set(), []
    for m in DOMAIN_RE.finditer(text):
        d = m.group(1).lower().lstrip("www.")
        if d != own and d not in seen:
            seen.add(d)
            out.append(d)
    return out[:limit]


def plan_stages(job: dict, force: str | None = None,
                skip: set[str] | None = None) -> list[str]:
    """Какие стадии выполнять: не-done/skipped, минус пропущенные; force=имя|all сбрасывает."""
    skip = skip or set()
    done = {s for s, st in (job.get("stages") or {}).items()
            if st.get("status") in ("done", "skipped")}
    if force == "all":
        done = set()
    elif force:
        done.discard(force)
    return [s for s in STAGES if s not in done and s not in skip]


def traffic_dynamics(history: dict, current=None) -> dict | None:
    """Просадка трафика из visits_history PR-CY: пик → текущее → % падения.

    Слайд «остановить просадку» — главный аргумент SEO-КП. Ключи YYYYMM, нули
    игнорируем (PR-CY ставит 0 за месяцы без данных).
    """
    points = {m: v for m, v in (history or {}).items() if isinstance(v, (int, float)) and v > 0}
    if not points:
        return None
    peak_month, peak = max(points.items(), key=lambda kv: kv[1])
    cur = current if isinstance(current, (int, float)) and current > 0 else points[max(points)]
    if peak <= cur:
        return None
    ym = str(peak_month)
    return {"peak": int(peak), "peak_month": f"{ym[4:6]}.{ym[:4]}",
            "current": int(cur), "drop_pct": -round((peak - cur) / peak * 100)}


def assemble_kp_data(bitrix: dict | None, audit: dict | None,
                     metrika: dict | None, prodoc: list | None,
                     brand: str = "belberry") -> dict:
    """Свод фактов с источниками + чек-лист ручных шагов. Без источника — не факт."""
    facts, hypotheses = [], []

    def fact(key, value, source):
        if value is None or value == "":
            return
        facts.append({"key": key, "value": value, "source": source, "status": "факт"})

    if bitrix:
        fact("deal_title", bitrix.get("title"), "bitrix.json:deal")
        fact("company_revenue", bitrix.get("company_revenue"), "bitrix.json:deal")
        brief = bitrix.get("brief") or {}
        # подписи полей гуляют между брифами — берём по префиксу
        for k, v in brief.items():
            if any(k.startswith(p) for p in
                   ("Приоритетные", "Регион", "Опишите вашу целевую",
                    "УТП", "Сильные стороны")):
                fact(f"brief:{k}", v, "bitrix.json:бриф СП1056")
    has_metrika_trend = bool(((metrika or {}).get("trend") or {}).get("organic", {}).get("current"))
    if audit:
        cl = audit.get("client") or {}
        if isinstance(cl, dict):
            # ПРАВИЛО: есть Метрика — трафик-показатели PR-CY (оценки) не используем
            keys = ("sqi", "yandex_index", "google_index", "load_time", "schema_org")
            if not metrika:
                keys += ("organic_pct", "bounce_rate", "visits_monthly")
            for k in keys:
                fact(k, cl.get(k), "audit.json:pr-cy")
            if not has_metrika_trend:
                drop = traffic_dynamics(cl.get("visits_history") or {}, cl.get("visits_monthly"))
                if drop:
                    fact("traffic_drop",
                         f"пик {drop['peak']} ({drop['peak_month']}) → сейчас {drop['current']} "
                         f"= {drop['drop_pct']}%", "audit.json:pr-cy:visits_history (оценка)")
    if metrika:
        for k in ("visits", "users", "bounce_rate", "organic_share", "goals"):
            fact(f"metrika:{k}", metrika.get(k), "metrika.json")
        organic = (metrika.get("trend") or {}).get("organic") or {}
        if organic.get("current"):
            fact("metrika:organic_trend",
                 f"{organic.get('peak')} ({organic.get('peak_month')}) → "
                 f"{organic.get('current')} ({organic.get('current_month')}), "
                 f"{organic.get('change_pct')}% — {organic.get('direction')}",
                 "metrika.json:trend")
    if prodoc:
        for i, c in enumerate(prodoc):
            if isinstance(c, dict):
                fact(f"prodoctorov:{i}:rating", c.get("rating"), "prodoctorov.json")
                fact(f"prodoctorov:{i}:reviews", c.get("reviews"), "prodoctorov.json")

    if not metrika:
        hypotheses.append({"key": "посещаемость", "status": "гипотеза",
                           "note": "Метрика недоступна — только оценка PR-CY; запросить гостевой доступ"})

    return {
        "deal_id": (bitrix or {}).get("deal_id"),
        "domain": domain_from_bitrix(bitrix or {}),
        "brand": "Acoola Team" if brand == "acoola" else "Belberry",
        "facts": facts,
        "hypotheses": hypotheses,
        "manual_checklist": [
            "Цены — только из сметы сметчика (Google Sheets по матрице), не выдумывать",
            "Титул: клиент, домен, дата, дедлайн подарка/скидки",
            "Каскад скидок: 10% логотип / 5% оперативность с датой (по правилам матрицы)",
            "Прогнозы — диапазоны + дисклеймер «оценка на текущий момент» (LEGAL-MED-2026 §2)",
            "Никаких гарантий результата и «случаев излечения» (ст. 24 ФЗ-38)",
            "Перед отправкой: в папке только клиентские файлы (без внутренних калькуляторов)",
        ],
    }


def inject_auto_blocks(kp_html: str, benchmark: str | None, problems: str | None) -> tuple[str, list[str]]:
    """Вставка авто-фрагментов по маркерам. Возвращает (html, что_не_вставлено)."""
    missing = []
    for mark, frag, name in ((MARK_BENCH, benchmark, "seo_benchmark"),
                             (MARK_PROBLEMS, problems, "problem_solution")):
        if frag and mark in kp_html:
            kp_html = kp_html.replace(mark, frag)
        elif frag:
            missing.append(name)
    return kp_html, missing


# ── исполнение стадий ─────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _run(script: str, args: list[str], cwd: Path) -> None:
    cmd = [sys.executable, str(KP_DIR / script), *args]
    print(f"  $ {script} {' '.join(args)}")
    r = subprocess.run(cmd, cwd=cwd, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"{script} завершился с кодом {r.returncode}")


def run_pipeline(a: argparse.Namespace) -> int:
    # папка клиента: --client или домен (узнаём после стадии bitrix)
    client_dir = KP_DIR / "clients" / a.client if a.client else None
    if client_dir:
        client_dir.mkdir(parents=True, exist_ok=True)

    # bootstrap: bitrix первой стадией, чтобы получить домен для имени папки
    tmp_dir = client_dir or (KP_DIR / "clients" / f"_deal_{a.deal_id}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    job_path = tmp_dir / "kp_job.json"
    job = _load(job_path) or {"deal_id": a.deal_id, "stages": {}}

    if a.status:
        print(f"job: {job_path}")
        for s in STAGES:
            st = (job.get("stages") or {}).get(s, {})
            print(f"  {s:<12} {st.get('status', '—'):<8} {st.get('at', '')}")
        return 0

    skip = set()
    if a.skip_metrika:
        skip.add("metrika")
    if a.skip_prodoctorov or not a.prodoctorov:
        skip.add("prodoctorov")

    todo = plan_stages(job, a.force, skip)
    print(f"Сделка {a.deal_id} → {tmp_dir.name} | стадии: {', '.join(todo) or 'всё готово'}")

    def mark(stage, status="done"):
        job.setdefault("stages", {})[stage] = {"status": status, "at": _now()}
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    for stage in todo:
        print(f"▶ {stage}")
        if stage == "bitrix":
            _run("bitrix_audit.py", [str(a.deal_id)], tmp_dir)
        elif stage == "audit":
            bx = _load(tmp_dir / "bitrix.json") or {}
            domain = domain_from_bitrix(bx)
            if not domain:
                raise RuntimeError("домен не определён — проверь bitrix.json или задай --client")
            comps = a.competitors or competitors_from_brief(bx)
            if not comps:
                print("  ⚠ конкуренты не найдены в брифе — бенчмарк будет без соседей "
                      "(можно перезапустить: --force audit --competitors d1 d2)")
            _run("build_kp.py", [domain, *comps], tmp_dir)
        elif stage == "metrika":
            bx = _load(tmp_dir / "bitrix.json") or {}
            args = [domain_from_bitrix(bx), str(a.days)]
            region = (bx.get("brief") or {}).get("Регион продвижения")
            if region:
                args.append(region)  # гео-проблемы считаются от целевого региона брифа
            try:
                _run("metrika_audit.py", args, tmp_dir)
            except RuntimeError as e:
                print(f"  ⚠ Метрика недоступна ({e}) — продолжаем без неё")
                mark(stage, "skipped")
                continue
        elif stage == "webmaster":
            bx = _load(tmp_dir / "bitrix.json") or {}
            try:
                _run("webmaster_audit.py", [domain_from_bitrix(bx)], tmp_dir)
            except RuntimeError:
                print("  ⚠ Вебмастер недоступен (нет права/делегирования) — пропускаем")
                mark(stage, "skipped")
                continue
        elif stage == "prodoctorov":
            _run("prodoctorov_audit.py", a.prodoctorov, tmp_dir)
        elif stage == "screenshot":
            chrome = find_chrome()
            bx = _load(tmp_dir / "bitrix.json") or {}
            dom = domain_from_bitrix(bx)
            if not chrome or not dom:
                print("  ⚠ нет Chrome/домена — скрин пропущен")
                mark(stage, "skipped")
                continue
            r = subprocess.run([chrome, "--headless", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
                "--screenshot=" + str(tmp_dir / "site.png"),
                "--window-size=1280,860", "--hide-scrollbars",
                "--virtual-time-budget=6000", f"https://{dom}/"],
                capture_output=True, timeout=90)
            if not (tmp_dir / "site.png").exists():
                print("  ⚠ скрин не снялся — пропуск")
                mark(stage, "skipped")
                continue
            print(f"  скрин сайта: {((tmp_dir / 'site.png').stat().st_size // 1024)} КБ")
            # проблемные страницы из находок Метрики
            mt = _load(tmp_dir / "metrika.json") or {}
            for path_ in problem_paths_from_metrika(mt):
                slug = path_.strip("/").replace("/", "_") or "page"
                subprocess.run([chrome, "--headless", "--disable-gpu", "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--screenshot=" + str(tmp_dir / f"page_{slug}.png"),
                    "--window-size=1280,860", "--hide-scrollbars",
                    "--virtual-time-budget=6000", f"https://{dom}{path_}"],
                    capture_output=True, timeout=90)
                if (tmp_dir / f"page_{slug}.png").exists():
                    print(f"  скрин проблемной: {path_}")
        elif stage == "pdf":
            chrome = find_chrome()
            if not chrome or not (tmp_dir / "kp.html").exists():
                print("  ⚠ нет Chrome/деки — PDF пропущен")
                mark(stage, "skipped")
                continue
            subprocess.run([chrome, "--headless", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
                "--no-pdf-header-footer", "--print-to-pdf=" + str(tmp_dir / "deck.pdf"),
                "--virtual-time-budget=4000",
                "file://" + str(tmp_dir / "kp.html")], capture_output=True, timeout=180)
            if (tmp_dir / "deck.pdf").exists():
                print(f"  deck.pdf: {((tmp_dir / 'deck.pdf').stat().st_size // 1024)} КБ")
            else:
                print("  ⚠ PDF не собрался — пропуск")
                mark(stage, "skipped")
                continue
        elif stage == "insights":
            # смысловой слой: бриф + транскрипт + сайт → боли и решения (LLM)
            if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")):
                print("  ⚠ нет LLM-ключа (ANTHROPIC/OPENAI) — смысловой слой пропущен")
                mark(stage, "skipped")
                continue
            try:
                _run("kp_insights.py", [str(tmp_dir)], tmp_dir)
            except RuntimeError as e:
                print(f"  ⚠ смысловой слой не собрался ({e}) — продолжаем без него")
                mark(stage, "skipped")
                continue
        elif stage == "assemble":
            data = assemble_kp_data(_load(tmp_dir / "bitrix.json"), _load(tmp_dir / "audit.json"),
                                    _load(tmp_dir / "metrika.json"), _load(tmp_dir / "prodoctorov.json"),
                                    brand=a.brand)
            (tmp_dir / "kp_data.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  факты: {len(data['facts'])}, гипотезы: {len(data['hypotheses'])}, "
                  f"ручных шагов: {len(data['manual_checklist'])}")
        elif stage == "scaffold":
            dst = tmp_dir / "kp.html"
            if not dst.exists():
                shutil.copy(pick_template(a.brand) / "kp.html", dst)
                print(f"  эталон скопирован: {dst.relative_to(KP_DIR)}")
            html = dst.read_text(encoding="utf-8")
            bench = (tmp_dir / "seo_benchmark.html")
            probs = (tmp_dir / "problem_solution.html")
            # проблемы = техфлаги PR-CY + находки глубокого аудита Метрики
            metrika = _load(tmp_dir / "metrika.json") or {}
            metrika_rows = None
            if metrika.get("problems"):
                from metrika_audit import render_problems_html
                metrika_rows = render_problems_html(metrika["problems"])
                print(f"  проблем из Метрики: {len(metrika['problems'])}")
            # смысловой слой: проблемы сайта (LLM по тексту страниц) + боли клиента
            insights = _load(tmp_dir / "insights.json") or {}
            site_rows = pains_html = None
            if insights:
                from kp_insights import render_pains_html, render_site_rows
                site_rows = render_site_rows(insights)
                pains_html = render_pains_html(insights)
                print(f"  смысловой слой: болей {len(insights.get('pains') or [])}, "
                      f"проблем сайта {len(insights.get('site_issues') or [])}")
            wm = _load(tmp_dir / "webmaster.json") or {}
            wm_rows = None
            if wm.get("found"):
                from webmaster_audit import render_webmaster_rows
                wm_rows = render_webmaster_rows(wm)
                if wm_rows:
                    print(f"  Вебмастер: быстрых побед {len(wm.get('quick_wins') or [])}")
            prcy_rows = filter_prcy_rows(
                probs.read_text(encoding="utf-8") if probs.exists() else None,
                bool(metrika), a.brand)
            all_problems = combine_problem_rows(combine_problem_rows(combine_problem_rows(
                prcy_rows, metrika_rows), site_rows), wm_rows)
            html, missing = inject_auto_blocks(
                html, bench.read_text(encoding="utf-8") if bench.exists() else None,
                all_problems)
            # кейсы с сайта Акулы — по нише клиента (только для бренда acoola)
            if a.brand == "acoola":
                try:
                    import acoola_cases
                    bx = _load(tmp_dir / "bitrix.json") or {}
                    niche = niche_text_from_bitrix(bx) or domain_from_bitrix(bx)
                    cases = acoola_cases.pick(niche)
                    if cases:
                        html, injected = acoola_cases.inject_cases(
                            html, acoola_cases.render_cases_html(cases))
                        mark_note = "" if injected else " (маркер AUTO:CASES не найден!)"
                        print(f"  кейсы подобраны по нише «{niche[:50]}»{mark_note}: "
                              + ", ".join(c.get("title", "?")[:25] for c in cases))
                except Exception as e:  # noqa: BLE001 — кейсы не должны ронять сборку
                    print(f"  ⚠ кейсы не подобраны: {e}")
            # факты в слайды: плейсхолдеры + баннер просадки трафика
            data = _load(tmp_dir / "kp_data.json") or {}
            subs = deck_substitutions(data, datetime.now().strftime("%d.%m.%Y"))
            spec = _load(tmp_dir / "smeta.json")
            subs.update(smeta_substitutions(spec))
            subs.update(benchmark_substitutions(_load(tmp_dir / "audit.json")))
            subs.update(offer_substitutions(metrika, spec))
            bx_data = _load(tmp_dir / "bitrix.json") or {}
            if bx_data.get("manager"):
                subs["{{МЕНЕДЖЕР}}"] = bx_data["manager"]
            for ph, val in subs.items():
                html = html.replace(ph, val)
            drop_html = render_traffic_drop(data, metrika)
            if MARK_TRAFFIC in html:
                html = html.replace(MARK_TRAFFIC, drop_html or
                    '<div class="pb-txt">Главные точки роста — в аудите '
                    'на следующих слайдах.</div>')
            if pains_html and MARK_PAINS in html:
                html = html.replace(MARK_PAINS, pains_html)
            # слайд «Что мешает» — только реальные данные клиента
            blockers = render_blockers_html(_load(tmp_dir / "audit.json"), metrika, insights)
            if blockers and MARK_BLOCKERS in html:
                html = html.replace(MARK_BLOCKERS, blockers)
            # прогноз — от фактической конверсии Метрики; нет данных — честная заглушка
            forecast = render_forecast_html(metrika)
            if MARK_FORECAST in html:
                html = html.replace(MARK_FORECAST, forecast or FORECAST_FALLBACK_ROW)
            # графики из данных: спарклайн органики + бар-чарт ИКС
            trend_svg = render_trend_svg(metrika)
            if MARK_TREND in html:
                html = html.replace(MARK_TREND, trend_svg or "")
            shot = tmp_dir / "site.png"
            if MARK_SHOT in html:
                if shot.exists():
                    import base64
                    b64 = base64.b64encode(shot.read_bytes()).decode()
                    html = html.replace(MARK_SHOT,
                        embed_screenshot_html(b64, data.get("domain") or ""))
                else:
                    html = html.replace(MARK_SHOT, "")
            if MARK_PSHOTS in html:
                html = html.replace(MARK_PSHOTS, render_problem_shots(tmp_dir, metrika) or "")
            if MARK_SOURCES in html:
                html = html.replace(MARK_SOURCES, render_sources_svg(metrika) or
                    '<div style="font-size:12px;color:#717885;">нужен доступ к Метрике</div>')
            if MARK_GEO in html:
                html = html.replace(MARK_GEO, render_geo_svg(metrika) or "")
            iks_svg = render_iks_bars(_load(tmp_dir / "audit.json"))
            if MARK_IKS in html:
                html = html.replace(MARK_IKS, iks_svg or
                    '<div style="font-size:12px;color:#717885;">данных по конкурентам нет</div>')
            # клиент никогда не должен увидеть {{ПЛЕЙСХОЛДЕР}}
            html, left = scrub_placeholders(html)
            if left:
                print(f"  ⚠ вычищено незаполненных плейсхолдеров: {left} "
                      f"(данных в брифе не нашлось)")
            # нумерация по факту — после ВСЕХ вставок
            html = renumber_pagenums(html)
            dst.write_text(html, encoding="utf-8")
            if missing:
                print(f"  ⚠ маркеры {missing} в эталоне не найдены — вставь фрагменты вручную "
                      f"(карта слайдов: SEO-KP-PLAYBOOK.md)")
        elif stage == "polish":
            if a.no_polish:
                mark(stage, "skipped")
                continue
            if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")):
                print("  ⚠ нет LLM-ключа — полировка пропущена")
                mark(stage, "skipped")
                continue
            try:
                _run("kp_polish.py", [str(tmp_dir)], tmp_dir)
            except RuntimeError as e:
                print(f"  ⚠ полировка не удалась ({e}) — дека остаётся как после scaffold")
                mark(stage, "skipped")
                continue
        elif stage == "smeta":
            import kp_smeta
            spec_path = tmp_dir / "smeta.json"
            if spec_path.exists():
                # ручные правки сейлса священны — только пересобираем xlsx
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                print("  smeta.json уже есть — пересобираю xlsx без перезаписи спеки")
            else:
                bx = _load(tmp_dir / "bitrix.json") or {}
                preset_key = preset_for_brief(bx.get("brief_services"))
                spec = {"client": domain_from_bitrix(bx) or tmp_dir.name,
                        "brand": "Acoola Team" if a.brand == "acoola" else "Belberry",
                        "deadline": "", "flags": {"logo_discount": False, "fast_pay": True},
                        **kp_smeta.PRESETS[preset_key]}
                spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
                print(f"  пресет «{preset_key}» (тарифы матрицы) — состав и суммы "
                      f"подтвердить со сметчиком")
            kp_smeta.write_xlsx(spec, tmp_dir / f"Смета_{spec['client']}.xlsx")
        mark(stage)

    print("\nГотово. Дальше руками:")
    print(f"  1. Чек-лист: {tmp_dir / 'kp_data.json'} → manual_checklist")
    print(f"  2. Смета: python3 kp_smeta.py clients/{tmp_dir.name} --init --service seo"
          f" → правка smeta.json → python3 kp_smeta.py clients/{tmp_dir.name}")
    print(f"  3. Цены из сметы → kp.html")
    print(f"  4. bash build.sh clients/{tmp_dir.name} \"КП Belberry — {tmp_dir.name}\"")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("deal_id", type=int)
    p.add_argument("--client")
    p.add_argument("--brand", choices=["belberry", "acoola"], default="belberry",
                   help="шаблон деки: Belberry (медицина) или Acoola Team (остальные ниши)")
    p.add_argument("--competitors", nargs="*", default=[])
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--prodoctorov", nargs="*", default=[])
    p.add_argument("--skip-metrika", action="store_true")
    p.add_argument("--skip-prodoctorov", action="store_true")
    p.add_argument("--no-polish", action="store_true",
                   help="без LLM-полировки текстов (быстрее/дешевле)")
    p.add_argument("--status", action="store_true")
    p.add_argument("--force", help="имя стадии или all")
    return run_pipeline(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())
