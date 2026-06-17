"""Массовый безопасный проход обогащения компаний Bitrix24.

Идёт от самых новых карточек к старым по ID DESC, что на портале Belberry
соответствует DATE_CREATE DESC для текущего потока создания компаний.
Реквизиты не создаёт и заполненные поля не перезаписывает.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


MOSCOW_TZ = ZoneInfo("Europe/Moscow")
WORKSPACE_ROOT = Path("/Users/pro2kuror/Desktop/VibeCoding")
MODULE_ROOT = (
    WORKSPACE_ROOT
    / "tmp/crm_company_enrich_worktree/belberry/bitrix24/crm_company_enrich"
)

if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from crm_company_enrich.bitrix_client import BitrixClient  # noqa: E402
from crm_company_enrich.config import LOG_PATH, STATE_PATH  # noqa: E402
from crm_company_enrich.stages import sync_deals  # noqa: E402


def now_msk() -> str:
    return datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")


def load_state(path: Path, *, before_id: int | None) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "started_at_msk": now_msk(),
        "finished_at_msk": "",
        "cursor_before_id": before_id,
        "processed": 0,
        "updated_company_runs": 0,
        "updated_deals": 0,
        "company_updated_from_deals": 0,
        "noop": 0,
        "failed": 0,
        "pages": 0,
        "last_company_id": "",
    }


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    obj.setdefault("ts_msk", now_msk())
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


def get_page(bx: BitrixClient, before_id: int | None) -> list[dict]:
    filt: dict[str, str] = {}
    if before_id:
        filt["<ID"] = str(before_id)
    body = bx.call(
        "crm.company.list",
        {
            "filter": filt,
            "order": {"ID": "DESC"},
            "select": [
                "ID",
                "TITLE",
                "DATE_CREATE",
                "DATE_MODIFY",
                "UF_CRM_1735331882180",
                "UF_CRM_5DEF838D882A2",
            ],
            "start": -1,
        },
    )
    rows = body.get("result") or []
    rows.sort(key=lambda c: int(c.get("ID") or 0), reverse=True)
    return rows


def run(args: argparse.Namespace) -> dict:
    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    state = load_state(args.state, before_id=args.before_id)
    append_jsonl(args.jsonl, {"event": "start_or_resume", "state": state})
    save_state(args.state, state)

    before_id = state.get("cursor_before_id")
    processed_this_run = 0

    while True:
        rows = get_page(bx, int(before_id) if before_id else None)
        if not rows:
            break
        state["pages"] += 1

        for row in rows:
            if args.limit is not None and processed_this_run >= args.limit:
                state["finished_at_msk"] = ""
                save_state(args.state, state)
                append_jsonl(args.jsonl, {"event": "paused_by_limit", "state": state})
                return state

            company_id = str(row.get("ID") or "")
            if not company_id:
                continue

            before_id = int(company_id)
            state["cursor_before_id"] = before_id
            state["last_company_id"] = company_id

            entry = {
                "event": "company",
                "company_id": company_id,
                "title": row.get("TITLE"),
                "date_create": row.get("DATE_CREATE"),
            }
            try:
                deals = bx.list_company_deals(company_id)
                has_active_deals = any(str(d.get("CLOSED") or "N") != "Y" for d in deals)
                if has_active_deals:
                    result = sync_deals.run(
                        bx,
                        company_id=company_id,
                        dry_run=False,
                        overwrite=False,
                        active_only=True,
                    )
                    entry["mode"] = "sync_deals"
                    state["updated_deals"] += int(result.get("updated") or 0)
                    state["company_updated_from_deals"] += int(
                        result.get("company_updated") or 0
                    )
                    if (
                        not result.get("updated")
                        and not result.get("company_updated")
                        and not result.get("failed")
                    ):
                        state["noop"] += 1
                else:
                    result = sync_deals.run_company(
                        bx,
                        company_id=company_id,
                        dry_run=False,
                        overwrite=False,
                    )
                    entry["mode"] = "sync_company"
                    state["updated_company_runs"] += int(result.get("updated") or 0)
                    state["noop"] += int(result.get("noop") or 0)

                failed = int(result.get("failed") or 0)
                state["failed"] += failed
                entry["status"] = "failed" if failed else "ok"
                entry["result"] = result
            except Exception as exc:  # noqa: BLE001
                state["failed"] += 1
                entry["status"] = "failed"
                entry["error"] = str(exc)[:800]

            state["processed"] += 1
            processed_this_run += 1
            append_jsonl(args.jsonl, entry)

            if state["processed"] % args.checkpoint_every == 0:
                save_state(args.state, state)
                print(json.dumps({"progress": state}, ensure_ascii=False), flush=True)

            if args.throttle > 0:
                time.sleep(args.throttle)

        save_state(args.state, state)
        if len(rows) < 50:
            break

    state["finished_at_msk"] = now_msk()
    save_state(args.state, state)
    append_jsonl(args.jsonl, {"event": "finish", "state": state})
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--before-id", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--throttle", type=float, default=0.2)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
