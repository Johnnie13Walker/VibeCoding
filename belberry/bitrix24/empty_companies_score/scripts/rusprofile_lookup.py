#!/usr/bin/env python3
"""Поиск компаний на rusprofile.ru по названию — для триажа пустых реквизитов.

По дефолту lookup-only: запрашивает rusprofile, парсит первые результаты,
выводит таблицу с найденными ИНН/ОГРН/КПП/полное_название. НЕ пишет в Bitrix.

Для bulk-обновления реквизитов в Bitrix (после ручной проверки) — отдельный
шаг через `--apply-from <results.json>`: читает заранее проверенный мэппинг
`{company_id: {RQ_INN, RQ_KPP, RQ_OGRN, RQ_COMPANY_NAME}}` и делает
crm.requisite.update.

Запуск (lookup):
  /opt/openclaw/venvs/crm_company_merge/bin/python \\
  /opt/openclaw/repos/vibecoding/belberry/bitrix24/empty_companies_score/scripts/rusprofile_lookup.py \\
  --ids 2978,3534,5254,...  --out /tmp/rusprofile_results.json

Запуск (apply, после ручной проверки JSON):
  BITRIX_STATE_PATH=... /opt/openclaw/venvs/crm_company_merge/bin/python \\
  ... --apply-from /tmp/rusprofile_results.json
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from empty_companies_score.bitrix_client import BitrixClient  # noqa: E402
from empty_companies_score.config import BITRIX_STATE, PORTAL_BASE  # noqa: E402

DATA_DIR = Path("/opt/openclaw/data/empty_co")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ids", help="company_id через запятую")
    p.add_argument("--titles", help="напрямую title через `||` (если --ids не дан)")
    p.add_argument("--out", help="куда писать JSON-результаты lookup")
    p.add_argument("--apply-from", help="JSON с проверенными mapping → применить crm.requisite.update")
    p.add_argument("--throttle", type=float, default=2.5, help="пауза между запросами к rusprofile (сек)")
    args = p.parse_args()

    if args.apply_from:
        return _apply(Path(args.apply_from))

    bx = BitrixClient(BITRIX_STATE)
    targets = _resolve_targets(args.ids, args.titles, bx)
    print(f"[{_ts()}] lookup для {len(targets)} компаний (throttle={args.throttle}s) ...")
    results: list[dict] = []
    for cid, title in targets:
        print(f"\n[{_ts()}] #{cid} '{title}'")
        try:
            hits = _rusprofile_search(title)
        except Exception as e:  # noqa: BLE001
            print(f"  ! lookup error: {e}")
            results.append({"company_id": cid, "title_in_b24": title, "error": str(e)})
            continue
        if not hits:
            print("  ∅ ничего не найдено")
            results.append({"company_id": cid, "title_in_b24": title, "hits": []})
        else:
            for h in hits[:3]:
                print(f"  → {h.get('inn'):<12} {h.get('ogrn'):<14} '{h.get('name', '')[:80]}'")
            results.append({"company_id": cid, "title_in_b24": title, "hits": hits[:5]})
        time.sleep(args.throttle)

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"\n→ {args.out}")

    found = sum(1 for r in results if r.get("hits"))
    print(f"\n[{_ts()}] done: {found}/{len(results)} с хоть какими-то hits, {len(results) - found - sum(1 for r in results if r.get('error'))} пусто, {sum(1 for r in results if r.get('error'))} ошибок")
    return 0


def _resolve_targets(ids_arg: str | None, titles_arg: str | None, bx: BitrixClient) -> list[tuple[str, str]]:
    if titles_arg:
        return [(f"manual_{i}", t.strip()) for i, t in enumerate(titles_arg.split("||"))]
    if not ids_arg:
        print("--ids или --titles обязателен", file=sys.stderr)
        sys.exit(2)
    ids = [s.strip() for s in ids_arg.split(",") if s.strip()]
    out: list[tuple[str, str]] = []
    for cid in ids:
        r = bx.call("crm.company.get", [("id", cid)])
        if r.get("error_description") == "Not found":
            print(f"WARN #{cid} не найден в Bitrix, пропускаю", file=sys.stderr)
            continue
        c = r.get("result") or {}
        out.append((cid, (c.get("TITLE") or "").strip()))
    return out


def _rusprofile_search(query: str) -> list[dict]:
    """GET https://www.rusprofile.ru/search?query=... → парсим первые карточки."""
    url = "https://www.rusprofile.ru/search?" + urllib.parse.urlencode({"query": query})
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru,en;q=0.5",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        html = raw.decode("utf-8", errors="replace")
    return _parse_rusprofile(html)


