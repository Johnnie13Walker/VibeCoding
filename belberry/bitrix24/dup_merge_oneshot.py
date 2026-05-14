"""
dup_merge_oneshot.py — точечное слияние 11 групп дублей по жёстко заданному списку
(winner, losers). Используется один раз для текущей вкладки 'Дубли компаний' минус
ДАНТИСТЪ-кластер (5250071606).

Шаги для каждого loser:
  1. fetch company snapshot + UFs
  2. fetch deals/leads/contacts/activities/requisites привязанные к loser
  3. backup JSON в belberry/bitrix24/backups/manual_merge/
  4. rebind deals: crm.deal.update fields[COMPANY_ID]=winner
  5. rebind leads:  crm.lead.update fields[COMPANY_ID]=winner
  6. rebind contacts: crm.contact.company.items.set — заменить loser→winner
  7. rebind activities: crm.activity.update fields[OWNER_ID]=winner (OWNER_TYPE_ID=4 keeps)
  8. delete loser requisites: crm.requisite.delete
  9. delete loser company: crm.company.delete
  10. append summary line

Запуск:
  bash shared/scripts/bitrix-sync-state.sh
  python belberry/bitrix24/dup_merge_oneshot.py --dry-run   # обязательно сначала
  python belberry/bitrix24/dup_merge_oneshot.py             # реальное применение
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BITRIX_STATE = Path(
    os.environ.get(
        "BITRIX_STATE_PATH",
        "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json",
    )
)
BACKUP_DIR = Path(__file__).parent / "backups" / "manual_merge"

# Жёсткий список — формируется из текущего dup_sheet_sync вывода 2026-05-14.
# ДАНТИСТЪ (5250071606) намеренно пропущен — user сказал «разбираться отдельно».
GROUPS = [
    {"inn": "5001044465", "winner": "900",   "losers": ["8500"]},   # ДЕНТАМЕД
    {"inn": "5047048896", "winner": "24496", "losers": ["8526"]},   # Окм
    {"inn": "5053046424", "winner": "2890",  "losers": ["17412"]},  # ЦСС
    {"inn": "5406824209", "winner": "3668",  "losers": ["22976"]},  # ПРЕМИУМ КЛИНИК
    {"inn": "6671295025", "winner": "22944", "losers": ["23368"]},  # Камашева / БЕЗ НАЗВАНИЯ
    {"inn": "7701616802", "winner": "9702",  "losers": ["17424"]},  # ДОКТОР ЛИНЗ
    {"inn": "7716604976", "winner": "17614", "losers": ["768"]},    # УЛЫБНИСЬ
    {"inn": "7721590091", "winner": "14914", "losers": ["3628", "3638"]},  # ПРЕЗИДЕНТ-ТМ
    {"inn": "7734440833", "winner": "14388", "losers": ["622"]},    # КЛИНИКА ВОССТАНОВ. НЕВРОЛ.
    {"inn": "7802561500", "winner": "24176", "losers": ["7562"]},   # ЭДМЕД
    {"inn": "7813612683", "winner": "20288", "losers": ["8460"]},   # МЕДАЛЛ
]


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def call(method: str, params, max_tries: int = 6):
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
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if e.code in (429, 500, 502, 503, 504) and attempt < max_tries - 1:
                time.sleep(min(30, 2 ** attempt))
                continue
            raise RuntimeError(f"{method} HTTP {e.code}: {body[:200]}") from e
        except Exception:
            if attempt < max_tries - 1:
                time.sleep(min(20, 2 ** attempt))
                continue
            raise


def list_all(method: str, params, page_size: int = 50):
    """Стримит весь результат через filter[>ID]."""
    out = []
    start = 0
    while True:
        page_params = list(params) + [("start", str(start))]
        r = call(method, page_params)
        batch = r.get("result", []) or []
        out.extend(batch)
        nxt = r.get("next")
        if nxt is None:
            break
        start = nxt
    return out


def inventory_loser(loser_id: str) -> dict:
    """Что висит на этой карточке. Возвращает {} в company если карточка уже удалена."""
    inv = {"company_id": loser_id, "company": {}, "requisites": [], "deals": [], "leads": [], "contacts": [], "activities": []}
    try:
        inv["company"] = call("crm.company.get", [("ID", loser_id)]).get("result") or {}
    except RuntimeError as e:
        if "Not found" in str(e) or "HTTP 400" in str(e):
            return inv  # treated as already-deleted
        raise
    if not inv["company"]:
        return inv
    inv["requisites"] = list_all(
        "crm.requisite.list",
        [
            ("filter[ENTITY_TYPE_ID]", "4"),
            ("filter[ENTITY_ID]", loser_id),
        ],
    )
    inv["deals"] = list_all(
        "crm.deal.list",
        [("filter[COMPANY_ID]", loser_id), ("select[]", "ID"), ("select[]", "TITLE"), ("select[]", "STAGE_ID"), ("select[]", "CATEGORY_ID")],
    )
    inv["leads"] = list_all(
        "crm.lead.list",
        [("filter[COMPANY_ID]", loser_id), ("select[]", "ID"), ("select[]", "TITLE"), ("select[]", "STATUS_ID")],
    )
    inv["contacts"] = list_all(
        "crm.contact.list",
        [("filter[COMPANY_ID]", loser_id), ("select[]", "ID"), ("select[]", "NAME"), ("select[]", "LAST_NAME")],
    )
    # Activities привязанные именно к компании
    inv["activities"] = list_all(
        "crm.activity.list",
        [
            ("filter[OWNER_TYPE_ID]", "4"),
            ("filter[OWNER_ID]", loser_id),
            ("select[]", "ID"),
            ("select[]", "SUBJECT"),
            ("select[]", "OWNER_TYPE_ID"),
            ("select[]", "OWNER_ID"),
        ],
    )
    return inv


def save_backup(inn: str, winner: str, loser_id: str, inv: dict) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = BACKUP_DIR / f"{inn}_{loser_id}_into_{winner}_{ts}.json"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "inn": inn,
        "winner_id": winner,
        "loser_id": loser_id,
        "inventory": inv,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def rebind_deal(deal_id: str, winner: str, dry: bool) -> None:
    if dry:
        return
    call("crm.deal.update", [("ID", deal_id), ("fields[COMPANY_ID]", winner)])


def rebind_lead(lead_id: str, winner: str, dry: bool) -> None:
    if dry:
        return
    call("crm.lead.update", [("ID", lead_id), ("fields[COMPANY_ID]", winner)])


def rebind_activity(act_id: str, winner: str, dry: bool, loser: str = None) -> None:
    """Modern Bitrix24 API: activity.binding.add winner + binding.delete loser.
    crm.activity.update fields[OWNER_ID] возвращает 'Fields is not specified' — legacy путь не работает.
    """
    if dry:
        return
    # Сначала добавить winner-binding (idempotent: если уже привязан, Bitrix вернёт ok)
    try:
        call(
            "crm.activity.binding.add",
            [("activityId", str(act_id)), ("entityTypeId", "4"), ("entityId", str(winner))],
        )
    except RuntimeError as e:
        # Если bindings.add не доступен — fallback на update
        if "no method" in str(e).lower() or "method not found" in str(e).lower():
            call("crm.activity.update", [("id", str(act_id)), ("fields[OWNER_ID]", str(winner))])
            return
        raise
    # Затем удалить loser-binding
    if loser:
        try:
            call(
                "crm.activity.binding.delete",
                [("activityId", str(act_id)), ("entityTypeId", "4"), ("entityId", str(loser))],
            )
        except RuntimeError:
            pass  # уже отвязан — норм


def rebind_contact(contact_id: str, winner: str, loser: str, dry: bool) -> None:
    """Контакт может быть связан с несколькими компаниями. Снимаем loser, добавляем winner."""
    items = call("crm.contact.company.items.get", [("id", contact_id)]).get("result") or []
    # Items: [{"COMPANY_ID": "...", "IS_PRIMARY": "Y/N", "SORT": "...", ...}]
    new_items = []
    has_winner = False
    for it in items:
        cid = str(it.get("COMPANY_ID"))
        if cid == str(loser):
            continue  # снимаем
        if cid == str(winner):
            has_winner = True
        new_items.append(it)
    if not has_winner:
        new_items.append({"COMPANY_ID": str(winner), "IS_PRIMARY": "N", "SORT": 100})
    if dry:
        return
    # crm.contact.company.items.set нужен формат items[N][COMPANY_ID]=...
    params = [("id", contact_id)]
    for i, it in enumerate(new_items):
        params.append((f"items[{i}][COMPANY_ID]", str(it["COMPANY_ID"])))
        if "IS_PRIMARY" in it:
            params.append((f"items[{i}][IS_PRIMARY]", str(it["IS_PRIMARY"])))
        if "SORT" in it:
            params.append((f"items[{i}][SORT]", str(it["SORT"])))
    call("crm.contact.company.items.set", params)


def delete_requisite(req_id: str, dry: bool) -> None:
    if dry:
        return
    call("crm.requisite.delete", [("ID", req_id)])


def delete_company(cid: str, dry: bool) -> None:
    if dry:
        return
    call("crm.company.delete", [("ID", cid)])


def process_group(group: dict, dry: bool) -> dict:
    inn = group["inn"]
    winner = group["winner"]
    summary = {"inn": inn, "winner": winner, "losers": [], "errors": []}
    log(f"=== ИНН {inn} | winner={winner} | losers={group['losers']} ===")

    for loser_id in group["losers"]:
        log(f"  -- loser #{loser_id} -- inventorying...")
        inv = inventory_loser(loser_id)
        c = inv["company"]
        if not c:
            log(f"     loser #{loser_id} already deleted — skipping")
            summary["losers"].append({"loser_id": loser_id, "skipped": "already_deleted"})
            continue
        log(
            f"     title={c.get('TITLE','?')[:40]!r} "
            f"deals={len(inv['deals'])} leads={len(inv['leads'])} "
            f"contacts={len(inv['contacts'])} acts={len(inv['activities'])} "
            f"req={len(inv['requisites'])}"
        )

        # backup
        bpath = save_backup(inn, winner, loser_id, inv)
        log(f"     backup → {bpath.name}")

        ops = {"deals": 0, "leads": 0, "contacts": 0, "activities": 0, "req_deleted": 0}
        loser_summary = {
            "loser_id": loser_id,
            "title": c.get("TITLE", ""),
            "counts": {k: len(inv[k]) for k in ("deals", "leads", "contacts", "activities", "requisites")},
            "ops": ops,
            "backup": str(bpath),
        }

        per_entity_errors = []

        def _try(label, fn, *args):
            try:
                fn(*args, dry)
                return True
            except Exception as e:
                per_entity_errors.append(f"{label}: {e}")
                log(f"     [warn] {label} failed: {e}")
                return False

        for d in inv["deals"]:
            if _try(f"deal#{d['ID']}", rebind_deal, d["ID"], winner):
                ops["deals"] += 1
        for l in inv["leads"]:
            if _try(f"lead#{l['ID']}", rebind_lead, l["ID"], winner):
                ops["leads"] += 1
        for ct in inv["contacts"]:
            if _try(f"contact#{ct['ID']}", rebind_contact, ct["ID"], winner, loser_id):
                ops["contacts"] += 1
        for a in inv["activities"]:
            try:
                rebind_activity(a["ID"], winner, dry, loser=loser_id)
                ops["activities"] += 1
            except Exception as e:
                per_entity_errors.append(f"activity#{a['ID']}: {e}")
                log(f"     [warn] activity#{a['ID']} failed: {e}")
        for r in inv["requisites"]:
            if _try(f"requisite#{r['ID']}", delete_requisite, r["ID"]):
                ops["req_deleted"] += 1

        # Удаляем компанию только если все entity-операции прошли (иначе данные останутся орфанами)
        if per_entity_errors:
            loser_summary["per_entity_errors"] = per_entity_errors
            loser_summary["company_deleted"] = False
            log(
                f"     ❌ entity ops had {len(per_entity_errors)} errors — НЕ удаляем company #{loser_id}, "
                f"чтобы не оставить орфанов. См. backup и решай вручную."
            )
            summary["errors"].append({"loser_id": loser_id, "entity_errors": per_entity_errors})
        else:
            try:
                delete_company(loser_id, dry)
                loser_summary["company_deleted"] = True
                log(
                    f"     {'[DRY] ' if dry else ''}rebound: deals={ops['deals']} leads={ops['leads']} "
                    f"contacts={ops['contacts']} acts={ops['activities']} req-deleted={ops['req_deleted']} "
                    f"→ company #{loser_id} deleted"
                )
            except Exception as e:
                loser_summary["error"] = str(e)
                summary["errors"].append({"loser_id": loser_id, "error": str(e)})
                log(f"     !!! company.delete ERROR: {e}")

        summary["losers"].append(loser_summary)

    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="не делать write-операций")
    ap.add_argument("--limit", type=int, default=0, help="обрабатывать только первые N групп")
    ap.add_argument("--inn", action="append", help="только указанные ИНН (можно несколько раз)")
    ap.add_argument("--group", action="append", help="ad-hoc группа inn:winner:loser1,loser2 (можно несколько)")
    args = ap.parse_args()

    log(f"dup_merge_oneshot: start (dry_run={args.dry_run})")
    groups = GROUPS
    if args.group:
        groups = []
        for spec in args.group:
            parts = spec.split(":")
            if len(parts) != 3:
                raise SystemExit(f"bad --group spec: {spec}")
            inn, winner, losers = parts
            groups.append({"inn": inn, "winner": winner, "losers": losers.split(",")})
    if args.inn:
        groups = [g for g in groups if g["inn"] in args.inn]
    if args.limit:
        groups = groups[: args.limit]
    log(f"groups: {len(groups)} | total losers: {sum(len(g['losers']) for g in groups)}")

    results = []
    for g in groups:
        try:
            results.append(process_group(g, args.dry_run))
        except Exception as e:
            log(f"group {g['inn']} FAILED: {e}")
            results.append({"inn": g["inn"], "fatal": str(e)})

    # сводный отчёт
    out_path = BACKUP_DIR / f"_summary_{datetime.now().strftime('%Y%m%dT%H%M%S')}{'_dry' if args.dry_run else ''}.json"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    log(f"summary → {out_path}")

    # короткий summary в stdout
    print("\n=== SUMMARY ===")
    for r in results:
        if "fatal" in r:
            print(f"  ИНН {r['inn']}: FATAL — {r['fatal']}")
            continue
        for ls in r["losers"]:
            if ls.get("skipped"):
                print(f"  ⊘ ИНН {r['inn']} loser #{ls['loser_id']}: {ls['skipped']}")
                continue
            mark = "❌" if (ls.get("error") or ls.get("per_entity_errors")) else ("[dry]" if args.dry_run else "✓")
            title = ls.get("title", "")
            print(
                f"  {mark} ИНН {r['inn']} loser #{ls['loser_id']} ({title[:30]!r}): "
                f"counts={ls.get('counts',{})} ops={ls.get('ops',{})}"
            )

    if args.dry_run:
        log("DRY-RUN done — no Bitrix mutations. Inspect summary above + backup files.")
    else:
        log("DONE — losers removed, dups should disappear from sheet on next dup_sheet_sync run.")


if __name__ == "__main__":
    main()
