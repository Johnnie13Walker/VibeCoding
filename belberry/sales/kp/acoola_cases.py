#!/usr/bin/env python3
"""Автоподбор кейсов с сайта acoola.team для деки КП.

Сбор: страница https://acoola.team/projects/ отрендерена сервером (Nuxt SSR),
карточки кейсов лежат в HTML блоками ``case-item``:
  - ``case-item__name``  — название + ссылка на кейс
  - ``case-item__tag``   — услуга (SEO / Контекстная реклама / SMM / ORM / …)
  - ``case-item__desk``  — сфера/отрасль клиента (есть не у всех)
  - ``case-item__info-prop-label`` + ``…-desc`` — пары «показатель — пояснение»

Железное правило: цифры результата берём дословно с сайта; если у кейса
цифр нет — список metrics пустой, ничего не выдумываем.

CLI:
  python3 acoola_cases.py refresh                 — пересобрать кэш с сайта
  python3 acoola_cases.py pick "<ниша>" [--services seo,smm]  — топ-3 кейса
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SITE = "https://acoola.team"
INDEX_URL = SITE + "/projects/"
CACHE_PATH = Path(__file__).resolve().parent / "acoola_cases.json"

# Маркеры в шаблоне kp.html: фрагмент render_cases_html() вставляется
# ВМЕСТО содержимого между ними (сами маркеры можно удалить при вставке).
MARK_CASES_BEGIN = "<!--AUTO:CASES-->"
MARK_CASES_END = "<!--/AUTO:CASES-->"

_TAG_RE = re.compile(r"<[^>]+>")
_CARD_SPLIT = '<div class="case-item --cursor">'
_NAME_RE = re.compile(r'<a href="(/projects/[^"]+)"[^>]*>(.*?)</a>', re.S)
_TAGS_RE = re.compile(r'case-item__tag[^"]*">(.*?)</div>', re.S)
_DESK_RE = re.compile(r'case-item__desk[^"]*">(.*?)</div>', re.S)
_PROP_RE = re.compile(
    r'case-item__info-prop-label[^"]*">(.*?)</div>\s*'
    r'<div class="case-item__info-prop-desc[^"]*">(.*?)</div>', re.S)
_DIGIT_RE = re.compile(r"\d")
# компактная «цифра» для крупного шрифта плитки: 140%, 1 374 ₽, в 2,4 раза…
_FIGURE_RE = re.compile(
    r"(?:[вс]\s+)?[+\-−×x]?\d[\d\s.,:]*\s*"
    r"(?:%|₽|руб[а-яё]*|раз[а-яё]*|млн\s*₽?|тыс[а-яё.]*|шт|звёзд[а-яё]*|звезд[а-яё]*|мин[а-яё.]*|aed|\$)?",
    re.I)

# суффиксы для грубой нормализации русских слов (без сторонних библиотек)
_SUFFIXES = ("иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими",
             "ах", "ях", "ов", "ев", "ие", "ые", "ий", "ый", "ая", "яя",
             "ое", "ее", "ой", "ей", "ам", "ям", "ом", "ем",
             "ы", "и", "а", "я", "о", "е", "у", "ю", "ь")


# ── сбор с сайта ──────────────────────────────────────────────────────────────

def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (kp-builder)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _text(fragment: str) -> str:
    """HTML-фрагмент → чистый текст одной строкой."""
    txt = html_mod.unescape(_TAG_RE.sub(" ", fragment))
    return re.sub(r"\s+", " ", txt.replace("\xa0", " ").replace(" ", " ")).strip()


def _client_from_title(title: str) -> str:
    """«Кейс Kenner: контекст…» → «Kenner»; иначе само название."""
    m = re.match(r"Кейс\s+([^:]{2,40}):", title)
    if m:
        return m.group(1).strip()
    return title.strip()


def parse_cases(index_html: str) -> list[dict]:
    """Разбор страницы /projects/ в список кейсов (pure, без сети)."""
    cases: list[dict] = []
    seen: set[str] = set()
    for chunk in index_html.split(_CARD_SPLIT)[1:]:
        m = _NAME_RE.search(chunk)
        if not m:
            continue
        url = SITE + m.group(1)
        if url in seen:
            continue
        seen.add(url)
        title = _text(m.group(2))
        services = [t for t in (_text(x) for x in _TAGS_RE.findall(chunk)) if t]
        desks = [d for d in (_text(x) for x in _DESK_RE.findall(chunk)) if d]
        summary = ""
        metrics: list[dict] = []
        for raw_label, raw_desc in _PROP_RE.findall(chunk):
            label, desc = _text(raw_label), _text(raw_desc)
            if not label and not desc:
                continue
            if label.lower() == "о проекте":
                summary = summary or desc
            elif _DIGIT_RE.search(label + " " + desc):
                # дословные цифры с сайта — ничего не пересчитываем
                metrics.append({"label": label, "text": desc})
            elif not summary:
                summary = (label + " " + desc).strip()
        cases.append({
            "title": title,
            "client": _client_from_title(title),
            "url": url,
            "niche": desks[0] if desks else "",
            "services": services,
            "summary": summary,
            "metrics": metrics,
        })
    return cases


def refresh(cache_path: Path = CACHE_PATH) -> list[dict]:
    """Пересобрать кейсы с сайта и записать кэш с датой сбора."""
    cases = parse_cases(fetch(INDEX_URL))
    payload = {
        "collected_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": INDEX_URL,
        "count": len(cases),
        "cases": cases,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return cases


def load_cases(cache_path: Path = CACHE_PATH) -> list[dict]:
    """Кейсы из кэша; если кэша нет — собрать с сайта."""
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))["cases"]
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    return refresh(cache_path)


# ── подбор по нише ────────────────────────────────────────────────────────────

def _stem(word: str) -> str:
    w = word.lower().replace("ё", "е")
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[а-яёa-z0-9]{3,}", text.lower())}


def _stem_match(query_stem: str, hay_stems: set[str]) -> bool:
    for h in hay_stems:
        if query_stem == h:
            return True
        # «производств» ~ «производител»: общий префикс из 6 знаков
        if len(query_stem) >= 6 and len(h) >= 6 and query_stem[:6] == h[:6]:
            return True
    return False


def score_case(case: dict, niche_stems: set[str], services: list[str] | None) -> int:
    """Скоринг кейса: ниша ×3, услуга ×2, цифры +2, приоритет SEO +1."""
    score = 0
    title_niche = _stems(case.get("title", "") + " " + case.get("niche", ""))
    summary = _stems(case.get("summary", ""))
    for qs in niche_stems:
        if _stem_match(qs, title_niche):
            score += 3
        elif _stem_match(qs, summary):
            score += 1
    case_services = {s.lower() for s in case.get("services", [])}
    wanted = {s.strip().lower() for s in services} if services else set()
    for w in wanted:
        if any(w in cs or cs in w for cs in case_services):
            score += 2
    if case.get("metrics"):
        score += 2
    # для SEO-КП кейсы SEO в приоритете (по умолчанию движок — SEO-дека)
    if "seo" in case_services and (not wanted or "seo" in wanted):
        score += 1
    return score


def pick(niche_text: str, services: list[str] | None = None,
         cases: list[dict] | None = None, top: int = 3) -> list[dict]:
    """Топ-N кейсов под нишу клиента (стабильная сортировка по убыванию очков)."""
    if cases is None:
        cases = load_cases()
    niche_stems = _stems(niche_text)
    scored = [(score_case(c, niche_stems, services), i, c) for i, c in enumerate(cases)]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [dict(c, score=s) for s, _, c in scored[:top]]


# ── HTML-фрагмент для слайда кейсов ───────────────────────────────────────────

def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:—-")
    return cut + "…"


def _figure(metric: dict) -> tuple[str, str]:
    """(крупная цифра, подпись) из метрики кейса — дословно с сайта."""
    label, text = metric.get("label", ""), metric.get("text", "")
    if _DIGIT_RE.search(label) and len(label) <= 26:
        return label, _cut(text, 110)
    m = _FIGURE_RE.search(text)
    if m:
        return m.group(0).strip(), _cut(text, 110)
    return "", _cut((label + " " + text).strip(), 110)


def render_cases_html(cases: list[dict]) -> str:
    """Три плитки кейсов в вёрстке слайда (классы tile/tt/tn/tnum/tm/tcap)."""
    esc = html_mod.escape
    tiles: list[str] = []
    fills = ("tile fill", "tile", "tile fill")  # чередование как в эталоне
    for i, case in enumerate(cases[:3]):
        niche = case.get("niche") or " / ".join(case.get("services", []))
        num, caption = ("", "")
        if case.get("metrics"):
            num, caption = _figure(case["metrics"][0])
        title = case.get("title", "")
        # без описания: название кейса, а если оно совпадает с клиентом — ниша
        fallback = title if title != case.get("client") else (case.get("niche") or title)
        comment = _cut(case.get("summary") or fallback, 120)
        tiles.append(
            f'      <a class="{fills[i % 3]}" href="{esc(case.get("url", ""), quote=True)}" target="_blank">\n'
            f'        <div class="tt">{esc(_cut(niche, 48).upper())} ↗</div>\n'
            f'        <div class="tn">{esc(_cut(case.get("client", ""), 60))}</div>\n'
            f'        <div class="tnum">{esc(num)}</div>\n'
            f'        <div class="tm">{esc(caption)}</div>\n'
            f'        <div class="tcap">{esc(comment)}</div>\n'
            f'      </a>')
    return "\n".join(tiles)


def inject_cases(kp_html: str, fragment: str) -> tuple[str, bool]:
    """Вставка фрагмента между маркерами AUTO:CASES (вместо плиток-заглушек)."""
    b, e = kp_html.find(MARK_CASES_BEGIN), kp_html.find(MARK_CASES_END)
    if b < 0 or e < 0 or e < b:
        return kp_html, False
    return kp_html[:b] + fragment + kp_html[e + len(MARK_CASES_END):], True


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Кейсы acoola.team для деки КП")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("refresh", help="пересобрать кэш кейсов с сайта")
    pk = sub.add_parser("pick", help="подобрать топ-3 кейса под нишу")
    pk.add_argument("niche", help="ниша/ключевые слова клиента")
    pk.add_argument("--services", default="", help="услуги через запятую: seo,smm,…")
    a = p.parse_args(argv)

    if a.cmd == "refresh":
        cases = refresh()
        with_digits = sum(1 for c in cases if c["metrics"])
        print(f"Собрано кейсов: {len(cases)} (с цифрами: {with_digits}) → {CACHE_PATH.name}")
        return 0

    services = [s for s in a.services.split(",") if s.strip()] or None
    chosen = pick(a.niche, services=services)
    for c in chosen:
        print(f"[{c['score']}] {c['title']}")
        print(f"    ниша: {c['niche'] or '—'} | услуги: {', '.join(c['services']) or '—'}")
        for m in c["metrics"][:3]:
            print(f"    цифра: {m['label']} — {m['text'][:90]}")
        print(f"    {c['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
