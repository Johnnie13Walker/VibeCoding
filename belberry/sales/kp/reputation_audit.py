#!/usr/bin/env python3
"""reputation_audit.py — автосбор репутационной выдачи для ORM-КП.

Что собирает НАДЁЖНО (без выдумки):
  • площадки в выдаче по запросу «<бренд> отзывы» (DuckDuckGo HTML, без ключа);
  • классификацию площадок по типам (гео-сервисы / медагрегаторы / отзовики /
    соцсети / СМИ / прочее) — для слайда «виды ресурсов в выдаче»;
  • присутствие/отсутствие на ключевых площадках;
  • рейтинг и число отзывов с ПроДокторов (GET, Schema.org) — если карточка в выдаче.

Что НЕ собирает (парсить надёжно нельзя — Яндекс.Карты/2ГИС за JS и антиботом):
  • точные звёзды по каждой площадке и тональность отзывов — это ручные зоны КП.

    python3 reputation_audit.py "<бренд>" [город]   # пишет reputation.json
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
DDG = "https://html.duckduckgo.com/html/"

# домен → (тип, человекочитаемое имя площадки). Порядок проверки — по вхождению.
PLATFORM_TYPES: dict[str, tuple[str, str]] = {
    # гео-сервисы и карты
    "yandex.ru": ("гео-сервисы", "Яндекс.Карты"),
    "2gis.ru": ("гео-сервисы", "2ГИС"),
    "zoon.ru": ("гео-сервисы", "Zoon"),
    "flamp.ru": ("гео-сервисы", "Flamp"),
    "google.com": ("гео-сервисы", "Google Карты"),
    # медицинские агрегаторы
    "prodoctorov.ru": ("медагрегаторы", "ПроДокторов"),
    "napopravku.ru": ("медагрегаторы", "НаПоправку"),
    "doctu.ru": ("медагрегаторы", "Doctu"),
    "like.doctor": ("медагрегаторы", "Like.Doctor"),
    "docdoc.ru": ("медагрегаторы", "DocDoc"),
    "sberhealth.ru": ("медагрегаторы", "СберЗдоровье"),
    "32top.ru": ("медагрегаторы", "32top"),
    "topdent.ru": ("медагрегаторы", "TopDent"),
    "1dentist.ru": ("медагрегаторы", "1Dentist"),
    "gidpozubam.ru": ("медагрегаторы", "ГидПоЗубам"),
    "stomatologija.su": ("медагрегаторы", "Стоматология.су"),
    "dentistfind.ru": ("медагрегаторы", "DentistFind"),
    "fadent.ru": ("медагрегаторы", "FaDent"),
    # отзовики
    "otzovik.com": ("отзовики", "Otzovik"),
    "irecommend.ru": ("отзовики", "iRecommend"),
    "otzyvru.com": ("отзовики", "OtzyvRu"),
    "otzyv.ru": ("отзовики", "Otzyv.ru"),
    "yell.ru": ("отзовики", "Yell"),
    "ocompanii.net": ("отзовики", "О Компании"),
    # соцсети
    "vk.com": ("соцсети", "ВКонтакте"),
    "ok.ru": ("соцсети", "Одноклассники"),
    "t.me": ("соцсети", "Telegram"),
    "dzen.ru": ("соцсети", "Дзен"),
}
TYPE_ORDER = ["гео-сервисы", "медагрегаторы", "отзовики", "соцсети", "СМИ", "прочее"]


def ddg_domains(query: str, limit: int = 25) -> list[tuple[str, str, str]]:
    """Выдача DuckDuckGo: [(домен, url, заголовок)] по запросу. Ошибка → []."""
    try:
        data = urllib.parse.urlencode({"q": query, "kl": "ru-ru"}).encode()
        req = urllib.request.Request(DDG, data=data, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            h = r.read().decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return []
    out, seen = [], set()
    for m in re.finditer(
            r'result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', h, re.S):
        href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        um = re.search(r"uddg=([^&]+)", href)
        real = urllib.parse.unquote(um.group(1)) if um else href
        dom = urllib.parse.urlparse(real).netloc.replace("www.", "")
        if dom and dom not in seen:
            seen.add(dom)
            out.append((dom, real, title))
        if len(out) >= limit:
            break
    return out


def classify(domain: str) -> tuple[str, str]:
    """(тип, имя площадки) по домену; неизвестный медиа-домен → СМИ/прочее."""
    for key, (typ, name) in PLATFORM_TYPES.items():
        if domain == key or domain.endswith("." + key) or key in domain:
            return typ, name
    # эвристика СМИ: новостные TLD/слова
    if re.search(r"(news|gazeta|ria|tass|kommersant|rbc|vc\.ru|\.media)", domain):
        return "СМИ", domain
    return "прочее", domain


def prodoctorov_rating(url: str) -> dict | None:
    """Рейтинг и отзывы с карточки ПроДокторов (Schema.org). Недоступно → None."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            h = r.read().decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return None
    rt = re.search(r'itemprop="ratingValue"\s*content="([0-9.]+)"', h)
    rv = re.search(r'itemprop="reviewCount"\s*content="(\d+)"', h)
    if not rt:
        tm = re.search(r"<title>(.*?)</title>", h, re.S)
        rv = rv or (re.search(r"(\d+)\s*отзыв", tm.group(1)) if tm else None)
    return {"rating": rt.group(1) if rt else None,
            "reviews": int(rv.group(1)) if rv else None}


