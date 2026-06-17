"""ETL-оркестратор Bitrix24 → Google Sheets.

Запускается из cron каждые 15 мин. Логика:
1. Прочитать etl_state.json (last_run для каждой сущности).
2. Для каждой сущности: вытащить инкремент, сложить в Sheets с upsert.
3. Обновить etl_state.json.
4. Дописать строку в sync_log.

Запуск:
    python -m sales_dashboard.cli etl --full     # полная выгрузка
    python -m sales_dashboard.cli etl            # инкрементальный
"""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from . import config
from .bitrix_client import BitrixClient
from .extractors import calls as calls_ex
from .extractors import deals as deals_ex
from .extractors import users as users_ex
from .sheets_client import SheetsClient


@dataclass
class StageResult:
    name: str
    ok: bool
    rows: int = 0
    inserted: int = 0
    updated: int = 0
    duration_s: float = 0.0
    error: str = ""


@dataclass
class EtlRun:
    started_at: datetime
    full: bool
    results: list[StageResult] = field(default_factory=list)


def load_state() -> dict:
    if config.ETL_STATE_PATH.exists():
        return json.loads(config.ETL_STATE_PATH.read_text())
    return {}


def save_state(state: dict) -> None:
    config.ETL_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _since(state: dict, key: str, *, full: bool, fallback_days: int) -> datetime:
    if full or key not in state:
        return datetime.now(config.MOSCOW_TZ) - timedelta(days=fallback_days)
    # отступаем чуть назад для подхвата edge-кейсов
    base = datetime.fromisoformat(state[key])
    return base - timedelta(hours=config.INCREMENTAL_LOOKBACK_HOURS)


def run_stage(
    name: str,
    fn: Callable[[], tuple[int, int, int]],
) -> StageResult:
    started = datetime.now(config.MOSCOW_TZ)
    try:
        rows, inserted, updated = fn()
        return StageResult(
            name=name,
            ok=True,
            rows=rows,
            inserted=inserted,
            updated=updated,
            duration_s=(datetime.now(config.MOSCOW_TZ) - started).total_seconds(),
        )
    except Exception as e:
        return StageResult(
            name=name,
            ok=False,
            duration_s=(datetime.now(config.MOSCOW_TZ) - started).total_seconds(),
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}",
        )


