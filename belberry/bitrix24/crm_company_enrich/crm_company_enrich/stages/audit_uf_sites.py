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


def run(
    bx,
    *,
    dry_run: bool = True,
    rollback_to_vk: bool = False,
    report_path: Path = DEFAULT_REPORT_PATH,
    timeout: float = 6.0,
) -> dict[str, Any]:
    if not dry_run and not rollback_to_vk:
        raise ValueError("--live audit-uf-sites требует --rollback-to-vk")

    rows = _companies_with_uf_site(bx)
    checks = _check_sites(rows, timeout=timeout)
    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    live_updates = 0
    backup_dir = LOG_DIR / "uf_site_audit"

    for company in rows:
        company_id = str(company.get("ID") or "")
        uf_site = str(company.get(UF_SITE_FIELD) or "").strip()
        check = checks.get(company_id) or is_site_alive(uf_site)
        counts[check.reason] += 1
        counts["alive" if check.is_alive else "dead"] += 1

        target = _rollback_target(company) if rollback_to_vk and not check.is_alive else ""
        result = {
            "company_id": company_id,
            "title": str(company.get("TITLE") or ""),
            "uf_site": uf_site,
            "is_alive": check.is_alive,
            "status_code": check.status_code,
            "reason": check.reason,
            "rollback_target": target,
        }
        results.append(result)

        if dry_run or check.is_alive:
            continue

        backup_dir.mkdir(parents=True, exist_ok=True)
        _write_backup(backup_dir / f"{company_id}.json", company, result)
        bx.update_company(company_id, {UF_SITE_FIELD: target})
        live_updates += 1

    summary = {
        "dry_run": dry_run,
        "rollback_to_vk": rollback_to_vk,
        "total": len(rows),
        "alive": counts.get("alive", 0),
        "dead": counts.get("dead", 0),
        "reasons": {
            key: counts.get(key, 0)
            for key in ("ok", "dns", "timeout", "5xx", "4xx_blocked", "conn_refused", "ssl_error", "bad_url")
        },
        "live_updates": live_updates,
        "report_path": str(report_path),
        "backup_dir": str(backup_dir),
        "results": results,
    }
    if dry_run:
        report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def _check_sites(rows: list[dict[str, Any]], *, workers: int = DEFAULT_WORKERS, timeout: float = 6.0) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_by_company_id = {
            executor.submit(is_site_alive, str(company.get(UF_SITE_FIELD) or "").strip(), timeout=timeout): str(company.get("ID") or "")
            for company in rows
        }
        for future in as_completed(future_by_company_id):
            company_id = future_by_company_id[future]
            checks[company_id] = future.result()
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