def aggregate(results: list[tuple[str, str, str]], brand: str,
              city: str, own_domain: str = "") -> dict:
    """Чистая сборка среза из выдачи (без сети): площадки, типы, ПроДокторов.

    Собственный домен клиента — не площадка отзывов, исключаем.
    """
    own = (own_domain or "").replace("www.", "").lower()
    platforms, counts, pd_url = [], {t: 0 for t in TYPE_ORDER}, None
    for dom, url, _title in results:
        if own and (dom == own or dom.endswith("." + own)):
            continue
        typ, name = classify(dom)
        counts[typ] = counts.get(typ, 0) + 1
        platforms.append({"domain": dom, "type": typ, "name": name, "url": url})
        if dom == "prodoctorov.ru" and pd_url is None:
            pd_url = url
    return {
        "brand": brand, "city": city,
        "query": f"{brand} отзывы" + (f" {city}" if city else ""),
        "platforms": platforms,
        "type_counts": {t: counts[t] for t in TYPE_ORDER if counts.get(t)},
        "prodoctorov_url": pd_url,
        "found": bool(platforms),
    }


def collect(brand: str, city: str = "", own_domain: str = "") -> dict:
    """Репутационный срез бренда: площадки выдачи, типы, ПроДокторов (с сетью)."""
    q = f"{brand} отзывы" + (f" {city}" if city else "")
    data = aggregate(ddg_domains(q), brand, city, own_domain)
    pd_url = data.pop("prodoctorov_url", None)
    data["prodoctorov"] = None
    if pd_url:
        pd = prodoctorov_rating(pd_url)
        if pd:
            pd["url"] = pd_url
            data["prodoctorov"] = pd
    return data


