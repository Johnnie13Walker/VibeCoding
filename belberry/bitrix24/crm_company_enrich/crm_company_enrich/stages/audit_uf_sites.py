"""Аудит UF site перед cleanup существующих значений."""
from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..config import LOG_DIR
from .enrich_web import is_site_alive

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
UF_SITE_FIELD = "UF_CRM_5DEF838D882A2"
DEFAULT_REPORT_PATH = Path("/tmp/uf_site_audit.json")
DEFAULT_WORKERS = 256
# Reasons, на которых сайт почти гарантированно мёртв (нет такого домена либо
# сокет отказывает). Используются по умолчанию в clear_dead, чтобы не сносить
# UF на временных проблемах (timeout/5xx/ssl_error/4xx_blocked).
DEFAULT_CLEAR_DEAD_REASONS: tuple[str, ...] = ("dns", "conn_refused")


def run(
    bx,
    *,
    dry_run: bool = True,
    rollback_to_vk: bool = False,
    clear_dead: bool = False,
    clear_dead_reasons: tuple[str, ...] = DEFAULT_CLEAR_DEAD_REASONS,
    # Безопасный default: если у компании есть хотя бы одна сделка (любая стадия,
    # любая воронка) — UF site НЕ чистим. Это защита от «домен умер, но компания
    # реальный клиент с историей». Можно переопределить flag'ом force_with_deals.
    skip_if_has_deals: bool = True,
    force_with_deals: bool = False,
    report_path: Path = DEFAULT_REPORT_PATH,
    timeout: float = 6.0,
) -> dict[str, Any]:
    if not dry_run and not rollback_to_vk and not clear_dead:
        raise ValueError("--live audit-uf-sites требует --rollback-to-vk или --clear-dead")
    if rollback_to_vk and clear_dead:
        raise ValueError("--rollback-to-vk и --clear-dead взаимоисключающи")

    clear_reasons = tuple(clear_dead_reasons or ())
    apply_skip_deals = bool(skip_if_has_deals and clear_dead and not force_with_deals)

    rows = _companies_with_uf_site(bx)
    checks = _check_sites(rows, timeout=timeout)

    # Только для clear_dead режима подтягиваем сделки заранее (batch)
    deals_by_cid: dict[str, list[dict[str, Any]]] = {}
    if apply_skip_deals:
        clear_candidates = [
            str(company.get("ID") or "")
            for company in rows
            if (
                not checks.get(str(company.get("ID") or ""), _UNKNOWN).is_alive
                and checks.get(str(company.get("ID") or ""), _UNKNOWN).reason in clear_reasons
                and str(company.get(UF_SITE_FIELD) or "").strip()
            )
        ]
        deals_by_cid = _fetch_deals_for(bx, clear_candidates)

    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    live_updates = 0
    cleared = 0
    rolled_back = 0
    skipped_has_deals = 0
    backup_dir = LOG_DIR / ("uf_site_clear" if clear_dead else "uf_site_audit")

    for company in rows:
        company_id = str(company.get("ID") or "")
        uf_site = str(company.get(UF_SITE_FIELD) or "").strip()
        check = checks.get(company_id) or is_site_alive(uf_site)
        counts[check.reason] += 1
        counts["alive" if check.is_alive else "dead"] += 1

        rollback_target = (
            _rollback_target(company) if rollback_to_vk and not check.is_alive else ""
        )
        should_clear = (
            clear_dead and not check.is_alive and check.reason in clear_reasons
        )

        if rollback_to_vk:
            target_value = rollback_target
            action = "rollback" if rollback_target else ""
        elif should_clear:
            target_value = ""
            action = "clear"
        else:
            target_value = ""
            action = ""

        # Защита от сноса UF у компаний с активными/историческими сделками
        deals_count = len(deals_by_cid.get(company_id, []))
        if action == "clear" and apply_skip_deals and deals_count > 0:
            action = "skip_has_deals"
            skipped_has_deals += 1

        result = {
            "company_id": company_id,
            "title": str(company.get("TITLE") or ""),
            "uf_site": uf_site,
            "is_alive": check.is_alive,
            "status_code": check.status_code,
            "reason": check.reason,
            "rollback_target": rollback_target,
            "action": action,
            "deals_count": deals_count,
        }
        results.append(result)

        if dry_run or check.is_alive or action in ("", "skip_has_deals"):
            continue
        if action == "clear" and not uf_site:
            # нечего чистить — UF уже пустой
            continue

        backup_dir.mkdir(parents=True, exist_ok=True)
        _write_backup(backup_dir / f"{company_id}.json", company, result)
        bx.update_company(company_id, {UF_SITE_FIELD: target_value})
        live_updates += 1
        if action == "rollback":
            rolled_back += 1
        elif action == "clear":
            cleared += 1

    summary = {
        "dry_run": dry_run,
        "rollback_to_vk": rollback_to_vk,
        "clear_dead": clear_dead,
        "clear_dead_reasons": list(clear_reasons) if clear_dead else [],
        "skip_if_has_deals": apply_skip_deals,
        "total": len(rows),
        "alive": counts.get("alive", 0),
        "dead": counts.get("dead", 0),
        "reasons": {
            key: counts.get(key, 0)
            for key in (
                "ok",
                "redirect",
                "dns",
                "timeout",
                "5xx",
                "4xx_blocked",
                "conn_refused",
                "ssl_error",
                "bad_url",
            )
        },
        "live_updates": live_updates,
        "rolled_back": rolled_back,
        "cleared": cleared,
        "skipped_has_deals": skipped_has_deals,
        "report_path": str(report_path),
        "backup_dir": str(backup_dir),
        "results": results,
    }
    if dry_run:
        report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