def run_etl(full: bool = False) -> EtlRun:
    if not config.SHEET_ID:
        raise RuntimeError(
            "config.SHEET_ID пуст. Создай Google Sheet, расшарь "
            "на сервис-аккаунт finance-director-sheets@...iam.gserviceaccount.com "
            "с правами Editor, и пропиши ID в config.SHEET_ID."
        )

    started = datetime.now(config.MOSCOW_TZ)
    state = load_state()
    bx = BitrixClient(log_path=config.LOG_PATH)
    sh = SheetsClient(config.SHEET_ID, config.SERVICE_ACCOUNT_JSON)

    run = EtlRun(started_at=started, full=full)

    # ----- categories -----
    cat_rows: list[list] = []
    category_names: dict[int, str] = {}

    def _do_categories() -> tuple[int, int, int]:
        nonlocal cat_rows, category_names
        cat_rows = users_ex.extract_categories(bx)
        category_names = {r[0]: r[1] for r in cat_rows if isinstance(r[0], int)}
        sh.replace_tab(config.TAB_CATEGORIES, users_ex.CATEGORY_HEADER, cat_rows)
        return (len(cat_rows), len(cat_rows), 0)

    run.results.append(run_stage("categories", _do_categories))

    # ----- stages -----
    stage_names: dict[str, str] = {}

    def _do_stages() -> tuple[int, int, int]:
        nonlocal stage_names
        rows = users_ex.extract_stages(bx, cat_rows)
        # stages header: [stage_id, category_id, status_id, name, sort, semantic]
        stage_names = {r[0]: r[3] for r in rows if r[0]}
        sh.replace_tab(config.TAB_STAGES, users_ex.STAGE_HEADER, rows)
        return (len(rows), len(rows), 0)

    run.results.append(run_stage("stages", _do_stages))

    # ----- users -----
    user_names: dict[int, str] = {}

    def _do_users() -> tuple[int, int, int]:
        nonlocal user_names
        rows = users_ex.extract_users(bx)
        # users header: [user_id, active, email, name, last_name, second_name, full_name, ...]
        user_names = {r[0]: r[6] for r in rows if isinstance(r[0], int)}
        sh.replace_tab(config.TAB_USERS, users_ex.USER_HEADER, rows)
        return (len(rows), len(rows), 0)

    run.results.append(run_stage("users", _do_users))

    # ----- deals -----
    def _do_deals() -> tuple[int, int, int]:
        since = _since(state, "deals_last_run", full=full, fallback_days=config.INITIAL_BACKFILL_DAYS)
        rows = deals_ex.extract_deals(
            bx,
            since,
            config.PORTAL_DOMAIN,
            user_names=user_names,
            stage_names=stage_names,
            category_names=category_names,
        )
        if full:
            sh.replace_tab(config.TAB_DEALS, deals_ex.HEADER, rows)
            ins, upd = (len(rows), 0)
        else:
            ins, upd = sh.upsert_tab(
                config.TAB_DEALS, deals_ex.HEADER, rows, key_column="deal_id"
            )
        state["deals_last_run"] = datetime.now(config.MOSCOW_TZ).isoformat()
        return (len(rows), ins, upd)

    run.results.append(run_stage("deals", _do_deals))

    # ----- calls -----
    def _do_calls() -> tuple[int, int, int]:
        since = _since(
            state,
            "calls_last_run",
            full=full,
            fallback_days=config.INITIAL_BACKFILL_CALLS_DAYS,
        )
        all_rows: list[list] = []
        cur = since
        end = datetime.now(config.MOSCOW_TZ)
        while cur < end:
            nxt = min(cur + timedelta(days=1), end)
            all_rows.extend(calls_ex.extract_calls(bx, cur, nxt, user_names=user_names))
            cur = nxt
        if full:
            sh.replace_tab(config.TAB_CALLS, calls_ex.HEADER, all_rows)
            ins, upd = (len(all_rows), 0)
        else:
            ins, upd = sh.upsert_tab(
                config.TAB_CALLS, calls_ex.HEADER, all_rows, key_column="call_id"
            )
        state["calls_last_run"] = datetime.now(config.MOSCOW_TZ).isoformat()
        return (len(all_rows), ins, upd)

    run.results.append(run_stage("calls", _do_calls))

    save_state(state)

    # ----- sync_log -----
    log_rows = [
        [
            run.started_at.isoformat(timespec="seconds"),
            "full" if full else "incremental",
            r.name,
            "ok" if r.ok else "err",
            r.rows,
            r.inserted,
            r.updated,
            round(r.duration_s, 2),
            r.error[:500],
        ]
        for r in run.results
    ]
    try:
        sh.append_log(
            config.TAB_SYNC_LOG,
            ["ts", "mode", "stage", "status", "rows", "inserted", "updated", "duration_s", "error"],
            log_rows,
        )
    except Exception as e:
        sys.stderr.write(f"[sync_log] write failed: {e}\n")

    return run


def print_run(run: EtlRun) -> None:
    print(f"ETL {'FULL' if run.full else 'incremental'} @ {run.started_at.isoformat(timespec='seconds')}")
    print(f"{'stage':<14}{'status':<8}{'rows':>8}{'ins':>8}{'upd':>8}{'sec':>8}")
    for r in run.results:
        print(
            f"{r.name:<14}{'ok' if r.ok else 'ERR':<8}"
            f"{r.rows:>8}{r.inserted:>8}{r.updated:>8}{r.duration_s:>8.1f}"
        )
        if r.error:
            print(f"  ↳ {r.error.splitlines()[0]}")
