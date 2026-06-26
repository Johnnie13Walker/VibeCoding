"""Репутация клиента из публичных агрегаторов — outside-in сигнал для аудита.

Модульно: каждый источник независим, любой сбой → None, аудит идёт дальше.
- ProDoctorov (медтема, БЕЗ ключа): рейтинг + число отзывов клиники. Поиск через листинг
  города + матч по названию (search-API у ProDoctorov нет/404). Город берём из снимка сайта.
- 2ГИС (TODO, нужен бесплатный ключ): рейтинг/отзывы + конкуренты в нише/городе.

Включается флагом SCC_REPUTATION=1 (по умолчанию вкл). Любая ошибка тихо None.
"""

from __future__ import annotations

import html as _html
import os
import re

import requests

try:
    import urllib3

    urllib3.disable_warnings()
except Exception:  # pragma: no cover
    pass

REPUTATION_ON = os.environ.get("SCC_REPUTATION", "1") == "1"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_TIMEOUT = int(os.environ.get("SCC_REP_TIMEOUT", "12"))

# Кириллица → латиница для slug города ProDoctorov (vologda, moskva, sankt-peterburg).
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya", "-": "-", " ": "-",
}


def _translit(s: str) -> str:
    return "".join(_TRANSLIT.get(c, c) for c in (s or "").lower()).strip("-")


def _city_slug_from_site(site_text: str | None) -> str | None:
    """Город из текста главной сайта клиента → slug ProDoctorov. «г. Вологда» → vologda."""
    if not site_text:
        return None
    m = re.search(r"\bг\.?\s*([А-ЯЁ][а-яё-]{2,})", site_text) or \
        re.search(r"город\s+([А-ЯЁ][а-яё-]{2,})", site_text)
    return _translit(m.group(1)) if m else None


def _name_tokens(name: str) -> set[str]:
    # значимые слова названия (без орг-форм и общих слов)
    stop = {"ооо", "ип", "зао", "ао", "клиника", "клиники", "центр", "медицинский", "медцентр",
            "стоматология", "стоматологическая", "сеть", "группа", "компания", "the", "и"}
    words = re.findall(r"[a-zа-яё0-9]{3,}", (name or "").lower())
    return {w for w in words if w not in stop}


def _strip_html(t: str) -> str:
    t = re.sub(r"<[^>]+>", " ", t or "")
    return _html.unescape(re.sub(r"\s+", " ", t)).strip()


def _get(url: str, params: dict | None = None) -> str | None:
    try:
        r = requests.get(url, headers=_HEADERS, params=params, timeout=_TIMEOUT, verify=False)
    except Exception:
        return None
    if r.status_code == 200 and "html" in r.headers.get("Content-Type", "").lower():
        return r.text
    return None


def prodoctorov(company_name: str | None, city_slug: str | None) -> dict | None:
    """Рейтинг + число отзывов клиники на ProDoctorov. Матч по названию в листинге города."""
    if not company_name or not city_slug:
        return None
    listing = _get(f"https://prodoctorov.ru/{city_slug}/lpu/")
    if not listing:
        return None
    # пары (url, видимое название) из карточек ЛПУ
    cards = re.findall(r'href="(/' + re.escape(city_slug) + r'/lpu/\d+-[a-z0-9-]+/)"[^>]*>(.*?)</a>',
                       listing, re.S)
    want = _name_tokens(company_name)
    # доп. матч по латинице (название → translit, как в slug)
    want_translit = {_translit(w) for w in want}
    best, best_score, best_name = None, 0, None
    for href, label in cards:
        title = _strip_html(label)
        toks = _name_tokens(title)
        score = len(toks & want)
        if not score:  # запасной матч по slug (translit)
            slug = href.rstrip("/").split("-", 1)[-1]
            if any(t and t in slug for t in want_translit):
                score = 1
        if score > best_score:
            best, best_score, best_name = href, score, title
    if not best:
        return None
    own = _pd_clinic(best)
    if not own:
        return {"source": "prodoctorov", "found": False, "url": f"https://prodoctorov.ru{best}", "name": best_name}
    # конкуренты: другие клиники города из листинга (слаги клиник, без /vrachi/), сэмпл с их рейтингом
    comp_hrefs = []
    for h in re.findall(r'/' + re.escape(city_slug) + r'/lpu/\d+-[a-z0-9-]+/', listing):
        if h != best and h not in comp_hrefs:
            comp_hrefs.append(h)
        if len(comp_hrefs) >= int(os.environ.get("SCC_PD_COMPETITORS", "4")):
            break
    competitors = []
    for h in comp_hrefs:
        c = _pd_clinic(h)
        if c and (c.get("rating") or c.get("reviews_count")):
            competitors.append(c)
    return {"source": "prodoctorov", **own, "competitors": competitors}