def render_resource_types_svg(data: dict, accent: str = "#3086FB",
                              width: int = 520, height: int = 230) -> str | None:
    """Бар-чарт «виды ресурсов в выдаче» из type_counts (маркер AUTO:REP_TYPES)."""
    counts = (data or {}).get("type_counts") or {}
    rows = [(t, n) for t, n in counts.items() if n]
    if not rows:
        return None
    import html as _h
    mx = max(n for _, n in rows)
    pad_b, pad_t, gap = 34, 16, 18
    bw = (width - gap * (len(rows) + 1)) / len(rows)
    plot_h = height - pad_b - pad_t
    bars = []
    for i, (t, n) in enumerate(rows):
        x = gap + i * (bw + gap)
        bh = max(6, plot_h * n / mx)
        y = pad_t + plot_h - bh
        bars.append(
            f'<rect x="{x:.0f}" y="{y:.0f}" width="{bw:.0f}" height="{bh:.0f}" '
            f'rx="5" fill="{accent}"/>'
            f'<text x="{x + bw / 2:.0f}" y="{y - 6:.0f}" text-anchor="middle" '
            f'font-size="15" font-weight="800" fill="#313131">{n}</text>'
            f'<text x="{x + bw / 2:.0f}" y="{height - 12:.0f}" text-anchor="middle" '
            f'font-size="10.5" fill="#717885">{_h.escape(t)}</text>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'xmlns="http://www.w3.org/2000/svg">' + "".join(bars) + "</svg>")


def render_platforms_html(data: dict, accent: str = "#3086FB",
                          limit: int = 9) -> str | None:
    """Список найденных площадок с типом (маркер AUTO:REP_PLATFORMS)."""
    platforms = (data or {}).get("platforms") or []
    if not platforms:
        return None
    import html as _h
    rows = []
    for p in platforms[:limit]:
        rows.append(
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'gap:14px;padding:11px 4px;border-bottom:1px solid #EDF1F7;">'
            f'<span style="font-size:13.5px;font-weight:700;color:#313131;">'
            f'{_h.escape(p.get("name", ""))}</span>'
            f'<span style="font-size:11px;font-weight:700;color:{accent};'
            f'background:rgba(0,0,0,.03);border-radius:999px;padding:3px 11px;">'
            f'{_h.escape(p.get("type", ""))}</span></div>')
    return "".join(rows)


STRATEGY_BY_TYPE = {
    "гео-сервисы": "наращивание рейтинга",
    "медагрегаторы": "наращивание позитива",
    "отзовики": "нивелирование негатива",
    "соцсети": "работа от лица бренда",
    "СМИ": "мониторинг упоминаний",
}


def render_strategy_rows(data: dict, accent: str = "#3086FB",
                         limit: int = 9) -> str | None:
    """Строки таблицы «рейтинг и стратегия» (маркер AUTO:REP_STRATEGY).

    Колонка площадок — авто из выдачи; оценка/отзывы/тональность — «—»
    (снимаются вручную при аудите); стратегия — по типу площадки.
    """
    platforms = (data or {}).get("platforms") or []
    if not platforms:
        return None
    import html as _h
    pd = (data or {}).get("prodoctorov") or {}
    rows = []
    for p in platforms[:limit]:
        # для ПроДокторов подставляем снятую оценку, остальное — ручное
        is_pd = p.get("domain") == "prodoctorov.ru"
        rating = (_h.escape(str(pd.get("rating"))) if is_pd and pd.get("rating")
                  else "—")
        reviews = (str(pd.get("reviews")) if is_pd and pd.get("reviews") else "—")
        strat = STRATEGY_BY_TYPE.get(p.get("type", ""), "наращивание позитива")
        rows.append(
            f'<tr><td>{_h.escape(p.get("name", ""))}</td>'
            f'<td class="right num">{rating}</td>'
            f'<td class="right num">{reviews}</td>'
            f'<td>—</td>'
            f'<td style="color:{accent};font-weight:600;">{strat}</td></tr>')
    return "".join(rows)


def reputation_summary(data: dict) -> str:
    """Короткий вывод о репутационной выдаче (для {{ОРМ_ВЫВОД}}). Нет данных → ''."""
    platforms = (data or {}).get("platforms") or []
    if not platforms:
        return ""
    n = len(platforms)
    counts = data.get("type_counts") or {}
    review_sites = counts.get("отзовики", 0) + counts.get("медагрегаторы", 0)
    if review_sites:
        return (f"В выдаче по «{data.get('brand', 'бренд')} отзывы» — {n} площадок, "
                f"из них {review_sites} отзовиков и агрегаторов: первое впечатление "
                f"пациента формируют сторонние ресурсы, а не ваш сайт. Берём их под контроль.")
    return (f"В выдаче по «{data.get('brand', 'бренд')} отзывы» — {n} площадок; "
            f"закрепляем присутствие бренда и управляем оценками на приоритетных.")


def main() -> int:
    if len(sys.argv) < 2:
        print('usage: reputation_audit.py "<бренд>" [город]')
        return 1
    brand = sys.argv[1]
    city = sys.argv[2] if len(sys.argv) > 2 else ""
    data = collect(brand, city)
    json.dump(data, open("reputation.json", "w"), ensure_ascii=False, indent=2)
    print(f"# Репутационная выдача: {data['query']}")
    print(f"  площадок: {len(data['platforms'])}  "
          f"типы: {data['type_counts']}")
    for p in data["platforms"]:
        print(f"  [{p['type']:13}] {p['name']:18} {p['domain']}")
    if data["prodoctorov"]:
        print(f"  ПроДокторов: рейтинг={data['prodoctorov'].get('rating')} "
              f"отзывов={data['prodoctorov'].get('reviews')}")
    print("→ reputation.json   (точные звёзды/тональность по площадкам — ручные зоны КП)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