class _Unknown:
    is_alive = False
    reason = "unknown"


_UNKNOWN = _Unknown()


def _fetch_deals_for(bx, company_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Подтянуть сделки для списка компаний через batch (по 50)."""
    out: dict[str, list[dict[str, Any]]] = {cid: [] for cid in company_ids}
    if not company_ids:
        return out
    if not hasattr(bx, "batch") or not hasattr(bx, "call"):
        # Клиент без batch/call API — не можем проверить сделки. Возвращаем пусто,
        # тогда skip_if_has_deals не сработает; это рассматривается как degraded
        # mode (актуально для in-memory FakeBitrix в тестах).
        return out

    select = ["ID", "CATEGORY_ID", "STAGE_ID", "CLOSED"]
    CHUNK = 50
    for i in range(0, len(company_ids), CHUNK):
        chunk = company_ids[i:i + CHUNK]
        commands = {
            f"d{idx}": ("crm.deal.list", {"filter": {"COMPANY_ID": cid}, "select": select, "start": 0})
            for idx, cid in enumerate(chunk)
        }
        try:
            result = bx.batch(commands)
        except Exception:
            continue
        for idx, cid in enumerate(chunk):
            payload = result.get(f"d{idx}") or []
            if isinstance(payload, list):
                out[cid] = payload
    return out


def _check_sites(rows: list[dict[str, Any]], *, workers: int = DEFAULT_WORKERS, timeout: float = 6.0) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_by_company_id = {
            executor.submit(is_site_alive, str(company.get(UF_SITE_FIELD) or "").strip(), timeout=timeout): str(company.get("ID") or "")
            for company in rows
        }
        for future in as_completed(future_by_company_id):
            company_id = future_by_company_id[future]
            try:
                checks[company_id] = future.result()
            except Exception:
                # Worker exception (LocationParseError, UnicodeError и пр.)
                # не валит весь audit — компания помечается как bad_url
                from .enrich_web import SiteAliveCheck
                checks[company_id] = SiteAliveCheck("", False, None, "bad_url")
    return checks


def _companies_with_uf_site(bx) -> list[dict[str, Any]]:
    select = ["ID", "TITLE", "WEB", UF_SITE_FIELD]
    filter_ = {f"!{UF_SITE_FIELD}": ""}
    if hasattr(bx, "batch") and hasattr(bx, "call"):
        first = bx.call("crm.company.list", {"filter": filter_, "select": select, "start": 0})
        rows = list(first.get("result") or [])
        total = int(first.get("total") or len(rows))
        offsets = list(range(50, total, 50))
        for chunk_start in range(0, len(offsets), 50):
            chunk = offsets[chunk_start:chunk_start + 50]
            result = bx.batch({
                f"p{offset}": (
                    "crm.company.list",
                    {"filter": filter_, "select": select, "start": offset},
                )
                for offset in chunk
            })
            for offset in chunk:
                page = result.get(f"p{offset}") or []
                if isinstance(page, list):
                    rows.extend(page)
        return [company for company in rows if str(company.get(UF_SITE_FIELD) or "").strip()]

    try:
        rows = bx.list_companies(select=select, filter_=filter_)
    except TypeError:
        rows = bx.list_companies(select=select)
    return [company for company in rows if str(company.get(UF_SITE_FIELD) or "").strip()]


def _rollback_target(company: dict[str, Any]) -> str:
    for item in company.get("WEB") or []:
        value = item.get("VALUE") if isinstance(item, dict) else item
        raw = str(value or "").strip()
        lowered = raw.lower()
        if "vk.com" in lowered or "2gis." in lowered or "2gis.ru" in lowered:
            return raw
    return ""


def _write_backup(path: Path, company: dict[str, Any], result: dict[str, Any]) -> None:
    payload = {
        "created_at": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
        "company": company,
        "audit": result,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
