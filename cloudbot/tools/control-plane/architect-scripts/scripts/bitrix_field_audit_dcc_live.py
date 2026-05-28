#!/usr/bin/env python3
"""Live factual audit for deals, contacts, companies."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path("/Users/pro2kuror/Desktop/Cloudbot/architect")
BASE_SCRIPT = ROOT / "scripts" / "bitrix_field_audit_gd324.py"
OUTPUT_XLSX = ROOT / "docs" / "architecture" / "gd-324-deals-contacts-companies-field-audit-live.xlsx"
OUTPUT_SUMMARY = ROOT / "docs" / "architecture" / "gd-324-deals-contacts-companies-field-audit-live-summary.md"
OUTPUT_JSON = ROOT / "tmp" / "gd324_field_audit" / "gd324_deals_contacts_companies_live.json"


def load_base():
    spec = importlib.util.spec_from_file_location("bitrix_field_audit_gd324", BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = load_base()


def log(message: str) -> None:
    print(message, flush=True)


def query_string(params: dict[str, Any]) -> str:
    pairs: list[tuple[str, str]] = []

    def walk(prefix: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for key, nested in value.items():
                walk(f"{prefix}[{key}]" if prefix else str(key), nested)
            return
        if isinstance(value, (list, tuple, set)):
            for nested in value:
                walk(f"{prefix}[]", nested)
            return
        pairs.append((prefix, str(value)))

    for key, value in params.items():
        walk(str(key), value)
    return urllib.parse.urlencode(pairs)


def batch_list(auth, method: str, select_fields: list[str], *, order_field: str = "ID", page_size: int = 50, commands_per_batch: int = 10) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    start = 0
    iteration = 0
    batch_capacity = commands_per_batch * page_size
    while True:
        iteration += 1
        commands: dict[str, str] = {}
        starts: list[int] = []
        for idx in range(commands_per_batch):
            batch_start = start + idx * page_size
            starts.append(batch_start)
            params = {"select": select_fields, "order": {order_field: "ASC"}, "start": batch_start}
            commands[f"c{idx}"] = f"{method}?{query_string(params)}"
        payload = auth.call_payload("batch", params={"halt": 0, "cmd": commands}, default={})
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        chunk_map = result.get("result", {}) if isinstance(result, dict) else {}
        got_any = False
        batch_count = 0
        for idx in range(commands_per_batch):
            rows = chunk_map.get(f"c{idx}", [])
            if rows:
                got_any = True
                records.extend(row for row in rows if isinstance(row, dict))
                batch_count += len(rows)
        if not got_any:
            break
        if batch_count < batch_capacity:
            log(f"{method}: batch-iteration={iteration}, records={len(records)}, final_batch={batch_count}")
            break
        start += batch_capacity
        log(f"{method}: batch-iteration={iteration}, records={len(records)}, next_start={start}")
    return records


def fetch_entity_records(auth, method: str, *, order_field: str = "ID") -> list[dict[str, Any]]:
    select_fields = ["*", "UF_*"]
    log(f"{method}: wildcard sweep")
    rows = batch_list(auth, method, select_fields, order_field=order_field)
    log(f"{method}: total records={len(rows)}")
    return rows


def fetch_all() -> tuple[list[tuple[Any, dict[str, dict[str, Any]]]], dict[str, Any]]:
    auth = base.make_auth()
    field_maps, _, _, deal_categories, status_labels = base.entity_field_maps(auth)

    log("Live sweep: deals")
    deals = fetch_entity_records(auth, "crm.deal.list")
    log("Live sweep: contacts")
    contacts = fetch_entity_records(auth, "crm.contact.list")
    log("Live sweep: companies")
    companies = fetch_entity_records(auth, "crm.company.list")

    deal_categories_by_id = {base.normalize_label(cat.get("id")): base.normalize_label(cat.get("name")) for cat in deal_categories}

    slices: list[tuple[Any, dict[str, dict[str, Any]]]] = []
    for category_id, category_name in deal_categories_by_id.items():
        category_records = [item for item in deals if base.normalize_label(item.get("CATEGORY_ID")) == category_id]
        slices.append(
            (
                base.EntitySlice(
                    entity_name="Сделки",
                    category_name=category_name,
                    category_id=category_id,
                    stage_field="STAGE_ID",
                    stage_labels=base.stage_label_map(status_labels, f"DEAL_STAGE_{category_id}"),
                    records=category_records,
                ),
                field_maps["deal"],
            )
        )

    slices.append(
        (
            base.EntitySlice(
                entity_name="Контакты",
                category_name="",
                category_id="",
                stage_field=None,
                stage_labels={},
                records=contacts,
            ),
            field_maps["contact"],
        )
    )
    slices.append(
        (
            base.EntitySlice(
                entity_name="Компании",
                category_name="",
                category_id="",
                stage_field=None,
                stage_labels={},
                records=companies,
            ),
            field_maps["company"],
        )
    )

    stats = {
        "deals_total": len(deals),
        "contacts_total": len(contacts),
        "companies_total": len(companies),
        "deal_categories": deal_categories_by_id,
    }
    return slices, stats


def build_summary(rows: list[dict[str, Any]], stats: dict[str, Any], unused_rows: list[dict[str, Any]], duplicate_rows: list[dict[str, Any]], standardization_rows: list[dict[str, Any]]) -> str:
    sales_rows = [row for row in rows if row["Сущность"] == "Сделки"]
    low_fill_sales = [row for row in sales_rows if row["Системное / кастомное"] == "Кастомное" and row["_analyzed"] and row["_fill_rate"] < 2]
    important_weak = [row for row in rows if row["_analyzed"] and row["_semantic_key"] in base.IMPORTANT_SEMANTICS and row["_fill_rate"] < 15]
    return "\n".join(
        [
            "# GD-324: live summary по полям Сделок, Контактов и Компаний",
            "",
            f"Подготовлено: `{base.MOSCOW_NOW} МСК`",
            "",
            "## Охват",
            "",
            f"- Сделки: `{stats['deals_total']}` карточек",
            f"- Контакты: `{stats['contacts_total']}` карточек",
            f"- Компании: `{stats['companies_total']}` карточек",
            "",
            "## Что плохо",
            "",
            f"- Проанализировано `{len(rows)}` строк полей по ядру CRM.",
            f"- Найдено `{len(unused_rows)}` полностью пустых кастомных полей в live-данных.",
            f"- Найдено `{len(duplicate_rows)}` строк по смысловым дублям.",
            f"- Найдено `{len(standardization_rows)}` кандидатов на стандартизацию.",
            f"- В сделках есть `{len(low_fill_sales)}` кастомных полей с заполнением ниже `2%`.",
            f"- Коммерчески важные поля с низкой заполненностью: `{len(important_weak)}`.",
            "",
            "## С чего начать",
            "",
            "1. Скрыть полностью пустые кастомные поля.",
            "2. Объединить дубли по source/source_detail, client_type, segment, next_step, next_contact_date, rejection_reason.",
            "3. Отдельно почистить сделочные карточки: там основной перегруз.",
            "4. Проверить руками, какие поля реально сидят в карточках, роботах и БП.",
            "",
            "## Ограничения",
            "",
            "- Использование в бизнес-процессах и роботах по-прежнему требует ручной проверки.",
            "- Доли заполнения посчитаны по live-выгрузке ядра CRM, но не по смарт-процессам.",
        ]
    )


def main() -> None:
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    slices, stats = fetch_all()
    all_rows: list[dict[str, Any]] = []
    for entity_slice, field_map in slices:
        analyzed_codes = set(base.select_codes_for_analysis(field_map, dynamic=False))
        rows = base.entity_usage_rows(
            entity_slice.entity_name,
            entity_slice.category_name,
            field_map,
            entity_slice.records,
            entity_slice.stage_field,
            entity_slice.stage_labels,
            analyzed_codes=analyzed_codes,
        )
        all_rows.extend(rows)

    duplicate_groups, duplicate_rows = base.build_duplicate_index(all_rows)
    base.apply_recommendations(all_rows, duplicate_groups)
    unused_rows = base.make_unused_rows(all_rows)
    merge_rows = base.make_merge_rows(duplicate_rows)
    standardization_rows = base.make_standardization_rows(all_rows)
    final_recommendations = base.make_final_recommendations(all_rows)

    workbook = base.Workbook()
    workbook.remove(workbook.active)
    visible_rows = [{key: value for key, value in row.items() if not key.startswith("_")} for row in all_rows]
    base.write_sheet(workbook, "Все поля", visible_rows)
    base.write_sheet(workbook, "Неиспользуемые поля", unused_rows)
    base.write_sheet(workbook, "Дублирующие поля", duplicate_rows)
    base.write_sheet(workbook, "Поля для объединения", merge_rows)
    base.write_sheet(workbook, "Поля для стандартизации", standardization_rows)
    base.write_sheet(workbook, "Итоговые рекомендации", final_recommendations)
    workbook.save(OUTPUT_XLSX)

    OUTPUT_JSON.write_text(
        json.dumps(
            {
                "stats": stats,
                "rows": visible_rows,
                "unused_rows": unused_rows,
                "duplicate_rows": duplicate_rows,
                "standardization_rows": standardization_rows,
                "final_recommendations": final_recommendations,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    OUTPUT_SUMMARY.write_text(build_summary(all_rows, stats, unused_rows, duplicate_rows, standardization_rows), encoding="utf-8")
    print(OUTPUT_XLSX)
    print(OUTPUT_SUMMARY)
    print(json.dumps({"rows": len(visible_rows), "unused": len(unused_rows), "duplicates": len(duplicate_rows), **stats}, ensure_ascii=False))


if __name__ == "__main__":
    main()
