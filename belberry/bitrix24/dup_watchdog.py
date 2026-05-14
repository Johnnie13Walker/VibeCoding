"""
dup_watchdog.py — детектор новых дублей компаний Belberry Bitrix24.

Запускать раз в час по cron:
  0 * * * * cd /opt/vibecoding && /usr/bin/python3 belberry/bitrix24/dup_watchdog.py >> /var/log/dup_watchdog.log 2>&1

Логика:
  1. Читает state-файл (последний обработанный max company.ID).
  2. Запрашивает компании, созданные после prev_max_id.
  3. Для каждой новой компании:
     - извлекает ИНН (crm.requisite.list)
     - проверяет нет ли уже компании с таким ИНН (среди всех или среди созданных раньше)
  4. Если найден дубль:
     - помечает новую компанию COMMENTS = "POSSIBLE DUPLICATE OF #<existing> by dup_watchdog"
     - алёртит в Telegram (если TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID настроены)
  5. Также детектит TITLE = "данные не найдены" → отдельный алёрт (importer bug).
  6. Обновляет state с новым max_id.

Что НЕ делает (намеренно):
  - не блокирует создание компании (Bitrix REST не имеет on-add блокировки без onPull/server events)
  - не удаляет автоматически
  - только помечает + уведомляет
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime

STATE_FILE = Path(os.environ.get("DUP_WATCHDOG_STATE", "/Users/pro2kuror/Desktop/VibeCoding/shared/state/dup_watchdog_state.json"))
BITRIX_STATE = Path(os.environ.get("BITRIX_STATE_PATH", "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json"))
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
DRY_RUN = "--dry-run" in sys.argv

def log(msg):
    print(f"[{datetime.now().isoformat()}] {msg}", flush=True)

def call(method, params, max_tries=6):
    s = json.loads(BITRIX_STATE.read_text())["payload"]
    endpoint = s["auth[client_endpoint]"].rstrip("/")
    token = s["auth[access_token]"]
    url = f"{endpoint}/{method}"
    data = urllib.parse.urlencode([("auth", token), *params]).encode()
    for attempt in range(max_tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < max_tries - 1:
                time.sleep(min(30, 2 ** attempt))
                continue
            raise

def tg_send(text):
    if not (TG_TOKEN and TG_CHAT):
        log(f"  [TG skipped] {text[:80]}")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15).read()
    except Exception as e:
        log(f"  [TG err] {e}")

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"max_id": 0, "last_run": None, "alerted_pairs": []}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

def fetch_new_companies(after_id):
    """Fetch companies created with ID > after_id."""
    companies = []
    last_id = after_id
    while True:
        resp = call("crm.company.list", [
            ("filter[>ID]", str(last_id)),
            ("order[ID]", "ASC"),
            ("start", "-1"),
            ("select[]", "ID"), ("select[]", "TITLE"),
            ("select[]", "DATE_CREATE"), ("select[]", "CREATED_BY_ID"),
            ("select[]", "COMMENTS"),
        ])
        batch = resp.get("result", []) or []
        if not batch:
            break
        companies.extend(batch)
        last_id = int(batch[-1]["ID"])
        if len(batch) < 50:
            break
    return companies

def get_inn(company_id):
    r = call("crm.requisite.list", [
        ("filter[ENTITY_TYPE_ID]", "4"),
        ("filter[ENTITY_ID]", str(company_id)),
        ("select[]", "RQ_INN"),
        ("start", "-1"),
    ]).get("result", []) or []
    for req in r:
        inn = (req.get("RQ_INN") or "").strip()
        if inn:
            return inn
    return None

def find_existing_by_inn(inn, exclude_id):
    """Returns first existing company with given INN (excluding the one we just got)."""
    # Use crm.requisite.list filter[RQ_INN] then look up entity
    r = call("crm.requisite.list", [
        ("filter[ENTITY_TYPE_ID]", "4"),
        ("filter[RQ_INN]", inn),
        ("select[]", "ENTITY_ID"),
        ("select[]", "ID"),
        ("start", "-1"),
    ]).get("result", []) or []
    others = [req for req in r if str(req["ENTITY_ID"]) != str(exclude_id)]
    if not others:
        return None
    # Pick the oldest entity (smallest ID = older usually)
    others.sort(key=lambda x: int(x["ENTITY_ID"]))
    return str(others[0]["ENTITY_ID"])


def all_companies_by_inn(inn):
    """Все ENTITY_ID компаний с данным RQ_INN."""
    r = call("crm.requisite.list", [
        ("filter[ENTITY_TYPE_ID]", "4"),
        ("filter[RQ_INN]", inn),
        ("select[]", "ENTITY_ID"),
        ("start", "-1"),
    ]).get("result", []) or []
    return sorted({str(req["ENTITY_ID"]) for req in r}, key=int)


def detect_tangle(cids):
    """Тангл-сигнатура: >=3 карточек с одним ИНН + минимум 2 разных сайта/города.
    Возвращает {sites, cities, companies} если тангл, иначе None.
    """
    if len(cids) < 3:
        return None
    sites = set()
    cities = set()
    companies = []
    for cid in cids:
        try:
            c = call("crm.company.get", [("ID", cid)]).get("result") or {}
        except Exception:
            continue
        site = (c.get("UF_CRM_5DEF838D882A2") or "").strip()
        city = (c.get("UF_CRM_1584876724") or "").strip()
        title = (c.get("TITLE") or "").strip()
        if site:
            sites.add(site)
        if city:
            cities.add(city)
        companies.append({"id": cid, "title": title, "site": site, "city": city})
    if len(sites) >= 2 or len(cities) >= 2:
        return {"sites": sites, "cities": cities, "companies": companies}
    return None

PORTAL_BASE = "https://belberrycrm.bitrix24.ru/crm/company/details"

def url_of(cid):
    return f"{PORTAL_BASE}/{cid}/"

def main():
    state = load_state()
    prev_max = state.get("max_id", 0)
    log(f"Watchdog started. Last max_id={prev_max}")

    new_companies = fetch_new_companies(prev_max)
    log(f"New companies since last run: {len(new_companies)}")

    if not new_companies:
        state["last_run"] = datetime.now().isoformat()
        save_state(state)
        return

    new_max = max(int(c["ID"]) for c in new_companies)

    alerts = []
    importer_bugs = []
    tangle_alerts = []  # тангл-сигнатура: один ИНН на 3+ карточках с разными сайтами/городами
    # Normalize legacy pairs (stored как list-of-list в JSON) → tuple (min,max) для устойчивости
    # к смене направления existing/new при удалении одной из карточек.
    alerted_pairs = set()
    for p in state.get("alerted_pairs", []):
        if len(p) >= 2:
            a, b = str(p[0]), str(p[1])
            alerted_pairs.add(tuple(sorted([a, b], key=int)))
    alerted_tangles = set(state.get("alerted_tangles", []))  # set of ИНН, по которым уже сообщили

    for c in new_companies:
        cid = c["ID"]
        title = (c.get("TITLE") or "").strip()

        # Importer-bug detector
        if title.lower() in ("данные не найдены", ""):
            importer_bugs.append({"id": cid, "title": title, "created_by": c.get("CREATED_BY_ID")})
            continue

        # INN-based duplicate check
        inn = get_inn(cid)
        if not inn:
            # No INN yet — может появиться позже, не алертим
            continue

        existing = find_existing_by_inn(inn, cid)
        if not existing:
            continue

        # Normalized pair key — stable независимо от того, какая карточка была "новее"
        pair_key = tuple(sorted([str(existing), str(cid)], key=int))
        if pair_key in alerted_pairs:
            continue

        # Idempotent guard через сами COMMENTS — если маркер уже там, не дублируем
        # (защита от потери state-файла).
        cur_comments = c.get("COMMENTS") or ""
        marker_signature = f"POSSIBLE DUPLICATE OF #{existing}"
        if marker_signature in cur_comments:
            alerted_pairs.add(pair_key)  # синхронизируем state с реальностью
            continue

        # Mark new card with COMMENT
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        marker = f"{marker_signature} by dup_watchdog {ts}"
        new_comments = (cur_comments + "\n\n" + marker).strip() if cur_comments else marker
        if not DRY_RUN:
            call("crm.company.update", [
                ("ID", cid),
                ("fields[COMMENTS]", new_comments),
            ])
        alerts.append({"new": cid, "existing": existing, "inn": inn, "title": title, "created_by": c.get("CREATED_BY_ID")})
        alerted_pairs.add(pair_key)

        # Tangle-сигнатура: 3+ карточек с одним ИНН + разные сайты/города (баг типа ДАНТИСТЪ).
        # Алертим один раз per-ИНН чтобы не повторяться.
        if inn not in alerted_tangles:
            all_cids = all_companies_by_inn(inn)
            tangle = detect_tangle(all_cids)
            if tangle:
                tangle_alerts.append({"inn": inn, **tangle})
                alerted_tangles.add(inn)

    # Build telegram report
    parts = []
    if alerts:
        lines = [f"⚠️ <b>Найдены {len(alerts)} новых дубля компаний</b>"]
        for a in alerts[:15]:
            lines.append(f'• <a href="{url_of(a["new"])}">#{a["new"]} {a["title"][:40]}</a> дубль <a href="{url_of(a["existing"])}">#{a["existing"]}</a> ИНН <code>{a["inn"]}</code> создал user {a["created_by"]}')
        if len(alerts) > 15:
            lines.append(f"... и ещё {len(alerts)-15}")
        parts.append("\n".join(lines))
    if importer_bugs:
        lines = [f"🐛 <b>Importer bug: {len(importer_bugs)} карточек с placeholder TITLE</b>"]
        for b in importer_bugs[:10]:
            lines.append(f'• <a href="{url_of(b["id"])}">#{b["id"]}</a> title="{b["title"]}" создал user {b["created_by"]}')
        if len(importer_bugs) > 10:
            lines.append(f"... и ещё {len(importer_bugs)-10}")
        parts.append("\n".join(lines))
    if tangle_alerts:
        lines = [f"🪢 <b>Обнаружен ТАНГЛ — несколько разных бизнесов под одним ИНН</b>"]
        for t in tangle_alerts:
            lines.append(f'ИНН <code>{t["inn"]}</code> — {len(t["companies"])} карточек, sites={len(t["sites"])} cities={len(t["cities"])}:')
            for cmp in t["companies"][:5]:
                lines.append(f'  • <a href="{url_of(cmp["id"])}">#{cmp["id"]}</a> {cmp["title"][:35]} | city={cmp["city"]!r} site={cmp["site"]!r}')
            if len(t["companies"]) > 5:
                lines.append(f'  ... и ещё {len(t["companies"])-5}')
        lines.append("Действие: проверить через rusprofile настоящий ИНН для каждой карточки и перепривязать.")
        parts.append("\n".join(lines))

    if parts:
        text = "\n\n".join(parts) + f"\n\n📊 Просканировано: {len(new_companies)} новых компаний"
        tg_send(text)
        log(f"Alerts: {len(alerts)} dup + {len(importer_bugs)} bugs")
    else:
        log(f"No issues. Scanned {len(new_companies)} new companies.")

    # Persist state
    state["max_id"] = new_max
    state["last_run"] = datetime.now().isoformat()
    state["alerted_pairs"] = list(alerted_pairs)[-1000:]  # keep last 1000
    state["alerted_tangles"] = list(alerted_tangles)[-200:]
    if not DRY_RUN:
        save_state(state)

if __name__ == "__main__":
    main()