def _parse_rusprofile(html: str) -> list[dict]:
    """Разметка search-страницы rusprofile [актуально 2026-05]:
        <div class="list-element">
          <a href="/id/<rusprofile_id>" class="list-element__title">ООО ...</a>
          <span class="list-element__text">директор ...</span>
          <div class="list-element__address">...</div>
          <div class="list-element__row-info">
            <span>ИНН: 5038070341</span>
            <span>ОГРН: 1095038004423</span>
            <span>Дата регистрации: 04.08.2009</span>
          </div>
        </div>
    Для ИП используется /ip/<id>. КПП на search-странице обычно не выводится.
    """
    blocks = html.split('<div class="list-element"')[1:50]
    hits: list[dict] = []
    for block in blocks:
        name_m = re.search(r'class="list-element__title"[^>]*>(.*?)</a>', block, re.DOTALL)
        inn_m = re.search(r'ИНН:\s*(\d{10}|\d{12})', block)
        ogrn_m = re.search(r'ОГРН(?:ИП)?:\s*(\d{13}|\d{15})', block)
        date_m = re.search(r'Дата регистрации:\s*([\d.]{10})', block)
        addr_m = re.search(r'class="list-element__address"[^>]*>([^<]+)</div>', block)
        rusprofile_url_m = re.search(r'href="(/(?:id|ip)/\d+)"', block)
        if not (name_m or inn_m):
            continue
        hits.append({
            "name": _clean_name(name_m.group(1)) if name_m else "",
            "inn": (inn_m.group(1) if inn_m else ""),
            "ogrn": (ogrn_m.group(1) if ogrn_m else ""),
            "date_reg": (date_m.group(1) if date_m else ""),
            "address": _unescape(addr_m.group(1).strip()) if addr_m else "",
            "rusprofile_url": ("https://www.rusprofile.ru" + rusprofile_url_m.group(1)) if rusprofile_url_m else "",
        })
    seen, dedup = set(), []
    for h in hits:
        key = h.get("inn") or h.get("name")
        if key in seen:
            continue
        seen.add(key)
        dedup.append(h)
    return dedup


def _unescape(s: str) -> str:
    return (s.replace("&quot;", '"').replace("&amp;", "&").replace("&#039;", "'")
            .replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ").strip())


def _clean_name(raw: str) -> str:
    """Title rusprofile приходит с <mark>...</mark> подсветками и переносами.
    Убираем теги, схлопываем пробелы."""
    txt = re.sub(r"<[^>]+>", "", raw)
    txt = re.sub(r"\s+", " ", txt)
    return _unescape(txt)


def _apply(mapping_path: Path) -> int:
    """JSON формат: список объектов {company_id, requisite_id?, RQ_INN, RQ_KPP, RQ_OGRN, RQ_COMPANY_NAME}.
    Если requisite_id не указан — берём первый существующий пустой реквизит компании."""
    bx = BitrixClient(BITRIX_STATE)
    mapping = json.loads(mapping_path.read_text())
    if not isinstance(mapping, list):
        print("apply_from JSON должен быть list", file=sys.stderr)
        return 2
    updated, skipped = [], []
    for item in mapping:
        cid = str(item["company_id"])
        inn = (item.get("RQ_INN") or "").strip()
        if not inn:
            skipped.append({"cid": cid, "reason": "no RQ_INN in mapping"})
            continue
        reqs = bx.call("crm.requisite.list", [
            ("filter[ENTITY_TYPE_ID]", "4"),
            ("filter[ENTITY_ID]", cid),
            ("select[]", "ID"),
            ("select[]", "RQ_INN"),
        ]).get("result", [])
        req_id = item.get("requisite_id")
        if not req_id:
            empty_reqs = [r for r in reqs if not (r.get("RQ_INN") or "").strip()]
            if not empty_reqs:
                skipped.append({"cid": cid, "reason": "нет пустого реквизита"})
                continue
            req_id = empty_reqs[0]["ID"]
        params = [("ID", str(req_id))]
        for field in ("RQ_INN", "RQ_KPP", "RQ_OGRN", "RQ_COMPANY_NAME"):
            v = (item.get(field) or "").strip()
            if v:
                params.append((f"fields[{field}]", v))
        body = bx.call("crm.requisite.update", params)
        if body.get("result"):
            updated.append({"cid": cid, "req_id": req_id, "inn": inn})
            print(f"  UPD #{cid} req#{req_id} ← INN={inn}")
        else:
            err = body.get("error_description") or body.get("error") or str(body.get("result"))
            skipped.append({"cid": cid, "reason": f"update_failed: {err}"})
            print(f"  ERR #{cid}: {err}")
    print(json.dumps({"updated": len(updated), "skipped": skipped}, ensure_ascii=False, indent=2))
    return 0


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    sys.exit(main())
