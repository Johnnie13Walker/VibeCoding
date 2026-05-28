#!/usr/bin/env python3
"""Прикладной live-аудит ключевых полей Сделок, Контактов и Компаний."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path("/Users/pro2kuror/Desktop/Cloudbot/architect")
BASE_SCRIPT = ROOT / "scripts" / "bitrix_field_audit_gd324.py"
OUT_XLSX = ROOT / "docs" / "architecture" / "gd-324-core-fields-live.xlsx"
OUT_SUMMARY = ROOT / "docs" / "architecture" / "gd-324-core-fields-live-summary.md"
OUT_JSON = ROOT / "tmp" / "gd324_field_audit" / "gd-324-core-fields-live.json"
CACHE_DIR = ROOT / "tmp" / "gd324_field_audit" / "core_live_cache"


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


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def batch_list(auth, method: str, select_fields: list[str], *, order_field: str = "ID", page_size: int = 50, commands_per_batch: int = 50) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    start = 0
    iteration = 0

    while True:
        iteration += 1
        current_batch = commands_per_batch
        retries_left = 3
        while True:
            commands: dict[str, str] = {}
            for idx in range(current_batch):
                batch_start = start + idx * page_size
                params = {"select": select_fields, "order": {order_field: "ASC"}, "start": batch_start}
                commands[f"c{idx}"] = f"{method}?{query_string(params)}"
            try:
                payload = auth.call_payload("batch", params={"halt": 0, "cmd": commands}, default={})
                break
            except Exception as exc:
                if retries_left > 0:
                    retries_left -= 1
                    log(f"{method}: сетевой сбой на batch={current_batch}, повтор через 2с: {exc}")
                    time.sleep(2)
                    continue
                if current_batch <= 5:
                    raise
                next_batch = max(5, current_batch // 2)
                log(f"{method}: timeout на batch={current_batch}, снижаю до {next_batch}: {exc}")
                current_batch = next_batch
                retries_left = 3

        batch_capacity = current_batch * page_size
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        chunk_map = result.get("result", {}) if isinstance(result, dict) else {}

        got_any = False
        batch_count = 0
        for idx in range(current_batch):
            rows = chunk_map.get(f"c{idx}", [])
            if rows:
                got_any = True
                batch_count += len(rows)
                records.extend(row for row in rows if isinstance(row, dict))
        if not got_any:
            break
        if batch_count < batch_capacity:
            log(f"{method}: итерация {iteration}, записей {len(records)}, финальный батч {batch_count}")
            break
        start += batch_capacity
        log(f"{method}: итерация {iteration}, записей {len(records)}, следующий start={start}")
    return records


IMPORTANT_SYSTEM_CODES = {
    "SOURCE_ID",
    "SOURCE_DESCRIPTION",
    "ASSIGNED_BY_ID",
    "CATEGORY_ID",
    "STAGE_ID",
    "STATUS_ID",
    "TITLE",
    "OPPORTUNITY",
    "COMPANY_ID",
    "CONTACT_ID",
    "COMMENTS",
    "ADDRESS_CITY",
    "ADDRESS_REGION",
    "ADDRESS_PROVINCE",
    "ADDRESS_COUNTRY",
    "WEB",
    "PHONE",
    "EMAIL",
}


def is_important_field(code: str, meta: dict[str, Any]) -> bool:
    if code in IMPORTANT_SYSTEM_CODES:
        return True
    if meta["origin"] == "Кастомное" and base.semantic_key(meta["title"], code):
        return True
    if base.semantic_key(meta["title"], code):
        return True
    return False


def get_field_maps(auth):
    cache_path = CACHE_DIR / "field_maps.json"
    cached = load_json(cache_path)
    if isinstance(cached, dict) and {"field_maps", "status_labels", "categories"} <= set(cached):
        return cached["field_maps"], cached["status_labels"], cached["categories"]

    deal_fields = {
        code: base.normalize_field_meta(code, meta)
        for code, meta in base.field_map_result(base.bitrix_call(auth, "crm.deal.fields")).items()
    }
    contact_fields = {
        code: base.normalize_field_meta(code, meta)
        for code, meta in base.field_map_result(base.bitrix_call(auth, "crm.contact.fields")).items()
    }
    company_fields = {
        code: base.normalize_field_meta(code, meta)
        for code, meta in base.field_map_result(base.bitrix_call(auth, "crm.company.fields")).items()
    }
    status_labels = {
        f"{item.get('ENTITY_ID')}::{item.get('STATUS_ID')}": base.normalize_label(item.get("NAME"))
        for item in base.bitrix_list(auth, "crm.status.list")
    }
    categories = base.list_result(base.bitrix_call(auth, "crm.category.list", {"entityTypeId": 2}))
    payload = {
        "field_maps": {"deal": deal_fields, "contact": contact_fields, "company": company_fields},
        "status_labels": status_labels,
        "categories": categories,
    }
    save_json(cache_path, payload)
    return payload["field_maps"], payload["status_labels"], payload["categories"]


def fetch_records(auth, method: str, field_map: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    cache_key = method.replace(".", "_")
    cache_path = CACHE_DIR / f"{cache_key}.json"
    cached = load_json(cache_path)
    if isinstance(cached, dict) and isinstance(cached.get("rows"), list) and isinstance(cached.get("codes"), list):
        log(f"{method}: беру из cache {len(cached['rows'])} записей")
        return cached["rows"], cached["codes"]

    codes = [code for code, meta in field_map.items() if is_important_field(code, meta)]
    if "ID" not in codes:
        codes.insert(0, "ID")
    log(f"{method}: важных полей {len(codes)}")
    initial_batch = 50 if method == "crm.deal.list" else 10
    rows = batch_list(auth, method, codes, commands_per_batch=initial_batch)
    save_json(cache_path, {"codes": codes, "rows": rows})
    return rows, codes


def make_slices(auth):
    field_maps, status_labels, categories = get_field_maps(auth)
    deals, deal_codes = fetch_records(auth, "crm.deal.list", field_maps["deal"])
    contacts, contact_codes = fetch_records(auth, "crm.contact.list", field_maps["contact"])
    companies, company_codes = fetch_records(auth, "crm.company.list", field_maps["company"])

    slices: list[tuple[Any, dict[str, dict[str, Any]], set[str]]] = []
    categories_by_id = {base.normalize_label(cat.get("id")): base.normalize_label(cat.get("name")) for cat in categories}
    for category_id, category_name in categories_by_id.items():
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
                set(deal_codes),
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
            set(contact_codes),
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
            set(company_codes),
        )
    )
    return slices, {
        "deals_total": len(deals),
        "contacts_total": len(contacts),
        "companies_total": len(companies),
        "deal_categories": categories_by_id,
    }


def shortlist(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    hide_first = []
    standardize_first = []
    merge_first = []

    for row in rows:
        if not row["_analyzed"]:
            continue
        if row["Системное / кастомное"] == "Кастомное" and row["_fill_rate"] == 0:
            hide_first.append(row)
        if row["_semantic_key"] in base.IMPORTANT_SEMANTICS and row["Есть смысловой дубль"] == "Да":
            merge_first.append(row)
        if row["_semantic_key"] in base.IMPORTANT_SEMANTICS and row["_fill_rate"] < 25:
            standardize_first.append(row)

    hide_first = sorted(hide_first, key=lambda r: (r["Сущность"], r["Воронка"], r["Поле"]))[:40]
    merge_first = sorted(merge_first, key=lambda r: (r["_semantic_key"], r["Сущность"], r["Поле"]))[:40]
    standardize_first = sorted(standardize_first, key=lambda r: (r["_fill_rate"], r["_semantic_key"], r["Сущность"]))[:40]
    return {"hide_first": hide_first, "merge_first": merge_first, "standardize_first": standardize_first}


def to_simple_rows(rows: list[dict[str, Any]], *, mode: str) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        if mode == "hide":
            result.append(
                {
                    "Сущность": row["Сущность"],
                    "Воронка": row["Воронка"],
                    "Поле": row["Поле"],
                    "Код поля": row["Код поля"],
                    "% заполнения": base.fmt_pct(row["_fill_rate"]),
                    "Почему": "Кастомное поле с нулевым заполнением",
                    "Действие": "Скрыть первым / проверить перед удалением",
                }
            )
        elif mode == "merge":
            result.append(
                {
                    "Сущность": row["Сущность"],
                    "Воронка": row["Воронка"],
                    "Поле": row["Поле"],
                    "Код поля": row["Код поля"],
                    "Семантика": row["_semantic_key"],
                    "Похожее поле": row["Название дубля / похожего поля"],
                    "Действие": "Объединить / оставить единый стандарт",
                }
            )
        elif mode == "standardize":
            result.append(
                {
                    "Сущность": row["Сущность"],
                    "Воронка": row["Воронка"],
                    "Поле": row["Поле"],
                    "Код поля": row["Код поля"],
                    "% заполнения": base.fmt_pct(row["_fill_rate"]),
                    "Семантика": row["_semantic_key"],
                    "Действие": "Стандартизировать заполнение и owner поля",
                }
            )
    return result


def build_summary(stats: dict[str, Any], unused_rows: list[dict[str, Any]], duplicate_rows: list[dict[str, Any]], standardization_rows: list[dict[str, Any]], lists: dict[str, list[dict[str, Any]]]) -> str:
    return "\n".join(
        [
            "# GD-324: практический shortlist по Сделкам, Контактам и Компаниям",
            "",
            f"Подготовлено: `{base.MOSCOW_NOW} МСК`",
            "",
            "## Охват",
            "",
            f"- Сделки: `{stats['deals_total']}` карточек",
            f"- Контакты: `{stats['contacts_total']}` карточек",
            f"- Компании: `{stats['companies_total']}` карточек",
            "",
            "## Что делать первым",
            "",
            f"- Скрыть в первую очередь: `{len(lists['hide_first'])}` полей из shortlist.",
            f"- Объединить в первую очередь: `{len(lists['merge_first'])}` полей/вариантов из shortlist.",
            f"- Стандартизировать в первую очередь: `{len(lists['standardize_first'])}` полей из shortlist.",
            "",
            "## Общие цифры",
            "",
            f"- Полностью пустых кастомных полей в live-ядре: `{len(unused_rows)}`.",
            f"- Строк по смысловым дублям: `{len(duplicate_rows)}`.",
            f"- Кандидатов на стандартизацию: `{len(standardization_rows)}`.",
            "",
            "## Основной вывод",
            "",
            "- Главный мусор сидит в сделках: там и самая тяжёлая сетка кастомных полей, и основной риск перегрузки карточки.",
            "- Контакты и компании тоже перегружены, но основной управленческий эффект даст чистка именно сделочного контура.",
            "- Первым делом надо убирать полностью пустые кастомные поля и сводить в один стандарт source/source_detail, client_type, segment, next_step, next_contact_date, rejection_reason.",
            "",
            "## Ограничения",
            "",
            "- Использование в карточках, роботах и БП требует ручной проверки в интерфейсе Bitrix24.",
        ]
    )


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    slices, stats = make_slices(base.make_auth())

    all_rows: list[dict[str, Any]] = []
    for entity_slice, field_map, analyzed_codes in slices:
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
    lists = shortlist(all_rows)

    wb = base.Workbook()
    wb.remove(wb.active)
    visible_rows = [{key: value for key, value in row.items() if not key.startswith("_")} for row in all_rows]
    base.write_sheet(wb, "Все поля", visible_rows)
    base.write_sheet(wb, "Неиспользуемые поля", unused_rows)
    base.write_sheet(wb, "Дублирующие поля", duplicate_rows)
    base.write_sheet(wb, "Поля для объединения", merge_rows)
    base.write_sheet(wb, "Поля для стандартизации", standardization_rows)
    base.write_sheet(wb, "Итоговые рекомендации", final_recommendations)
    base.write_sheet(wb, "Скрыть первым", to_simple_rows(lists["hide_first"], mode="hide"))
    base.write_sheet(wb, "Объединить первым", to_simple_rows(lists["merge_first"], mode="merge"))
    base.write_sheet(wb, "Стандартизировать первым", to_simple_rows(lists["standardize_first"], mode="standardize"))
    wb.save(OUT_XLSX)

    OUT_SUMMARY.write_text(build_summary(stats, unused_rows, duplicate_rows, standardization_rows, lists), encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "stats": stats,
                "unused_rows": unused_rows,
                "duplicate_rows": duplicate_rows,
                "standardization_rows": standardization_rows,
                "hide_first": to_simple_rows(lists["hide_first"], mode="hide"),
                "merge_first": to_simple_rows(lists["merge_first"], mode="merge"),
                "standardize_first": to_simple_rows(lists["standardize_first"], mode="standardize"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(OUT_XLSX)
    print(OUT_SUMMARY)
    print(json.dumps({"rows": len(visible_rows), "unused": len(unused_rows), "duplicates": len(duplicate_rows), **stats}, ensure_ascii=False))


if __name__ == "__main__":
    main()
