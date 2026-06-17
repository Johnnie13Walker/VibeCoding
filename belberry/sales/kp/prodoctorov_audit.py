#!/usr/bin/env python3
"""prodoctorov_audit.py — локальный аудит клиник по ПроДокторов (для слайда конкурентов).

Тянет НАБЛЮДАЕМЫЕ факты с карточки ПроДокторов: число врачей, число отзывов,
рейтинг (микроразметка Schema.org). URL карточки берётся из поиска (ручной шаг).

⚠️ Яндекс.Карты НЕ скриптуются (302 / JS-рендер) — рейтинг с Карт берём через
их API или вручную. ПроДокторов отдаётся обычным GET.

Использование:
    python3 prodoctorov_audit.py <url_prodoctorov> [url2 ...]
    python3 prodoctorov_audit.py https://prodoctorov.ru/spb/lpu/38705-mir-semi/
"""
import re
import sys
import json
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def prodoctorov(url: str) -> dict:
    out = {"url": url, "doctors": None, "reviews": None, "rating": None}
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            h = r.read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
        return out

    # итог клиники — в <title>: «… - N врачей, M отзывов | …»
    tm = re.search(r"<title>(.*?)</title>", h, re.S)
    title = tm.group(1) if tm else ""
    d = re.search(r"(\d+)\s*врач", title)
    rv = re.search(r"(\d+)\s*отзыв", title)
    rt = re.search(r'itemprop="ratingValue"\s*content="([0-9.]+)"', h)  # оценка ПроДокторов
    out["name"] = title.split(" - ")[0].strip() if title else None
    out["doctors"] = int(d.group(1)) if d else None
    out["reviews"] = int(rv.group(1)) if rv else None
    out["rating"] = rt.group(1) if rt else None  # шкала ПроДокторов своя
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: prodoctorov_audit.py <url_prodoctorov> [...]")
        sys.exit(1)
    res = [prodoctorov(u) for u in sys.argv[1:]]
    json.dump(res, open("prodoctorov.json", "w"), ensure_ascii=False, indent=2)
    print("# Локальный аудит (ПроДокторов)")
    for r in res:
        if r.get("error"):
            print(f"  ⚠ {r['url']}: {r['error']}")
        else:
            print(f"  {r.get('name','?')[:34]:34} врачей={r['doctors']}  отзывов={r['reviews']}  оценка={r['rating']}")
    print("→ prodoctorov.json   (Яндекс.Карты — отдельно, через API/вручную)")


if __name__ == "__main__":
    main()