def _pd_clinic(href: str) -> dict | None:
    """Имя+рейтинг+отзывы одной клиники ProDoctorov по её href."""
    page = _get(f"https://prodoctorov.ru{href}")
    if not page:
        return None
    rating = None
    mr = re.search(r"stars_rate.{0,400}?([0-9]{1,2}[.,][0-9])", page, re.S)
    if mr:
        rating = mr.group(1).replace(",", ".")
    mt = re.search(r"<title[^>]*>(.*?)</title>", page, re.S)
    title_txt = _strip_html(mt.group(1)) if mt else ""
    reviews = None
    mrev = re.search(r"([0-9][0-9 ]{0,6})\s*отзыв", title_txt)
    if mrev:
        reviews = int(mrev.group(1).replace(" ", ""))
    name = re.split(r"\s[-—]\s", title_txt)[0][:80] if title_txt else None
    return {"found": True, "url": f"https://prodoctorov.ru{href}", "name": name,
            "rating": rating, "reviews_count": reviews}


# ── Яндекс.Карты через Apify-актор (zen-studio/yandex-maps-scraper) ────────────
APIFY_TOKEN = os.environ.get("SCC_APIFY_TOKEN", "")
_YANDEX_ACTOR = "zen-studio~yandex-maps-scraper"


def _city_name_from_site(site_text: str | None) -> str | None:
    if not site_text:
        return None
    m = re.search(r"\bг\.?\s*([А-ЯЁ][а-яё-]{2,})", site_text) or \
        re.search(r"город\s+([А-ЯЁ][а-яё-]{2,})", site_text)
    return m.group(1) if m else None


def yandex_maps(brand: str | None, city: str | None) -> dict | None:
    """Рейтинг + число отзывов клиента на Яндекс.Картах (через Apify). Лёгкий вызов:
    без текстов отзывов, маленький лимит — нужен только рейтинг/счётчик."""
    if not APIFY_TOKEN or not brand:
        return None
    q = f"{brand} {city}".strip() if city else brand
    try:
        r = requests.post(
            f"https://api.apify.com/v2/acts/{_YANDEX_ACTOR}/run-sync-get-dataset-items",
            params={"token": APIFY_TOKEN},
            json={"query": [q], "maxResults": int(os.environ.get("SCC_YA_MAX", "6")),
                  "includeReviews": False, "language": "ru"},
            timeout=int(os.environ.get("SCC_YA_TIMEOUT", "180")),
        )
    except Exception:
        return None
    if r.status_code not in (200, 201):
        return None
    try:
        items = r.json()
    except Exception:
        return None
    if not isinstance(items, list) or not items:
        return None
    want = _name_tokens(brand)
    # клиент = лучший матч по названию, при равенстве — больше отзывов (главный филиал)
    def score(it):
        toks = _name_tokens(it.get("title") or it.get("name") or "")
        return (len(toks & want), int(it.get("ratingsCount") or it.get("reviewsCount") or 0))
    items_sorted = sorted(items, key=score, reverse=True)
    client = items_sorted[0]
    if score(client)[0] == 0:
        return None
    def fmt(it):
        rat = it.get("rating")
        return {"name": it.get("title") or it.get("name"),
                "rating": round(float(rat), 1) if rat is not None else None,
                "reviews_count": it.get("ratingsCount") or it.get("reviewsCount"),
                "url": it.get("url")}
    # конкуренты = прочие из выдачи с рейтингом, не совпадающие с клиентом
    competitors = [fmt(it) for it in items_sorted[1:5]
                   if (it.get("rating") or it.get("ratingsCount")) and it.get("title") != client.get("title")]
    return {"source": "yandex_maps", "found": True, **fmt(client), "competitors": competitors}


def collect(company_name: str | None, site_text: str | None) -> dict | None:
    """Снимок репутации по доступным источникам: ProDoctorov (медтема, без ключа) +
    Яндекс.Карты (через Apify, любой бизнес). Каждый источник независим, сбой → пропуск."""
    if not REPUTATION_ON:
        return None
    out = {}
    try:
        pd = prodoctorov(company_name, _city_slug_from_site(site_text))
        if pd:
            out["prodoctorov"] = pd
    except Exception:
        pass
    try:
        ya = yandex_maps(company_name, _city_name_from_site(site_text))
        if ya:
            out["yandex_maps"] = ya
    except Exception:
        pass
    return out or None
