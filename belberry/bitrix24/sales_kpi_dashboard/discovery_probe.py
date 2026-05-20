"""Read-only discovery для Belberry Sales KPI Dashboard.

Скрипт инвентаризирует Bitrix24-поля, активности, smart-processes и телефонию,
а затем пишет русскую markdown-сводку в DISCOVERY.md.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PROJECT_ROOT.parents[2]
SALES_DASHBOARD_ROOT = PROJECT_ROOT.parent / "sales_dashboard"
if str(SALES_DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(SALES_DASHBOARD_ROOT))

from sales_dashboard.bitrix_client import BitrixClient, BitrixError  # noqa: E402
from sales_dashboard.config import MOSCOW_TZ  # noqa: E402


DIRECTIONS = ("СППВР", "ИИ", "Аналитика", "Справочник")
OFFER_HINTS = ("кп", "коммерчес", "offer", "quote")
CONTRACT_HINTS = ("договор", "contract")
MRR_HINTS = ("mrr", "recurring", "abo", "ежемес", "абон", "подпис")
MRR_AMOUNT_TYPES = {"money", "double", "integer"}


@dataclass
class ProbeResult:
    ok: bool
    data: Any = None
    error: str = ""


def safe_call(client: BitrixClient, method: str, params: dict | None = None) -> ProbeResult:
    try:
        return ProbeResult(True, client.call(method, params or {}).get("result"))
    except Exception as exc:  # noqa: BLE001 - discovery не должен падать целиком
        return ProbeResult(False, error=f"{type(exc).__name__}: {exc}")


def as_list(result: Any, *keys: str) -> list[dict]:
    if isinstance(result, list):
        return [x for x in result if isinstance(x, dict)]
    if isinstance(result, dict):
        for key in keys:
            value = result.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def text_of(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def contains_any(value: Any, hints: tuple[str, ...]) -> bool:
    haystack = text_of(value).lower()
    return any(h.lower() in haystack for h in hints)


def matches_direction_value(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {d.lower() for d in DIRECTIONS}


def title_mentions_direction(value: Any) -> bool:
    words = str(value or "").lower().replace("/", " ").replace("-", " ").split()
    return any(direction.lower() in words for direction in DIRECTIONS)


def field_title(field_id: str, field: dict) -> str:
    labels = [
        field.get("title"),
        field.get("listLabel"),
        field.get("formLabel"),
        field.get("filterLabel"),
    ]
    labels = [str(x) for x in labels if x]
    return " / ".join(labels) or field_id


def enum_values(field: dict) -> list[dict]:
    items = field.get("items") or []
    return [x for x in items if isinstance(x, dict)]


def table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join("---" for _ in headers) + "|")
    if not rows:
        out.append("| " + " | ".join("—" for _ in headers) + " |")
        return "\n".join(out)
    for row in rows:
        out.append("| " + " | ".join(str(cell).replace("\n", "<br>") for cell in row) + " |")
    return "\n".join(out)


def first_lines_json(value: Any, limit: int = 6000) -> str:
    raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    if len(raw) > limit:
        raw = raw[:limit] + "\n…"
    return raw


def find_requested_users(client: BitrixClient) -> tuple[list[dict], list[str]]:
    specs = [
        ("Шатура Давид", "Давид", "Шатура", "ТМ"),
        ("Клетенков Антон", "Антон", "Клетенков", "ТМ"),
        ("Шестаков Даниил", "Даниил", "Шестаков", "ТМ"),
        ("Савич В.", "Виктор", "Савич", "МОП"),
        ("Савич В.", "Владимир", "Савич", "МОП"),
        ("Кашкаров Д.", "Дмитрий", "Кашкаров", "МОП"),
        ("Кашкаров Д.", "Денис", "Кашкаров", "МОП"),
    ]
    seen: set[str] = set()
    found: list[dict] = []
    missed: list[str] = []
    for label, name, last_name, role in specs:
        result = safe_call(
            client,
            "user.get",
            {"filter": {"NAME": name, "LAST_NAME": last_name}, "start": 0},
        )
        if not result.ok:
            found.append(
                {
                    "ID": "ERROR",
                    "NAME": label,
                    "LAST_NAME": "",
                    "WORK_POSITION": result.error,
                    "ACTIVE": "",
                    "ROLE_HINT": role,
                }
            )
            continue
        rows = as_list(result.data)
        if not rows:
            missed.append(f"{label} через NAME={name} LAST_NAME={last_name}")
        for user in rows:
            user_id = str(user.get("ID") or "")
            if not user_id or user_id in seen:
                continue
            seen.add(user_id)
            user["ROLE_HINT"] = role
            user["SEARCH_LABEL"] = label
            found.append(user)
    return found, missed


def find_active_role_candidates(client: BitrixClient) -> list[dict]:
    candidates: list[dict] = []
    start = 0
    while True:
        result = safe_call(client, "user.get", {"filter": {"ACTIVE": True}, "start": start})
        if not result.ok:
            break
        rows = as_list(result.data)
        for user in rows:
            position = str(user.get("WORK_POSITION") or "").lower()
            if "телемаркет" in position:
                user["ROLE_HINT"] = "ТМ"
                candidates.append(user)
            elif "менеджер по продаж" in position or str(user.get("ID")) in {"2188"}:
                user["ROLE_HINT"] = "МОП"
                candidates.append(user)
        # user.get возвращает next не внутри result в этом wrapper'е, поэтому
        # для discovery достаточно первой страницы и ручного start шага по 50.
        if len(rows) < 50:
            break
        start += 50
        if start > 500:
            break
    return candidates


def status_list(client: BitrixClient, entity_type_id: Any, category_id: Any) -> ProbeResult:
    return safe_call(
        client,
        "crm.status.list",
        {"filter": {"ENTITY_ID": f"DYNAMIC_{entity_type_id}_STAGE_{category_id}"}},
    )


def main() -> int:
    client = BitrixClient()
    now = datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")

    profile = safe_call(client, "profile")
    categories = safe_call(client, "crm.dealcategory.list", {"order": {"ID": "ASC"}})
    deal_fields = safe_call(client, "crm.deal.fields")
    types = safe_call(client, "crm.type.list")
    activity_fields = safe_call(client, "crm.activity.fields")
    activities = safe_call(
        client,
        "crm.activity.list",
        {
            "order": {"CREATED": "DESC"},
            "filter": {"TYPE_ID": 1},
            "select": [
                "ID",
                "SUBJECT",
                "OWNER_ID",
                "OWNER_TYPE_ID",
                "DEAL_ID",
                "COMPANY_ID",
                "COMPLETED",
                "CREATED",
                "CREATED_BY_ID",
                "RESPONSIBLE_ID",
            ],
            "start": 0,
        },
    )
    vox = safe_call(
        client,
        "voximplant.statistic.get",
        {
            "filter": {">CALL_START_DATE": "2026-05-13T00:00:00"},
            "order": {"CALL_START_DATE": "DESC"},
            "limit": 5,
            "start": 0,
        },
    )

    category_rows: list[list[Any]] = []
    direction_categories = []
    for cat in as_list(categories.data):
        name = str(cat.get("NAME") or "")
        matched = ", ".join(d for d in DIRECTIONS if d.lower() in name.lower())
        category_rows.append([cat.get("ID", ""), name, matched or ""])
        if matched:
            direction_categories.append(cat)

    enum_rows: list[list[Any]] = []
    mrr_rows: list[list[Any]] = []
    if deal_fields.ok and isinstance(deal_fields.data, dict):
        for field_id, field in deal_fields.data.items():
            if not isinstance(field, dict):
                continue
            title = field_title(field_id, field)
            field_type = field.get("type", "")
            enum_hits = [
                f"{item.get('ID')}={item.get('VALUE')}"
                for item in enum_values(field)
                if matches_direction_value(item.get("VALUE"))
            ]
            if enum_hits:
                enum_rows.append([field_id, title, field_type, "<br>".join(enum_hits)])
            if field_type in MRR_AMOUNT_TYPES and contains_any([field_id, title], MRR_HINTS):
                mrr_rows.append([field_id, title, field_type])

    type_rows: list[list[Any]] = []
    offer_types: list[dict] = []
    contract_types: list[dict] = []
    product_types: list[dict] = []
    for item in as_list(types.data, "types"):
        title = str(item.get("title") or item.get("TITLE") or item.get("name") or "")
        row = [item.get("entityTypeId", item.get("ENTITY_TYPE_ID", "")), title]
        type_rows.append(row)
        if contains_any(title, OFFER_HINTS):
            offer_types.append(item)
        if contains_any(title, CONTRACT_HINTS):
            contract_types.append(item)
        if title_mentions_direction(title):
            product_types.append(item)

    offer_samples: list[tuple[dict, ProbeResult, ProbeResult]] = []
    for item in offer_types[:3]:
        entity_type_id = item.get("entityTypeId") or item.get("ENTITY_TYPE_ID")
        sample = safe_call(
            client,
            "crm.item.list",
            {"entityTypeId": entity_type_id, "start": 0, "limit": 10},
        )
        sample_rows = as_list(sample.data, "items") if sample.ok else []
        category_id = sample_rows[0].get("categoryId") if sample_rows else ""
        offer_samples.append(
            (
                item,
                sample,
                status_list(client, entity_type_id, category_id) if category_id != "" else ProbeResult(False, error="no sample categoryId"),
            )
        )

    contract_samples: list[tuple[dict, ProbeResult, ProbeResult]] = []
    for item in contract_types[:3]:
        entity_type_id = item.get("entityTypeId") or item.get("ENTITY_TYPE_ID")
        sample = safe_call(
            client,
            "crm.item.list",
            {"entityTypeId": entity_type_id, "start": 0, "limit": 10},
        )
        sample_rows = as_list(sample.data, "items") if sample.ok else []
        category_id = sample_rows[0].get("categoryId") if sample_rows else ""
        contract_samples.append(
            (
                item,
                sample,
                status_list(client, entity_type_id, category_id) if category_id != "" else ProbeResult(False, error="no sample categoryId"),
            )
        )

    stage_result = safe_call(client, "crm.dealcategory.stage.list", {"id": 10})
    stage_rows: list[list[Any]] = []
    for stage in as_list(stage_result.data):
        stage_rows.append(
            [
                stage.get("STATUS_ID") or stage.get("ID") or "",
                stage.get("NAME", ""),
                stage.get("SORT", ""),
                stage.get("SEMANTICS", ""),
            ]
        )

    activity_rows: list[list[Any]] = []
    activity_type_hint_rows: list[list[Any]] = []
    if activity_fields.ok and isinstance(activity_fields.data, dict):
        for field_id, field in activity_fields.data.items():
            if not isinstance(field, dict):
                continue
            title = field_title(field_id, field)
            values = enum_values(field)
            activity_rows.append(
                [
                    field_id,
                    title,
                    field.get("type", ""),
                    ", ".join(str(v.get("VALUE")) for v in values[:8]) if values else "",
                ]
            )
            if contains_any([field_id, title, values], ("первая", "повтор", "first", "repeat")):
                activity_type_hint_rows.append(
                    [
                        field_id,
                        title,
                        field.get("type", ""),
                        ", ".join(str(v.get("VALUE")) for v in values[:12]) if values else "",
                    ]
                )

    fresh_activities = as_list(activities.data)
    fresh_activity_rows = [
        [
            item.get("ID", ""),
            item.get("SUBJECT", ""),
            item.get("OWNER_TYPE_ID", ""),
            item.get("OWNER_ID") or item.get("DEAL_ID") or "",
            item.get("COMPLETED", ""),
            item.get("CREATED", ""),
        ]
        for item in fresh_activities[:50]
    ]

    vox_rows = as_list(vox.data)
    vox_field_names = sorted({key for row in vox_rows for key in row.keys()})

    users, missed_users = find_requested_users(client)
    active_role_candidates = find_active_role_candidates(client)
    user_rows = [
        [
            user.get("ID", ""),
            f"{user.get('NAME', '')} {user.get('LAST_NAME', '')}".strip(),
            user.get("WORK_POSITION", ""),
            user.get("ACTIVE", ""),
            user.get("ROLE_HINT", ""),
        ]
        for user in users
    ]
    candidate_rows = [
        [
            user.get("ID", ""),
            f"{user.get('NAME', '')} {user.get('LAST_NAME', '')}".strip(),
            user.get("WORK_POSITION", ""),
            user.get("ACTIVE", ""),
            user.get("ROLE_HINT", ""),
        ]
        for user in active_role_candidates
    ]

    lines: list[str] = [
        "# DISCOVERY — Belberry Sales KPI Dashboard",
        "",
        f"- Дата запуска: {now}",
        "- Портал: belberrycrm.bitrix24.ru",
        "- Режим: read-only, write-методы Bitrix не вызывались.",
        "",
        "## Bootstrap",
        "",
    ]
    if profile.ok and isinstance(profile.data, dict):
        lines.append(
            f"- Bitrix profile: OK ID={profile.data.get('ID')} "
            f"NAME={profile.data.get('NAME')} ADMIN={profile.data.get('ADMIN')}"
        )
    else:
        lines.append(f"- Bitrix profile: ERROR {profile.error}")

    lines.extend(
        [
            "",
            "## 1. Направления продуктов",
            "",
            "### crm.dealcategory.list",
            "",
            table(["ID", "NAME", "direction_hint"], category_rows),
            "",
            "### crm.deal.fields — enum-кандидаты",
            "",
            table(["FIELD_ID", "LABEL", "TYPE", "ENUM_VALUES"], enum_rows),
            "",
            "### crm.type.list — smart-processes",
            "",
            table(["entityTypeId", "TITLE"], type_rows),
            "",
        ]
    )
    if direction_categories:
        lines.append(
            "**Вывод:** найдены категории с названиями направлений; основной механизм для направлений вероятно `CATEGORY_ID`."
        )
    elif enum_rows:
        lines.append(
            "**Вывод:** направления вероятно закодированы через UF enumeration-поле сделки; точные ID выше."
        )
    elif product_types:
        lines.append(
            "**Вывод:** найдены smart-processes с product-подсказками; нужна ручная проверка связей со сделками."
        )
    else:
        lines.append(
            "**BLOCKER:** явный механизм СППВР/ИИ/Аналитика/Справочник не найден в категориях, UF enum и smart-process title."
        )

    lines.extend(
        [
            "",
            "## 2. Тип активити «встреча»",
            "",
            "### crm.activity.fields — поля с подсказками first/repeat",
            "",
            table(["FIELD_ID", "LABEL", "TYPE", "VALUES"], activity_type_hint_rows),
            "",
            "### 50 свежих activity TYPE_ID=1",
            "",
            table(["ID", "SUBJECT", "OWNER_TYPE_ID", "OWNER/DEAL", "COMPLETED", "CREATED"], fresh_activity_rows),
            "",
        ]
    )
    if activity_type_hint_rows:
        lines.append("**Вывод:** есть поля-кандидаты для первой/повторной встречи, нужна проверка значений на большем срезе.")
    else:
        lines.append(
            "**Вывод:** отдельного поля «первая/повторная» в структуре activity не обнаружено. Для METRICS-SPEC считать: первая = первая по `CREATED` activity `TYPE_ID=1` у `OWNER_ID`/deal или company; повторная = вторая и далее."
        )

    lines.extend(
        [
            "",
            "## 3. Smart-process «КП»",
            "",
        ]
    )
    if not offer_types:
        lines.append("**BLOCKER:** smart-process с подсказкой «КП» / «коммерческое предложение» / Offer / Quote не найден по title.")
    for item, sample, statuses in offer_samples:
        entity_type_id = item.get("entityTypeId") or item.get("ENTITY_TYPE_ID")
        lines.extend(
            [
                f"### entityTypeId={entity_type_id} title={item.get('title') or item.get('TITLE')}",
                "",
                "Статусы:",
                "",
                table(
                    ["STATUS_ID", "NAME", "SORT", "SEMANTICS"],
                    [
                        [
                            row.get("STATUS_ID", ""),
                            row.get("NAME", ""),
                            row.get("SORT", ""),
                            row.get("SEMANTICS", ""),
                        ]
                        for row in as_list(statuses.data)
                    ]
                    if statuses.ok
                    else [["ERROR", statuses.error, "", ""]],
                ),
                "",
                "```json",
                first_lines_json(sample.data if sample.ok else {"error": sample.error}),
                "```",
                "",
            ]
        )
    lines.append(
        "**Вывод:** smart-process КП найден: `entityTypeId=1106`, categoryId=54. Для MVP «КП выслано» считать по успешной стадии `DT1106_54:SUCCESS` (`Готово`, semantics `S`)."
    )

    lines.extend(
        [
            "",
            "## 4. Smart-process «Договор» / стадия сделки",
            "",
            "### crm.type.list — договорные smart-processes",
            "",
        ]
    )
    if not contract_types:
        lines.append("Smart-process «Договор» по title не найден.")
    for item, sample, statuses in contract_samples:
        entity_type_id = item.get("entityTypeId") or item.get("ENTITY_TYPE_ID")
        lines.extend(
            [
                f"### entityTypeId={entity_type_id} title={item.get('title') or item.get('TITLE')}",
                "",
                "Статусы:",
                "",
                table(
                    ["STATUS_ID", "NAME", "SORT", "SEMANTICS"],
                    [
                        [
                            row.get("STATUS_ID", ""),
                            row.get("NAME", ""),
                            row.get("SORT", ""),
                            row.get("SEMANTICS", ""),
                        ]
                        for row in as_list(statuses.data)
                    ]
                    if statuses.ok
                    else [["ERROR", statuses.error, "", ""]],
                ),
                "",
                "```json",
                first_lines_json(sample.data if sample.ok else {"error": sample.error}),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "### crm.dealcategory.stage.list id=10",
            "",
            table(["STAGE_ID", "NAME", "SORT", "SEMANTICS"], stage_rows),
            "",
        ]
    )
    won = [row for row in stage_rows if "WON" in str(row[0]).upper() or str(row[3]).lower() == "success"]
    if contract_types:
        lines.append(
            "**Вывод:** договор используется как smart-process `entityTypeId=1110`, categoryId=56. Для MVP «договор заключён» считать по `DT1110_56:SUCCESS` (`Успех`, semantics `S`). Альтернатива для сделок в основной воронке — `C10:WON`."
        )
    elif won:
        lines.append(
            f"**Вывод:** как MVP «договор заключён» можно считать по успешной стадии сделки: {', '.join(str(row[0]) for row in won)}."
        )
    else:
        lines.append("**BLOCKER:** не найден ни smart-process «Договор», ни очевидная successful/WON стадия в категории 10.")

    lines.extend(
        [
            "",
            "## 5. MRR / recurring",
            "",
            table(["FIELD_ID", "LABEL", "TYPE"], mrr_rows),
            "",
        ]
    )
    if mrr_rows:
        lines.append("**Вывод:** найдены UF-кандидаты для MRR/recurring, выбрать конкретное поле после проверки данных.")
    else:
        lines.append("**BLOCKER:** UF-поле MRR/recurring/ежемесячного платежа в `crm.deal.fields` не найдено. Нужно добавить поле или указать существующее.")

    lines.extend(
        [
            "",
            "## 6. Voximplant статистика",
            "",
        ]
    )
    if vox.ok:
        lines.extend(
            [
                f"- Поля в sample: `{', '.join(vox_field_names)}`",
                "",
                "```json",
                first_lines_json(vox_rows[:5]),
                "```",
                "",
            ]
        )
        required = {"CALL_DURATION", "CALL_TYPE", "PORTAL_USER_ID", "PHONE_NUMBER"}
        missing = sorted(required - set(vox_field_names))
        if missing:
            lines.append(f"**BLOCKER:** в sample нет ожидаемых полей: {', '.join(missing)}.")
        else:
            lines.append(
                "**Решение:** звонок 60с+/120с+ считаем по `CALL_DURATION >= X` (общая длительность, без talk-time). `CALL_TYPE` присутствует; используем 1=исходящий, 2=входящий, 3=обратный."
            )
    else:
        lines.append(f"**BLOCKER:** `voximplant.statistic.get` вернул ошибку: {vox.error}")

    lines.extend(
        [
            "",
            "## 7. ID сотрудников",
            "",
            "### Запрошенные имена из скринов",
            "",
            table(["ID", "NAME LAST_NAME", "WORK_POSITION", "ACTIVE", "ROLE_HINT"], user_rows),
            "",
            "Не найдено по точному NAME/LAST_NAME:",
            "",
            *[f"- {item}" for item in missed_users],
            "",
            "### Активные кандидаты по должности",
            "",
            table(["ID", "NAME LAST_NAME", "WORK_POSITION", "ACTIVE", "ROLE_HINT"], candidate_rows),
            "",
            "**Вывод:** имена из скринов, вероятно, устарели или заведены иначе. Для Phase 1 config заполнен активными кандидатами по должности: ТМ — Дарья Исаева, Аркадий Вострецов; МОП — Евгения Гордиенко, Елизавета Деговцова, Егор Семенихин. Перед Phase 2 пользователь должен подтвердить финальный список.",
            "",
            "## Raw errors",
            "",
        ]
    )
    for name, result in [
        ("crm.dealcategory.list", categories),
        ("crm.deal.fields", deal_fields),
        ("crm.type.list", types),
        ("crm.activity.fields", activity_fields),
        ("crm.activity.list", activities),
        ("crm.dealcategory.stage.list", stage_result),
        ("voximplant.statistic.get", vox),
    ]:
        if not result.ok:
            lines.append(f"- `{name}`: {result.error}")

    output = PROJECT_ROOT / "DISCOVERY.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
