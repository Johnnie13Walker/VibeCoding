#!/usr/bin/env python3
"""Dry-run план объединения дублей сделок Bitrix24."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloudbot.providers.bitrix.bitrix_sales_adapter import BitrixSalesAdapter
from cloudbot.providers.bitrix.deal_duplicate_policy import (
    DEFAULT_DOMAIN_FIELDS,
    DealDuplicatePlan,
    group_deals_by_domain,
    plan_duplicate_group,
)
from scripts.run_sales_copilot import (
    DEFAULT_REMOTE_ENV_FILE,
    DEFAULT_REMOTE_STATE_DIR,
    _build_agent_env,
    _fetch_remote_env,
    _resolve_remote_host,
    _sync_remote_state,
)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            cleaned = cleaned[1:-1]
        values[key.strip()] = cleaned
    return values


def _load_runtime_env() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in (ROOT_DIR / ".env.integrations", ROOT_DIR / "infra" / "remote-ops.env"):
        merged.update(_parse_env_file(path))
    merged.update({str(key): str(value) for key, value in os.environ.items()})
    merged["TZ"] = "Europe/Moscow"
    return merged


def _domain_fields_from_env(env: Mapping[str, str]) -> tuple[str, ...]:
    raw = str(env.get("BITRIX_DEAL_DUPLICATE_DOMAIN_FIELDS") or "").strip()
    if not raw:
        return DEFAULT_DOMAIN_FIELDS
    fields = tuple(item.strip() for item in raw.split(",") if item.strip())
    return fields or DEFAULT_DOMAIN_FIELDS


def _read_input_json(path: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)], {}
    if not isinstance(payload, Mapping):
        raise ValueError("JSON должен быть списком сделок или объектом с ключом deals.")
    deals = payload.get("deals")
    product_rows = payload.get("product_rows_by_deal") or {}
    if not isinstance(deals, list):
        raise ValueError("В JSON объекте ключ deals должен быть списком.")
    normalized_products: dict[str, list[dict[str, Any]]] = {}
    if isinstance(product_rows, Mapping):
        for deal_id, rows in product_rows.items():
            if isinstance(rows, list):
                normalized_products[str(deal_id)] = [dict(item) for item in rows if isinstance(item, Mapping)]
    return [dict(item) for item in deals if isinstance(item, Mapping)], normalized_products


def _load_live_deals(
    adapter: BitrixSalesAdapter,
    *,
    limit: int | None,
    load_product_rows: bool,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    categories = adapter.get_deal_category_map()
    stage_maps = _load_stage_maps(adapter, categories)
    source_map = _load_source_map(adapter)
    deals = adapter.get_deals(limit=limit, order={"DATE_MODIFY": "DESC"})
    enriched = [
        _enrich_deal(deal, categories=categories, stage_maps=stage_maps, source_map=source_map)
        for deal in deals
    ]
    product_rows: dict[str, list[dict[str, Any]]] = {}
    if load_product_rows:
        product_rows = adapter.get_deal_product_rows([deal["id"] for deal in enriched])
    return enriched, product_rows


def _load_remote_bridge_deals(
    env: Mapping[str, str],
    *,
    limit: int | None,
    load_product_rows: bool,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    remote_host = _resolve_remote_host(env)
    remote_env_file = str(env.get("SALES_REMOTE_ENV_FILE") or DEFAULT_REMOTE_ENV_FILE).strip() or DEFAULT_REMOTE_ENV_FILE
    remote_state_dir = str(env.get("SALES_REMOTE_STATE_DIR") or DEFAULT_REMOTE_STATE_DIR).strip() or DEFAULT_REMOTE_STATE_DIR
    remote_env = _fetch_remote_env(env, remote_host, remote_env_file)

    tmp_root = ROOT_DIR / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bitrix-deal-duplicates-state-", dir=tmp_root) as tmp_dir:
        state_root = _sync_remote_state(env, remote_host, remote_state_dir, Path(tmp_dir))
        agent_env = _build_agent_env(env, remote_env, state_root, ROOT_DIR)
        adapter = BitrixSalesAdapter.from_env(env=agent_env)
        return _load_live_deals(adapter, limit=limit, load_product_rows=load_product_rows)


def _load_stage_maps(adapter: BitrixSalesAdapter, categories: Mapping[str, str]) -> dict[str, dict[str, str]]:
    maps: dict[str, dict[str, str]] = {}
    for category_id in categories:
        rows = adapter.get_deal_stage_map(category_id)
        maps[category_id] = {
            str(row.get("STATUS_ID") or row.get("statusId") or "").strip(): str(row.get("NAME") or "").strip()
            for row in rows
            if isinstance(row, Mapping)
        }
    return maps


def _load_source_map(adapter: BitrixSalesAdapter) -> dict[str, str]:
    rows = adapter.get_deal_source_map()
    return {
        str(row.get("STATUS_ID") or row.get("statusId") or "").strip(): str(row.get("NAME") or "").strip()
        for row in rows
        if isinstance(row, Mapping)
    }


def _enrich_deal(
    deal: Mapping[str, Any],
    *,
    categories: Mapping[str, str],
    stage_maps: Mapping[str, Mapping[str, str]],
    source_map: Mapping[str, str],
) -> dict[str, Any]:
    enriched = dict(deal)
    category_id = str(enriched.get("category_id") or enriched.get("CATEGORY_ID") or "").strip()
    stage_id = str(enriched.get("stage_id") or enriched.get("STAGE_ID") or "").strip()
    source_id = str(enriched.get("source_id") or enriched.get("SOURCE_ID") or "").strip()
    if category_id and "category_name" not in enriched:
        enriched["category_name"] = categories.get(category_id, "")
    if category_id and stage_id and "stage_name" not in enriched:
        enriched["stage_name"] = stage_maps.get(category_id, {}).get(stage_id, "")
    if source_id and "source_name" not in enriched:
        enriched["source_name"] = source_map.get(source_id, "")
    return enriched


def _build_plans(
    deals: Sequence[Mapping[str, Any]],
    *,
    product_rows_by_deal: Mapping[str, Sequence[Mapping[str, Any]]],
    domain_fields: Sequence[str],
) -> list[DealDuplicatePlan]:
    groups = group_deals_by_domain(deals, domain_fields=domain_fields)
    plans: list[DealDuplicatePlan] = []
    for domain_key, group in sorted(groups.items()):
        plans.append(
            plan_duplicate_group(
                group,
                domain_key=domain_key,
                product_rows_by_deal=product_rows_by_deal,
            )
        )
    return plans


def _involved_deal_ids(plans: Sequence[DealDuplicatePlan]) -> set[str]:
    ids: set[str] = set()
    for plan in plans:
        for action in plan.actions:
            ids.add(action.target_id)
            ids.update(action.duplicate_ids)
        ids.update(plan.protected_ids)
        ids.update(plan.skipped_ids)
    return ids


def _deal_snapshot(deal: Mapping[str, Any]) -> dict[str, Any]:
    raw = deal.get("raw") if isinstance(deal.get("raw"), Mapping) else {}
    return {
        "id": str(deal.get("id") or raw.get("ID") or "").strip(),
        "title": str(deal.get("title") or raw.get("TITLE") or "").strip(),
        "category_id": str(deal.get("category_id") or raw.get("CATEGORY_ID") or "").strip(),
        "category_name": str(deal.get("category_name") or "").strip(),
        "stage_id": str(deal.get("stage_id") or raw.get("STAGE_ID") or "").strip(),
        "stage_name": str(deal.get("stage_name") or "").strip(),
        "source_id": str(deal.get("source_id") or raw.get("SOURCE_ID") or "").strip(),
        "source_name": str(deal.get("source_name") or "").strip(),
        "source_description": str(deal.get("source_description") or raw.get("SOURCE_DESCRIPTION") or "").strip(),
        "assigned_id": str(deal.get("assigned_id") or raw.get("ASSIGNED_BY_ID") or "").strip(),
        "created_at": str(deal.get("created_at") or raw.get("DATE_CREATE") or "").strip(),
        "updated_at": str(deal.get("updated_at") or raw.get("DATE_MODIFY") or "").strip(),
        "closed": bool(deal.get("closed")),
        "utm_source": str(deal.get("utm_source") or raw.get("UTM_SOURCE") or "").strip(),
        "utm_medium": str(deal.get("utm_medium") or raw.get("UTM_MEDIUM") or "").strip(),
        "utm_campaign": str(deal.get("utm_campaign") or raw.get("UTM_CAMPAIGN") or "").strip(),
        "utm_content": str(deal.get("utm_content") or raw.get("UTM_CONTENT") or "").strip(),
        "utm_term": str(deal.get("utm_term") or raw.get("UTM_TERM") or "").strip(),
    }


def _deal_snapshots_by_id(
    deals: Sequence[Mapping[str, Any]],
    *,
    involved_ids: set[str],
) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for deal in deals:
        deal_id = str(deal.get("id") or "").strip()
        if deal_id and deal_id in involved_ids:
            snapshots[deal_id] = _deal_snapshot(deal)
    return snapshots


def _plan_to_dict(plan: DealDuplicatePlan) -> dict[str, Any]:
    return {
        "domain_key": plan.domain_key,
        "actions": [
            {
                "target_id": action.target_id,
                "duplicate_ids": list(action.duplicate_ids),
                "reason": action.reason,
                "attribution_source_id": action.attribution_source_id,
                "attribution_updates": dict(action.attribution_updates),
            }
            for action in plan.actions
        ],
        "protected_ids": list(plan.protected_ids),
        "skipped_ids": list(plan.skipped_ids),
        "warnings": list(plan.warnings),
    }


def _print_text(plans: Sequence[DealDuplicatePlan], *, deals_count: int) -> None:
    actions_count = sum(len(plan.actions) for plan in plans)
    duplicates_count = sum(len(action.duplicate_ids) for plan in plans for action in plan.actions)
    print("План дедупликации сделок Bitrix24 (dry-run)")
    print(f"Сделок проанализировано: {deals_count}")
    print(f"Доменов с дублями: {len(plans)}")
    print(f"Операций объединения в плане: {actions_count}")
    print(f"Сделок-дублей к объединению: {duplicates_count}")
    if not plans:
        return
    print("")
    for plan in plans:
        print(f"Домен: {plan.domain_key or '-'}")
        for action in plan.actions:
            fields = ", ".join(sorted(action.attribution_updates)) or "нет заполненных полей"
            print(
                f"- основная {action.target_id}; дубли {', '.join(action.duplicate_ids)}; "
                f"атрибуция из {action.attribution_source_id or '-'} ({fields}); {action.reason}"
            )
        if plan.protected_ids:
            print(f"- защищены от изменения: {', '.join(plan.protected_ids)}")
        if plan.skipped_ids:
            print(f"- ручная проверка: {', '.join(plan.skipped_ids)}")
        for warning in plan.warnings:
            print(f"- предупреждение: {warning}")
        print("")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Построить dry-run план объединения дублей сделок Bitrix24.")
    parser.add_argument("--input-json", type=Path, help="Локальный JSON со сделками вместо live Bitrix.")
    parser.add_argument("--limit", type=int, default=int(os.environ.get("BITRIX_DEAL_DUPLICATE_LIMIT", "1000")))
    parser.add_argument("--all", action="store_true", help="Проверить все сделки без лимита.")
    parser.add_argument("--skip-product-rows", action="store_true", help="Не читать товарные строки сделок.")
    parser.add_argument("--remote-bridge", action="store_true", help="Читать Bitrix через server OAuth state bridge.")
    parser.add_argument("--json", action="store_true", help="Вывести машинный JSON вместо текста.")
    parser.add_argument(
        "--domain-field",
        action="append",
        default=[],
        help="Поле, из которого брать домен. Можно указать несколько раз.",
    )
    args = parser.parse_args(argv)

    env = _load_runtime_env()
    limit = None if args.all or args.limit <= 0 else args.limit
    domain_fields = tuple(args.domain_field) if args.domain_field else _domain_fields_from_env(env)
    if args.input_json:
        deals, product_rows = _read_input_json(args.input_json)
    elif args.remote_bridge or str(env.get("BITRIX_DEAL_DUPLICATE_REMOTE_BRIDGE") or "") == "1":
        deals, product_rows = _load_remote_bridge_deals(
            env,
            limit=limit,
            load_product_rows=not args.skip_product_rows,
        )
    else:
        adapter = BitrixSalesAdapter.from_env(env=env)
        deals, product_rows = _load_live_deals(
            adapter,
            limit=limit,
            load_product_rows=not args.skip_product_rows,
        )

    plans = _build_plans(
        deals,
        product_rows_by_deal=product_rows,
        domain_fields=domain_fields,
    )
    if args.json:
        involved_ids = _involved_deal_ids(plans)
        print(
            json.dumps(
                {
                    "deals_count": len(deals),
                    "deals": _deal_snapshots_by_id(deals, involved_ids=involved_ids),
                    "plans": [_plan_to_dict(plan) for plan in plans],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_text(plans, deals_count=len(deals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
