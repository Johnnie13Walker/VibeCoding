"""HTML-форматирование управленческих sales-отчетов для Telegram."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from shared.contracts.sales_report_format_contract import (
    FORMATTER_MODULE,
    REPORT_FORMATS,
    REPORT_REQUIRED_MARKERS,
    SALES_REPORT_FORMAT_VERSION,
    report_format_metadata,
    report_required_markers,
)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
DEFAULT_TELEMARKETING_MIN_DIALS = 40
DEFAULT_TELEMARKETING_HIGH_DIALS = 30
DEFAULT_TELEMARKETING_VERY_LOW_CALLS = 1
DEFAULT_ACTIVE_CLIENT_MINUTES_TARGET = 300
DEFAULT_EMPTY_DIAL_MINUTES = 1.5
DEFAULT_EMPTY_DIAL_MINUTES_CAP = 90
DEFAULT_SM_CALL_MINUTES = 15
DEFAULT_TM_CALL_MINUTES = 12
DEFAULT_CHAT_DIALOG_MINUTES = 10
DEFAULT_MEETING_MINUTES = 50
TOP_OPERATIONAL_ENGAGEMENT_MIN = 9.0
SURNAME_SUFFIXES = (
    "ов",
    "ова",
    "ев",
    "ева",
    "ин",
    "ина",
    "ын",
    "ына",
    "ский",
    "ская",
    "цкий",
    "цкая",
    "енко",
    "енко",
    "ук",
    "юк",
    "чук",
    "як",
    "дзе",
    "швили",
    "ян",
)
RU_MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def report_marker_status(report_type: str, text: Any) -> dict[str, list[str]]:
    rendered = str(text or "")
    required = report_required_markers(report_type)
    present: list[str] = []
    missing: list[str] = []
    for marker in required:
        escaped_marker = escape(str(marker), quote=False)
        if marker in rendered or escaped_marker in rendered:
            present.append(marker)
        else:
            missing.append(marker)
    return {
        "present": present,
        "missing": missing,
    }


def _format_money(amount: float | int | None) -> str:
    if amount in (None, ""):
        return "данных недостаточно"
    return f"{int(round(float(amount))):,}".replace(",", " ") + " ₽"


def _money_html(amount: float | int | None) -> str:
    return f"<b>{_safe(_format_money(amount))}</b>"


def _heading_html(value: Any) -> str:
    return f"<b>{_safe(value)}</b>"


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return "без даты"
    return value.astimezone(MOSCOW_TZ).strftime("%d.%m %H:%M")


def _safe(value: Any) -> str:
    return escape(str(value or "").strip(), quote=False)


def _safe_attr(value: Any) -> str:
    return escape(str(value or "").strip(), quote=True)


def _short_title(value: Any, *, max_len: int = 72) -> str:
    raw = str(value or "").strip()
    if len(raw) <= max_len:
        return raw
    shortened = raw[: max_len - 1].rsplit(" ", 1)[0].strip()
    if len(shortened) < max_len // 2:
        shortened = raw[: max_len - 1].strip()
    return f"{shortened.rstrip(' /,-')}\u2026"


def _truncate_with_dots(value: Any, *, max_len: int = 70) -> str:
    raw = " ".join(str(value or "").split()).strip()
    if len(raw) <= max_len:
        return raw
    shortened = raw[: max_len - 3].rsplit(" ", 1)[0].strip()
    if len(shortened) < max_len // 2:
        shortened = raw[: max_len - 3].strip()
    return f"{shortened.rstrip(' /,-')}..."


def _looks_like_surname(token: str) -> bool:
    probe = str(token or "").strip().casefold()
    return any(probe.endswith(suffix) for suffix in SURNAME_SUFFIXES)


def _display_person_name(value: Any) -> str:
    raw = " ".join(str(value or "").split()).strip()
    if not raw or raw == "без ответственного" or raw.startswith("ID "):
        return raw or "без ответственного"
    parts = raw.split()
    if len(parts) == 1:
        return parts[0]
    if len(parts) >= 3:
        first, second = parts[0], parts[1]
        if _looks_like_surname(second) and not _looks_like_surname(first):
            return f"{second} {first}"
        return f"{first} {second}"
    first, second = parts
    if _looks_like_surname(second) and not _looks_like_surname(first):
        return f"{second} {first}"
    return f"{first} {second}"


def _entity_html(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or item.get("entity_type") or "").strip().lower()
    raw_title = item.get("title") or item.get("name") or "Без названия"
    max_len = 56 if kind == "lead" else 84
    title = _safe(_short_title(raw_title, max_len=max_len))
    url = str(item.get("card_url") or "").strip()
    manager_name = _display_person_name(item.get("assigned_name") or "без ответственного")
    manager_html = f"<b>{_safe(manager_name)}</b>"
    if url:
        return f'<a href="{_safe_attr(url)}">{title}</a> — {manager_html}'
    return f"{title} — {manager_html}"


def _bullet_list(items: list[str], fallback: str) -> list[str]:
    return [f"• {item}" for item in items] if items else [f"• {_safe(fallback)}"]


def _numbered_list(items: list[str], fallback: str) -> list[str]:
    if not items:
        return [f"1. {_safe(fallback)}"]
    return [f"{idx}. {item}" for idx, item in enumerate(items[:3], start=1)]


def _append_limitations(lines: list[str], limitations: list[str]) -> list[str]:
    if not limitations:
        return lines
    filtered = [item for item in limitations if item and not _looks_like_machine_code(item)]
    visible = filtered or [item for item in limitations if item]
    if not visible:
        return lines
    lines.extend(["", _heading_html("ℹ️ Ограничения")])
    lines.extend(f"• {_safe(item)}" for item in visible[:2])
    return lines


def _looks_like_machine_code(value: Any) -> bool:
    raw = str(value or "").strip()
    return bool(raw) and raw.lower() == raw and "_" in raw and " " not in raw


def _preformatted_block(lines: list[str]) -> str:
    return "<pre>" + "\n".join(escape(str(line), quote=False) for line in lines) + "</pre>"


def _reason_block(item: dict[str, Any]) -> str:
    detail_parts = []
    if item.get("amount") not in (None, ""):
        detail_parts.append(f"сумма: {_money_html(item.get('amount'))}")
    detail_parts.append(_safe(", ".join(item.get("reasons") or []) or "нужен контроль"))
    detail = "; ".join(detail_parts)
    return f"{_entity_html(item)}\n{detail}"


def _signal_html(value: Any) -> str:
    raw = str(value or "").strip()
    if " — " not in raw:
        return _safe(raw)
    manager_name, detail = raw.split(" — ", 1)
    return f"<b>{_safe(_display_person_name(manager_name))}</b> — {_safe(detail)}"


def _source_line(item: dict[str, Any]) -> str:
    return f"{_safe(item.get('source_name') or 'Источник не указан')} — {_safe(str(item.get('count') or 0))}"


def _delta_suffix(current: int | float, previous: Any) -> str:
    if previous in (None, ""):
        return " (н/д к прошлому дню)"
    try:
        delta = float(current) - float(previous)
    except (TypeError, ValueError):
        return " (н/д к прошлому дню)"
    if abs(delta) < 1e-9:
        return " (0 к прошлому дню)"
    signed = f"+{int(delta)}" if delta > 0 else str(int(delta))
    return f" ({_safe(signed)} к прошлому дню)"


def _metric_line(
    label: str,
    count: Any,
    *,
    amount: Any = None,
    previous_count: Any = None,
) -> str:
    line = f"• {_safe(label)}: {_safe(str(int(count or 0)))}"
    if amount is not None:
        line += f" / {_money_html(amount)}"
    line += _delta_suffix(int(count or 0), previous_count)
    return line


def _report_day_label(raw_value: Any) -> str:
    if isinstance(raw_value, datetime):
        return _safe(raw_value.astimezone(MOSCOW_TZ).strftime("%d.%m"))
    raw = str(raw_value or "").strip()
    if not raw:
        return "н/д"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return _safe(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MOSCOW_TZ)
    else:
        dt = dt.astimezone(MOSCOW_TZ)
    return _safe(dt.strftime("%d.%m"))


def _product_row_name(row: dict[str, Any]) -> str:
    for key in ("PRODUCT_NAME", "product_name", "NAME", "name"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    product_id = str(row.get("PRODUCT_ID") or row.get("product_id") or "").strip()
    if product_id:
        return f"Товар {product_id}"
    return "Состав не указан"


def _product_row_amount(row: dict[str, Any]) -> float:
    for key in ("SUM", "sum", "PRICE_EXCLUSIVE", "price_exclusive", "PRICE", "price"):
        raw_value = row.get(key)
        if raw_value in (None, ""):
            continue
        try:
            value = float(str(raw_value).replace(" ", "").replace(",", "."))
        except ValueError:
            continue
        if key.lower() == "sum":
            return value
        quantity_raw = row.get("QUANTITY") or row.get("quantity") or 1
        try:
            quantity = float(str(quantity_raw).replace(" ", "").replace(",", "."))
        except ValueError:
            quantity = 1.0
        return value * quantity
    return 0.0


def _hot_stage_products_line(item: dict[str, Any]) -> str:
    rows = list(item.get("product_rows") or [])
    normalized: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(f"{_safe(_product_row_name(row))} - {_money_html(_product_row_amount(row))}")
    return ", ".join(normalized)


def _hot_stage_deal_lines(item: dict[str, Any]) -> list[str]:
    manager_name = _safe(_display_person_name(item.get("assigned_name") or "без ответственного"))
    deal_html = _deal_link(item.get("title") or item.get("name") or "Сделка", item.get("card_url"))
    primary_line = (
        f"• {deal_html} - <b>{manager_name}</b> - {_money_html(item.get('amount'))}"
    )
    products_line = _hot_stage_products_line(item)
    if products_line:
        return [primary_line, products_line]
    return [primary_line]


def _new_deal_item(item: dict[str, Any]) -> str:
    source = str(item.get("source_name") or "Источник не указан").strip()
    if item.get("source_description"):
        source_description = " ".join(str(item.get("source_description") or "").split())
        source = f"{source} ({_short_title(source_description, max_len=72)})"
    return f"{_entity_html(item)}\nсумма: {_money_html(item.get('amount'))}; источник: {_safe(source)}"


def _lost_deal_item(item: dict[str, Any]) -> str:
    reason = " ".join(str(item.get("lost_reason") or "").split()) or "причина не указана в CRM"
    reason = _short_title(reason, max_len=140)
    return f"{_entity_html(item)}\nсумма: {_money_html(item.get('amount'))}; причина: {_safe(reason)}"


def _meeting_item(item: dict[str, Any]) -> str:
    return f"{_entity_html(item)}\nпроведена: {_safe(_format_dt(item.get('moved_at')))}"


def _brief_item(item: dict[str, Any]) -> str:
    return f"{_entity_html(item)}\nпринят: {_safe(_format_dt(item.get('moved_at')))}"


def _task_item(item: dict[str, Any]) -> str:
    deal_title = _safe(_short_title(item.get("deal_title") or "Сделка"))
    deal_url = str(item.get("deal_card_url") or "").strip()
    deal_html = f'<a href="{_safe_attr(deal_url)}">{deal_title}</a>' if deal_url else deal_title
    days_overdue = int(item.get("days_overdue") or 0)
    overdue_text = "срок прошёл сегодня" if days_overdue <= 0 else f"просрочено на {days_overdue} дн."
    return (
        f"{deal_html} — <b>{_safe(_display_person_name(item.get('manager_name') or 'без ответственного'))}</b>\n"
        f"{_safe(overdue_text)}; "
        f"задача: {_safe(item.get('task_title') or '-')}; дедлайн: {_safe(_format_dt(item.get('deadline')))}"
    )


def _deal_link(title: Any, url: Any) -> str:
    deal_title = _safe(_short_title(title or "Сделка", max_len=64))
    raw_url = str(url or "").strip()
    if raw_url:
        return f'<a href="{_safe_attr(raw_url)}">{deal_title}</a>'
    return deal_title


def _overdue_manager_item(item: dict[str, Any]) -> str:
    examples: list[str] = []
    seen_keys: set[str] = set()
    for example in item.get("deals") or []:
        deal_title = str(example.get("deal_title") or "").strip()
        deal_url = str(example.get("deal_card_url") or "").strip()
        task_title = _truncate_with_dots(example.get("task_title") or "Без названия", max_len=72)
        key = f"{deal_url}|{deal_title}|{task_title}"
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        examples.append(f"{_deal_link(deal_title, deal_url)} → {_safe(task_title)}")
        if len(examples) >= 3:
            break
    count = int(item.get("count") or 0)
    max_days_overdue = int(item.get("max_days_overdue") or 0)
    overdue_text = "макс просрочка: сегодня" if max_days_overdue <= 0 else f"макс просрочка: {max_days_overdue} дн."
    lines = [
        (
            f"{_safe(_display_person_name(item.get('manager_name') or 'без ответственного'))} — "
            f"{_safe(str(count))} {_safe(_ru_noun(count, 'просрочка', 'просрочки', 'просрочек'))}"
        ),
        _safe(overdue_text),
    ]
    if examples:
        lines.append(f"примеры: {'; '.join(examples)}")
    return "\n".join(lines)


def _rop_focus_task_item(item: dict[str, Any]) -> str:
    manager_name = _safe(_display_person_name(item.get("manager_name") or "без ответственного"))
    deal_html = _deal_link(item.get("deal_title") or "Сделка", item.get("deal_card_url"))
    task_title = _safe(_truncate_with_dots(item.get("task_title") or "Без названия", max_len=70))
    move_count = int(item.get("deadline_change_count") or 0)
    move_label = _ru_noun(move_count, "перенос", "переноса", "переносов")
    return f"{manager_name} — {deal_html} → {task_title} — {_safe(str(move_count))} {_safe(move_label)}"


def _overdue_manager_lines(items: list[dict[str, Any]]) -> list[str]:
    filtered = [item for item in items if int(item.get("count") or 0) > 0]
    if not filtered:
        return [f"{_heading_html('🗂 Просрочки по менеджерам')}: нет"]
    return [
        _heading_html("🗂 Просрочки по менеджерам"),
        *_bullet_list([_overdue_manager_item(item) for item in filtered], "Просрочек по менеджерам нет."),
    ]


def _sum_amount(items: list[dict[str, Any]]) -> float:
    return sum(float(item.get("amount") or 0.0) for item in items)


def _daily_detail_lines(
    title: str,
    items: list[dict[str, Any]],
    *,
    item_builder: Any,
    empty_text: str,
    limit: int | None = 3,
) -> list[str]:
    lines = [_heading_html(title)]
    if items:
        selected_items = items if limit is None else items[:limit]
        lines.extend(_bullet_list([item_builder(item) for item in selected_items], empty_text))
    else:
        lines.append(empty_text)
    return lines


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=MOSCOW_TZ)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=MOSCOW_TZ)


def _format_ru_day_month(value: Any) -> str:
    dt = _coerce_datetime(value)
    if not isinstance(dt, datetime):
        return "-"
    dt = dt.astimezone(MOSCOW_TZ)
    return f"{dt.day} {RU_MONTHS_GENITIVE[dt.month - 1]}"


def _days_until(next_step_at: Any, *, now: datetime | None) -> int | None:
    dt = _coerce_datetime(next_step_at)
    if not isinstance(dt, datetime) or not isinstance(now, datetime):
        return None
    return (dt.astimezone(MOSCOW_TZ).date() - now.astimezone(MOSCOW_TZ).date()).days


def _postponed_deal_item(item: dict[str, Any], *, now: datetime | None) -> str:
    parts = [
        _deal_link(item.get("title") or "Сделка", item.get("card_url")),
        _money_html(item.get("amount")),
        f"<b>{_safe(_display_person_name(item.get('assigned_name') or 'без ответственного'))}</b>",
    ]
    next_step_at = item.get("next_step_at")
    days_until = _days_until(next_step_at, now=now)
    if _coerce_datetime(next_step_at) is not None:
        contact_label = f"след. контакт {_safe(_format_ru_day_month(next_step_at))}"
        if days_until is not None:
            if days_until >= 0:
                contact_label += f" (через {_safe(str(days_until))} дн.)"
            else:
                contact_label += f" (просрочен на {_safe(str(abs(days_until)))} дн.)"
        parts.append(contact_label)
    else:
        parts.append("без даты следующего контакта")
    return " — ".join(parts)


def _no_next_step_item(item: dict[str, Any]) -> str:
    details = [f"сумма: {_money_html(item.get('amount'))}"]
    if item.get("stage_name"):
        details.append(f"стадия: {_safe(item.get('stage_name'))}")
    if item.get("inactive_days") is not None:
        details.append(f"без движения: {_safe(str(item.get('inactive_days')))} дн.")
    return f"{_entity_html(item)}\n{'; '.join(details)}"


def _daily_no_next_step_item(item: dict[str, Any]) -> str:
    return (
        f"{_entity_html(item)}\n"
        f"сумма: {_money_html(item.get('amount'))}; стадия: {_safe(item.get('stage_name') or '-')}; "
        "следующего шага нет"
    )


def _stale_deal_item(item: dict[str, Any]) -> str:
    return (
        f"{_entity_html(item)}\n"
        f"сумма: {_money_html(item.get('amount'))}; стадия: {_safe(item.get('stage_name') or '-')}; "
        f"без коммуникации: {_safe(str(item.get('communication_gap_days') or 0))} дн."
    )


def _stagnant_deal_item(item: dict[str, Any]) -> str:
    return (
        f"{_entity_html(item)}\n"
        f"сумма: {_money_html(item.get('amount'))}; стадия: {_safe(item.get('stage_name') or '-')}; "
        f"без движения: {_safe(str(item.get('inactive_days') or 0))} дн."
    )


def _sorted_stagnant_deals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            int(item.get("inactive_days") or 0),
            float(item.get("amount") or 0.0),
        ),
        reverse=True,
    )


def _sorted_stale_deals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            int(item.get("communication_gap_days") or 0),
            float(item.get("amount") or 0.0),
        ),
        reverse=True,
    )


def _sorted_no_next_step_deals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            float(item.get("amount") or 0.0),
            int(bool(item.get("late_stage"))),
            float(item.get("effective_probability") or 0.0),
            int(item.get("inactive_days") or 0),
        ),
        reverse=True,
    )


def _overdue_risk_deals(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    active_deals_by_id = {
        str(item.get("id") or "").strip(): item
        for item in (analysis.get("active_deals") or [])
        if str(item.get("id") or "").strip()
    }
    overdue_by_deal: dict[str, dict[str, Any]] = {}
    for task in analysis.get("overdue_deal_tasks") or []:
        deal_id = str(task.get("deal_id") or "").strip()
        if not deal_id or deal_id not in active_deals_by_id:
            continue
        deal = active_deals_by_id[deal_id]
        item = overdue_by_deal.setdefault(
            deal_id,
            {
                **deal,
                "days_overdue": 0,
                "task_title": "",
            },
        )
        task_days_overdue = int(task.get("days_overdue") or 0)
        if task_days_overdue >= int(item.get("days_overdue") or 0):
            item["days_overdue"] = task_days_overdue
            item["task_title"] = str(task.get("task_title") or "").strip()
    return sorted(
        overdue_by_deal.values(),
        key=lambda item: (
            int(item.get("days_overdue") or 0),
            float(item.get("amount") or 0.0),
        ),
        reverse=True,
    )


def _overdue_deal_item(item: dict[str, Any]) -> str:
    details = [
        f"сумма: {_money_html(item.get('amount'))}",
        f"стадия: {_safe(item.get('stage_name') or '-')}",
        f"просрочка: {_safe(str(item.get('days_overdue') or 0))} дн.",
    ]
    task_title = str(item.get("task_title") or "").strip()
    if task_title:
        details.append(f"задача: {_safe(_truncate_with_dots(task_title, max_len=70))}")
    return f"{_entity_html(item)}\n" + "; ".join(details)


def _risk_category_block(
    title: str,
    items: list[dict[str, Any]],
    *,
    item_builder: Any,
    empty_text: str,
) -> list[str]:
    lines = [_heading_html(title)]
    if items:
        lines.extend(
            [
                f"Всего: {_safe(str(len(items)))} / {_money_html(_sum_amount(items))}",
                *_bullet_list([item_builder(item) for item in items], empty_text),
            ]
        )
    else:
        lines.append(empty_text)
    return lines


def _format_share(part: int, total: int) -> str:
    if total <= 0:
        return "0%"
    share = round((float(part) / float(total)) * 100.0, 1)
    if float(share).is_integer():
        return f"{int(share)}%"
    return f"{share:.1f}%"


def _ru_noun(count: int, one: str, few: str, many: str) -> str:
    value = abs(int(count)) % 100
    if 11 <= value <= 14:
        return many
    tail = value % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def _rop_deal_reason(item: dict[str, Any], risk_item: dict[str, Any] | None) -> str:
    communication_gap = int(item.get("communication_gap_days") or 0)
    inactive_days = int(item.get("inactive_days") or 0)
    if communication_gap > 0:
        return f"{communication_gap} дн без коммуникации"
    if item.get("missing_next_step"):
        return "нет следующего шага"
    if item.get("late_stage") and inactive_days > 0:
        return f"{inactive_days} дн без движения"
    if item.get("late_stage"):
        return "поздняя стадия"
    if item.get("large_deal"):
        return "крупная сумма"
    if risk_item and risk_item.get("reasons"):
        return str((risk_item.get("reasons") or ["нужен контроль"])[0] or "нужен контроль").strip()
    if item.get("needs_leader"):
        return "нужен контроль РОПа"
    return "сделка требует внимания"


def _rop_deal_priority(item: dict[str, Any], risk_item: dict[str, Any] | None) -> tuple[float, int, int, int, int, int]:
    return (
        float(item.get("amount") or 0.0),
        int(bool(item.get("late_stage"))),
        int(item.get("communication_gap_days") or 0),
        int(bool(item.get("missing_next_step"))),
        int((risk_item or {}).get("severity") or 0),
        int(bool(item.get("needs_leader"))),
    )


def _manager_html(value: Any) -> str:
    return f"<b>{_safe(_display_person_name(value or 'без ответственного'))}</b>"


def _manager_identity_key(manager_id: Any, manager_name: Any) -> str:
    raw_id = str(manager_id or "").strip()
    if raw_id:
        return f"id:{raw_id}"
    parts = sorted(part.casefold() for part in str(manager_name or "").split() if part.strip())
    return "name:" + "|".join(parts) if parts else "name:без-ответственного"


def _focus_deal_link(item: dict[str, Any]) -> str:
    return _deal_link(
        item.get("title") or item.get("deal_title") or "Сделка",
        item.get("card_url") or item.get("deal_card_url"),
    )


def _format_score_out_of_10(value: Any) -> str:
    try:
        score = round(float(value or 0.0), 1)
    except (TypeError, ValueError):
        score = 0.0
    if float(score).is_integer():
        return str(int(score))
    return f"{score:.1f}"


def _role_marker(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "telemarketing":
        return "TM"
    return "SM"


def _focus_text_tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-zA-Zа-яА-Я0-9]+", str(value or "").casefold())
        if len(token) >= 4
    }


def _focus_item_matches_deal(deal: dict[str, Any], item: dict[str, Any]) -> bool:
    item_title = str(item.get("title") or "").strip()
    if not item_title:
        return False
    item_title_lc = item_title.casefold()

    for probe in (deal.get("title"), deal.get("relation_suffix")):
        probe_text = str(probe or "").strip()
        if not probe_text:
            continue
        probe_lc = probe_text.casefold()
        if probe_lc in item_title_lc or item_title_lc in probe_lc:
            return True

    deal_tokens = _focus_text_tokens(deal.get("title")) | _focus_text_tokens(deal.get("relation_suffix"))
    item_tokens = _focus_text_tokens(item_title)
    return bool(deal_tokens and item_tokens and deal_tokens.intersection(item_tokens))


def _focus_stage_has_marker(stage_name: Any, markers: tuple[str, ...]) -> bool:
    lowered = str(stage_name or "").casefold()
    return any(marker in lowered for marker in markers)


def _focus_meeting_kind(item: dict[str, Any]) -> str:
    lowered = " ".join(
        part
        for part in (
            str(item.get("title") or "").strip(),
            str(item.get("stage_name") or "").strip(),
        )
        if part
    ).casefold()
    if not lowered:
        return ""
    if any(marker in lowered for marker in ("бриф", "брифинг")):
        return "brief"
    if any(marker in lowered for marker in ("защит", "кп", "коммер", "proposal", "презент", "предлож")):
        return "proposal"
    return ""


def _focus_latest_event_at(items: list[dict[str, Any]]) -> datetime | None:
    timestamps = [item.get("moved_at") for item in items if isinstance(item.get("moved_at"), datetime)]
    return max(timestamps) if timestamps else None


def _build_focus_opportunity_candidates(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    now = analysis.get("now")
    if not isinstance(now, datetime):
        now = datetime.now(MOSCOW_TZ)

    meetings = list(analysis.get("conducted_meetings") or [])
    accepted_briefs = list(analysis.get("accepted_briefs") or [])
    candidates: list[dict[str, Any]] = []

    for deal in analysis.get("active_deals") or []:
        related_meetings = [item for item in meetings if _focus_item_matches_deal(deal, item)]
        related_brief_meetings = [item for item in related_meetings if _focus_meeting_kind(item) == "brief"]
        related_proposal_meetings = [item for item in related_meetings if _focus_meeting_kind(item) == "proposal"]
        related_briefs = [item for item in accepted_briefs if _focus_item_matches_deal(deal, item)]
        brief_events = [*related_brief_meetings, *related_briefs]
        latest_brief_at = _focus_latest_event_at(brief_events)
        proposal_after_brief = [
            item
            for item in related_proposal_meetings
            if isinstance(item.get("moved_at"), datetime)
            and (latest_brief_at is None or item.get("moved_at") >= latest_brief_at)
        ]

        stage_name = str(deal.get("stage_name") or "").strip()
        is_brief_stage = _focus_stage_has_marker(stage_name, ("бриф",))
        is_kp_stage = _focus_stage_has_marker(stage_name, ("кп", "коммер", "proposal", "предлож"))
        idle_days = max(int(deal.get("inactive_days") or 0), int(deal.get("communication_gap_days") or 0))
        amount = float(deal.get("amount") or 0.0)

        what_failed = ""
        why_missed = ""
        score = amount / 1000.0

        if latest_brief_at is not None:
            days_since_brief = max(int((now - latest_brief_at).total_seconds() // 86400), 0)
        else:
            days_since_brief = 0

        if latest_brief_at is not None and days_since_brief >= 7 and not proposal_after_brief:
            what_failed = f"после брифа прошло {days_since_brief} дн., а встречи по защите КП нет"
            why_missed = "обязательный переход к защите КП сорван, деньги зависли между этапами продажи"
            score += 160 + (days_since_brief * 8)
        elif is_brief_stage and not related_meetings:
            what_failed = f"сделка стоит на этапе «{stage_name or 'Бриф'}», но в истории нет ни одной встречи"
            why_missed = "обязательный первый шаг продажи не зафиксирован, сделка идёт вслепую"
            score += 130 + (idle_days * 6)
        elif (latest_brief_at is not None or is_kp_stage) and not related_proposal_meetings and idle_days >= 7:
            if latest_brief_at is not None:
                what_failed = f"после брифа нет перехода к защите КП уже {idle_days} дн."
            else:
                what_failed = (
                    f"сделка зависла на этапе «{stage_name or 'Подготовка КП'}», а встреча по защите КП не зафиксирована"
                )
            why_missed = "клиента не довели до обязательного шага продажи, поэтому шанс на деньги уходит"
            score += 120 + (idle_days * 7)

        if not what_failed:
            continue

        candidates.append(
            {
                "deal_id": str(deal.get("id") or "").strip(),
                "title": deal.get("title") or "Сделка",
                "card_url": deal.get("card_url"),
                "what_failed": what_failed,
                "why_missed": why_missed,
                "score": score,
            }
        )

    return sorted(candidates, key=lambda item: float(item.get("score") or 0.0), reverse=True)[:3]


def _prepare_focus_manager_rows(
    communications_summary: dict[str, Any],
    analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    managers = list(communications_summary.get("manager_stats") or communications_summary.get("managers") or [])
    if not managers:
        return []

    meeting_counts = _meeting_counts_by_manager(analysis)
    telemarketing_min_dials = int(
        (communications_summary.get("thresholds") or {}).get("telemarketing_min_dials") or DEFAULT_TELEMARKETING_MIN_DIALS
    )

    prepared_rows: list[dict[str, Any]] = []
    for item in managers:
        manager_key = _manager_identity_key(item.get("manager_id"), item.get("manager_name"))
        scorecard = _communications_scorecard(
            item,
            meetings_count=meeting_counts.get(manager_key, 0),
            telemarketing_min_dials=telemarketing_min_dials,
        )
        prepared_rows.append({**item, "_scorecard": scorecard})
    return prepared_rows


def _build_focus_manager_stats(
    analysis: dict[str, Any],
    prepared_manager_rows: list[dict[str, Any]],
    *,
    stale_days_limit: int,
) -> list[dict[str, Any]]:
    stats_by_name: dict[str, dict[str, Any]] = {}
    for item in prepared_manager_rows:
        manager_name = _display_person_name(item.get("manager_name") or "без ответственного")
        manager_key = _manager_identity_key(item.get("manager_id"), manager_name)
        stats_by_name[manager_key] = {
            **item,
            "manager_name": manager_name,
            "manager_key": manager_key,
            "missing_next_step_count": 0,
            "late_missing_next_step_count": 0,
            "stale_communication_count": 0,
            "stale_late_stage_count": 0,
            "late_stage_stuck_count": 0,
            "overdue_tasks_count": 0,
            "max_days_overdue": 0,
            "reschedule_deals_count": 0,
            "max_reschedule_count": 0,
            "issue_amount": 0.0,
            "top_stale_deal": None,
            "top_overdue_deal": None,
        }

    for deal in analysis.get("active_deals") or []:
        manager_name = _display_person_name(deal.get("assigned_name") or "без ответственного")
        manager_key = _manager_identity_key(deal.get("assigned_id"), manager_name)
        row = stats_by_name.setdefault(
            manager_key,
            {
                "manager_name": manager_name,
                "manager_key": manager_key,
                "employee_role": "sales",
                "missing_next_step_count": 0,
                "late_missing_next_step_count": 0,
                "stale_communication_count": 0,
                "stale_late_stage_count": 0,
                "late_stage_stuck_count": 0,
                "overdue_tasks_count": 0,
                "max_days_overdue": 0,
                "reschedule_deals_count": 0,
                "max_reschedule_count": 0,
                "issue_amount": 0.0,
                "top_stale_deal": None,
                "top_overdue_deal": None,
                "_scorecard": {},
            },
        )
        row["manager_name"] = manager_name

        has_issue = False
        if deal.get("missing_next_step"):
            row["missing_next_step_count"] = int(row.get("missing_next_step_count") or 0) + 1
            if deal.get("late_stage"):
                row["late_missing_next_step_count"] = int(row.get("late_missing_next_step_count") or 0) + 1
            has_issue = True

        communication_gap_days = int(deal.get("communication_gap_days") or 0)
        if communication_gap_days >= stale_days_limit:
            row["stale_communication_count"] = int(row.get("stale_communication_count") or 0) + 1
            if deal.get("late_stage"):
                row["stale_late_stage_count"] = int(row.get("stale_late_stage_count") or 0) + 1
            current_top = row.get("top_stale_deal")
            if current_top is None or float(deal.get("amount") or 0.0) > float(current_top.get("amount") or 0.0):
                row["top_stale_deal"] = deal
            has_issue = True

        if bool(deal.get("late_stage")) and int(deal.get("inactive_days") or 0) >= 5:
            row["late_stage_stuck_count"] = int(row.get("late_stage_stuck_count") or 0) + 1
            has_issue = True

        if has_issue:
            row["issue_amount"] = float(row.get("issue_amount") or 0.0) + float(deal.get("amount") or 0.0)

    for item in analysis.get("overdue_deal_tasks_by_manager") or []:
        manager_name = _display_person_name(item.get("manager_name") or "без ответственного")
        manager_key = _manager_identity_key(item.get("manager_id"), manager_name)
        row = stats_by_name.setdefault(
            manager_key,
            {
                "manager_name": manager_name,
                "manager_key": manager_key,
                "employee_role": "sales",
                "missing_next_step_count": 0,
                "late_missing_next_step_count": 0,
                "stale_communication_count": 0,
                "stale_late_stage_count": 0,
                "late_stage_stuck_count": 0,
                "overdue_tasks_count": 0,
                "max_days_overdue": 0,
                "reschedule_deals_count": 0,
                "max_reschedule_count": 0,
                "issue_amount": 0.0,
                "top_stale_deal": None,
                "top_overdue_deal": None,
                "_scorecard": {},
            },
        )
        if not str(row.get("manager_name") or "").strip() or str(row.get("manager_name")).strip() == "без ответственного":
            row["manager_name"] = manager_name
        row["overdue_tasks_count"] = max(int(row.get("overdue_tasks_count") or 0), int(item.get("count") or 0))
        row["max_days_overdue"] = max(int(row.get("max_days_overdue") or 0), int(item.get("max_days_overdue") or 0))
        deals = list(item.get("deals") or [])
        if deals:
            row["top_overdue_deal"] = sorted(
                deals,
                key=lambda deal_item: int(deal_item.get("days_overdue") or 0),
                reverse=True,
            )[0]

    seen_reschedules: set[tuple[str, str]] = set()
    for item in analysis.get("deadline_reschedule_focus_tasks") or []:
        manager_name = _display_person_name(item.get("manager_name") or "без ответственного")
        manager_key = _manager_identity_key(item.get("manager_id"), manager_name)
        deal_id = str(item.get("deal_id") or "").strip()
        row = stats_by_name.setdefault(
            manager_key,
            {
                "manager_name": manager_name,
                "manager_key": manager_key,
                "employee_role": "sales",
                "missing_next_step_count": 0,
                "late_missing_next_step_count": 0,
                "stale_communication_count": 0,
                "stale_late_stage_count": 0,
                "late_stage_stuck_count": 0,
                "overdue_tasks_count": 0,
                "max_days_overdue": 0,
                "reschedule_deals_count": 0,
                "max_reschedule_count": 0,
                "issue_amount": 0.0,
                "top_stale_deal": None,
                "top_overdue_deal": None,
                "_scorecard": {},
            },
        )
        if not str(row.get("manager_name") or "").strip() or str(row.get("manager_name")).strip() == "без ответственного":
            row["manager_name"] = manager_name
        if deal_id and (manager_key, deal_id) not in seen_reschedules:
            row["reschedule_deals_count"] = int(row.get("reschedule_deals_count") or 0) + 1
            seen_reschedules.add((manager_key, deal_id))
        row["max_reschedule_count"] = max(
            int(row.get("max_reschedule_count") or 0),
            int(item.get("deadline_change_count") or 0),
        )

    return list(stats_by_name.values())


def _focus_manager_priority(item: dict[str, Any]) -> float:
    return (
        (int(item.get("overdue_tasks_count") or 0) * 9)
        + (int(item.get("reschedule_deals_count") or 0) * 8)
        + (int(item.get("late_stage_stuck_count") or 0) * 7)
        + (int(item.get("missing_next_step_count") or 0) * 6)
        + (int(item.get("stale_communication_count") or 0) * 5)
        + int(item.get("max_days_overdue") or 0)
        + float(item.get("issue_amount") or 0.0) / 100000.0
    )


def _focus_control_signal(item: dict[str, Any], *, stale_days_limit: int) -> str:
    manager_name = _manager_html(item.get("manager_name") or "без ответственного")
    missing_next_step_count = int(item.get("missing_next_step_count") or 0)
    late_missing_next_step_count = int(item.get("late_missing_next_step_count") or 0)
    stale_communication_count = int(item.get("stale_communication_count") or 0)
    stale_late_stage_count = int(item.get("stale_late_stage_count") or 0)
    overdue_tasks_count = int(item.get("overdue_tasks_count") or 0)
    late_stage_stuck_count = int(item.get("late_stage_stuck_count") or 0)

    if missing_next_step_count > 0:
        line = (
            f"У {manager_name} {missing_next_step_count} "
            f"{_safe(_ru_noun(missing_next_step_count, 'сделка', 'сделки', 'сделок'))} без следующего шага"
        )
        if late_missing_next_step_count > 0:
            line += (
                f", из них {late_missing_next_step_count} "
                f"{_safe(_ru_noun(late_missing_next_step_count, 'сделка', 'сделки', 'сделок'))} на поздней стадии"
            )
        return f"{line}."

    if stale_communication_count > 0:
        line = (
            f"У {manager_name} {stale_communication_count} "
            f"{_safe(_ru_noun(stale_communication_count, 'сделка', 'сделки', 'сделок'))} "
            f"без коммуникации более {_safe(str(stale_days_limit))} дней"
        )
        if stale_late_stage_count == 1:
            line += ", одна уже на поздней стадии"
        elif stale_late_stage_count > 1:
            line += f", из них {stale_late_stage_count} на поздней стадии"
        return f"{line}."

    if overdue_tasks_count > 0 and late_stage_stuck_count > 0:
        return (
            f"У {manager_name} {overdue_tasks_count} "
            f"{_safe(_ru_noun(overdue_tasks_count, 'просроченная задача', 'просроченные задачи', 'просроченных задач'))} "
            f"и {late_stage_stuck_count} "
            f"{_safe(_ru_noun(late_stage_stuck_count, 'поздняя сделка', 'поздние сделки', 'поздних сделок'))} без движения."
        )

    if late_stage_stuck_count > 0:
        return (
            f"У {manager_name} {late_stage_stuck_count} "
            f"{_safe(_ru_noun(late_stage_stuck_count, 'поздняя сделка', 'поздние сделки', 'поздних сделок'))} без движения."
        )

    if overdue_tasks_count > 0:
        return (
            f"У {manager_name} {overdue_tasks_count} "
            f"{_safe(_ru_noun(overdue_tasks_count, 'просроченная задача', 'просроченные задачи', 'просроченных задач'))} "
            "по активным сделкам."
        )

    return ""


def _focus_manager_push_action(item: dict[str, Any]) -> str:
    manager_name = _manager_html(item.get("manager_name") or "без ответственного")
    scorecard = item.get("_scorecard") or {}
    operational_score = _format_score_out_of_10(scorecard.get("operational_score"))
    status_code = str(scorecard.get("status_code") or "").strip()
    dials = int(item.get("dials") or 0)
    normal_calls = int(item.get("normal_calls") or 0)
    messenger_dialogs = int(item.get("messenger_dialogs") or 0)
    meetings_count = int(scorecard.get("meetings_count") or 0)
    missing_next_step_count = int(item.get("missing_next_step_count") or 0)
    late_missing_next_step_count = int(item.get("late_missing_next_step_count") or 0)
    stale_communication_count = int(item.get("stale_communication_count") or 0)
    overdue_tasks_count = int(item.get("overdue_tasks_count") or 0)
    late_stage_stuck_count = int(item.get("late_stage_stuck_count") or 0)
    reschedule_deals_count = int(item.get("reschedule_deals_count") or 0)
    top_overdue_deal = item.get("top_overdue_deal") or {}

    issue_bits: list[str] = []
    if status_code in {"⚠️", "❌", "РИСК", "СТОП"} or float(scorecard.get("operational_score") or 0.0) < 6.0:
        issue_bits.append(
            f"низкая операционная вовлечённость {operational_score}/10"
        )
        activity_bits = [
            f"{dials} наб.",
            f"{normal_calls} дозв.",
            f"{messenger_dialogs} чатов",
        ]
        if meetings_count > 0:
            activity_bits.append(f"{meetings_count} встреч")
        issue_bits.append(", ".join(activity_bits))
    if missing_next_step_count > 0:
        issue_bits.append(
            f"{missing_next_step_count} "
            f"{_safe(_ru_noun(missing_next_step_count, 'сделка', 'сделки', 'сделок'))} без следующего шага"
        )
        if late_missing_next_step_count > 0:
            issue_bits.append(
                f"{late_missing_next_step_count} на поздней стадии"
            )
    if stale_communication_count > 0:
        issue_bits.append(
            f"{stale_communication_count} "
            f"{_safe(_ru_noun(stale_communication_count, 'сделка', 'сделки', 'сделок'))} без коммуникации"
        )
    if overdue_tasks_count > 0:
        issue_bits.append(
            f"{overdue_tasks_count} "
            f"{_safe(_ru_noun(overdue_tasks_count, 'просроченная задача', 'просроченные задачи', 'просроченных задач'))}"
        )
    if late_stage_stuck_count > 0:
        issue_bits.append(
            f"{late_stage_stuck_count} "
            f"{_safe(_ru_noun(late_stage_stuck_count, 'поздняя сделка', 'поздние сделки', 'поздних сделок'))} без движения"
        )
    if reschedule_deals_count > 0:
        issue_bits.append(
            f"{reschedule_deals_count} "
            f"{_safe(_ru_noun(reschedule_deals_count, 'сделка', 'сделки', 'сделок'))} с повторными переносами"
        )

    if issue_bits:
        return f"Дать в чате обновление по {manager_name}: " + "; ".join(issue_bits[:4]) + "."

    return ""


def _focus_money_action(item: dict[str, Any], *, stale_days_limit: int) -> str:
    if item.get("missing_next_step"):
        return "зафиксировать следующий шаг и дату"
    if int(item.get("overdue_days") or 0) > 0 and item.get("late_stage"):
        return "закрыть просрочку и подтвердить решение клиента"
    if int(item.get("communication_gap_days") or 0) >= stale_days_limit:
        return "вернуть в контакт и подтвердить реальный статус"
    if item.get("late_stage"):
        return "дожать решение клиента и дату оплаты"
    if int(item.get("overdue_days") or 0) > 0:
        return "снять просрочку и зафиксировать новый срок"
    return "обновить статус и зафиксировать ближайший шаг"


def _focus_false_progress_reason(item: dict[str, Any], *, stale_days_limit: int) -> str:
    reschedule_count = int(item.get("reschedule_count") or 0)
    overdue_days = int(item.get("overdue_days") or 0)
    communication_gap_days = int(item.get("communication_gap_days") or 0)
    inactive_days = int(item.get("inactive_days") or 0)

    if reschedule_count >= 3 and overdue_days > 0:
        return (
            f"срок задачи переносился {reschedule_count} "
            f"{_safe(_ru_noun(reschedule_count, 'раз', 'раза', 'раз'))}, просрочка уже {overdue_days} дн."
        )
    if reschedule_count >= 3:
        return (
            f"срок задачи переносился {reschedule_count} "
            f"{_safe(_ru_noun(reschedule_count, 'раз', 'раза', 'раз'))}, решения нет"
        )
    if communication_gap_days >= stale_days_limit:
        if item.get("late_stage"):
            return f"поздняя стадия, но {communication_gap_days} дн. без коммуникации"
        return f"активная стадия, но {communication_gap_days} дн. без коммуникации"
    return f"формально в работе, но {inactive_days} дн. без движения"


def _focus_priority_reason(item: dict[str, Any], *, stale_days_limit: int) -> str:
    communication_gap_days = int(item.get("communication_gap_days") or 0)
    overdue_days = int(item.get("overdue_days") or 0)
    inactive_days = int(item.get("inactive_days") or 0)
    if item.get("late_stage") and communication_gap_days >= stale_days_limit:
        return f"поздняя стадия и {communication_gap_days} дн. тишины: потеря уже рядом"
    if item.get("late_stage") and overdue_days > 0:
        return f"поздняя стадия и просрочка {overdue_days} дн.: нельзя выпускать из рук"
    if item.get("high_probability"):
        return f"деньги близко, но {inactive_days} дн. без движения"
    if item.get("needs_leader"):
        return "крупная сумма под риском: нельзя оставлять без контроля"
    return "сделка уже искажает прогноз и требует решения сегодня"


def _focus_personal_entry_reason(item: dict[str, Any], *, stale_days_limit: int) -> str:
    parts: list[str] = []
    communication_gap_days = int(item.get("communication_gap_days") or 0)
    if communication_gap_days >= stale_days_limit:
        parts.append(f"{communication_gap_days} дн. без контакта")
    if float(item.get("amount") or 0.0) >= 150000.0:
        parts.append("сумма значимая")
    if item.get("missing_next_step"):
        parts.append("нет зафиксированного следующего шага")
    overdue_days = int(item.get("overdue_days") or 0)
    if overdue_days > 0:
        parts.append(f"есть просрочка {overdue_days} дн.")
    reschedule_count = int(item.get("reschedule_count") or 0)
    if reschedule_count >= 3:
        parts.append("сроки переносились неоднократно")
    elif item.get("needs_leader"):
        parts.append("менеджер не довёл сделку до управляемого статуса")
    if item.get("late_stage") and not parts:
        parts.append("сделка застряла в чувствительной точке воронки")
    if int(item.get("risk_severity") or 0) >= 4:
        parts.append("риск потери уже высокий")
    prefix = ", ".join(dict.fromkeys(parts)) if parts else "сделка потеряла управляемый темп"
    return f"{prefix} — нужен личный контакт РОПа"


def _build_rop_focus_lines(
    analysis: dict[str, Any],
    risk_report: dict[str, Any],
    communications_summary: dict[str, Any] | None = None,
) -> list[str]:
    communications_summary = communications_summary or {}
    stale_days_limit = 14
    thresholds = communications_summary.get("thresholds") or {}
    if thresholds:
        stale_days_limit = int(thresholds.get("stale_communication_days") or stale_days_limit)
    prepared_manager_rows = _prepare_focus_manager_rows(communications_summary, analysis)
    manager_focus_rows = _build_focus_manager_stats(
        analysis,
        prepared_manager_rows,
        stale_days_limit=stale_days_limit,
    )
    manager_focus_rows = sorted(manager_focus_rows, key=_focus_manager_priority, reverse=True)

    risk_by_deal_id = {
        str(item.get("entity_id") or "").strip(): item
        for item in (risk_report.get("deal_risks") or [])
        if str(item.get("entity_id") or "").strip()
    }
    overdue_by_deal_id: dict[str, int] = {}
    for item in analysis.get("overdue_deal_tasks") or []:
        deal_id = str(item.get("deal_id") or "").strip()
        if not deal_id:
            continue
        overdue_by_deal_id[deal_id] = max(overdue_by_deal_id.get(deal_id, 0), int(item.get("days_overdue") or 0))

    reschedule_by_deal_id: dict[str, int] = {}
    for item in analysis.get("deadline_reschedule_focus_tasks") or []:
        deal_id = str(item.get("deal_id") or "").strip()
        if not deal_id:
            continue
        reschedule_by_deal_id[deal_id] = max(
            reschedule_by_deal_id.get(deal_id, 0),
            int(item.get("deadline_change_count") or 0),
        )

    enriched_deals: list[dict[str, Any]] = []
    for deal in analysis.get("active_deals") or []:
        deal_id = str(deal.get("id") or "").strip()
        risk_item = risk_by_deal_id.get(deal_id) or {}
        enriched_deals.append(
            {
                **deal,
                "risk_severity": int(risk_item.get("severity") or 0),
                "risk_item": risk_item,
                "overdue_days": int(overdue_by_deal_id.get(deal_id) or 0),
                "reschedule_count": int(reschedule_by_deal_id.get(deal_id) or 0),
            }
        )

    control_lines: list[str] = []
    for item in manager_focus_rows:
        signal = _focus_control_signal(item, stale_days_limit=stale_days_limit)
        if signal:
            control_lines.append(signal)
        if len(control_lines) >= 3:
            break

    repeated_deals_count = len(
        {
            str(item.get("deal_id") or "").strip()
            for item in (analysis.get("deadline_reschedule_focus_tasks") or [])
            if str(item.get("deal_id") or "").strip()
        }
    )
    if repeated_deals_count > 0:
        control_lines.append(
            f"По {repeated_deals_count} "
            f"{_safe(_ru_noun(repeated_deals_count, 'сделке', 'сделкам', 'сделкам'))} сроки задач переносились 3 и более раз — "
            "это уже не разовый сбой, а затянутая потеря контроля."
        )
    control_lines = control_lines[:4] or ["Критичных управленческих отклонений на сегодня нет."]

    def _money_score(item: dict[str, Any]) -> float:
        communication_gap_days = int(item.get("communication_gap_days") or 0)
        inactive_days = int(item.get("inactive_days") or 0)
        score = float(item.get("amount") or 0.0) / 1000.0
        score += float(item.get("effective_probability") or item.get("probability") or 0.0) * 2.0
        if item.get("high_probability"):
            score += 180
        if item.get("late_stage"):
            score += 140
        if item.get("missing_next_step"):
            score += 90
        if int(item.get("overdue_days") or 0) > 0:
            score += 70
        if 0 < communication_gap_days <= stale_days_limit * 2:
            score += 50
        score -= max(communication_gap_days - (stale_days_limit * 2), 0) * 5
        score -= max(inactive_days - 20, 0) * 3
        score -= int(item.get("reschedule_count") or 0) * 20
        return score

    money_candidates = [
        item
        for item in enriched_deals
        if float(item.get("amount") or 0.0) > 0
        and (
            item.get("high_probability")
            or item.get("late_stage")
            or item.get("missing_next_step")
            or int(item.get("overdue_days") or 0) > 0
            or int(item.get("communication_gap_days") or 0) > 0
        )
        and not (
            int(item.get("communication_gap_days") or 0) > stale_days_limit * 3
            and int(item.get("reschedule_count") or 0) >= 3
        )
    ]
    money_today = sorted(money_candidates, key=_money_score, reverse=True)[:3]
    money_lines = [
        f"{_focus_deal_link(item)} — {_money_html(item.get('amount'))} — {_safe(_focus_money_action(item, stale_days_limit=stale_days_limit))}."
        for item in money_today
    ]

    opportunity_candidates = _build_focus_opportunity_candidates(analysis)
    opportunity_lines = [
        f"{_deal_link(item.get('title') or 'Сделка', item.get('card_url'))} — "
        f"{_safe(item.get('what_failed') or 'обязательный шаг не выполнен')} — "
        f"{_safe(item.get('why_missed') or 'деньги зависают в процессе продажи')}."
        for item in opportunity_candidates
    ]

    push_lines: list[str] = []
    push_manager_names: list[str] = []
    used_managers: set[str] = set()
    for item in manager_focus_rows:
        manager_name = _display_person_name(item.get("manager_name") or "")
        if not manager_name or manager_name in used_managers:
            continue
        action = _focus_manager_push_action(item)
        if not action:
            continue
        push_lines.append(action)
        push_manager_names.append(manager_name)
        used_managers.add(manager_name)
        if len(push_lines) >= 3:
            break
    def _personal_entry_score(item: dict[str, Any]) -> float:
        return (
            (1000 if item.get("needs_leader") else 0)
            + float(item.get("amount") or 0.0) / 1000.0
            + (200 if item.get("late_stage") else 0)
            + (int(item.get("risk_severity") or 0) * 60)
            + (int(item.get("communication_gap_days") or 0) * 3)
            + (int(item.get("overdue_days") or 0) * 4)
            + (int(item.get("reschedule_count") or 0) * 40)
        )

    personal_entry_candidates = [
        item
        for item in enriched_deals
        if item.get("needs_leader")
        or (
            item.get("late_stage")
            and int(item.get("communication_gap_days") or 0) >= stale_days_limit
            and float(item.get("amount") or 0.0) >= 100000.0
        )
        or (int(item.get("reschedule_count") or 0) >= 3 and int(item.get("overdue_days") or 0) > 0)
    ]
    personal_entry = sorted(personal_entry_candidates, key=_personal_entry_score, reverse=True)[:2]
    personal_entry_lines = [
        f"{_focus_deal_link(item)} — {_money_html(item.get('amount'))} — {_safe(_focus_personal_entry_reason(item, stale_days_limit=stale_days_limit))}."
        for item in personal_entry
    ]

    action_items: list[str] = []
    if push_manager_names:
        manager_names = [_manager_html(name) for name in push_manager_names[:2] if str(name).strip()]
        if manager_names:
            action_items.append(
                f"До 13:00 получить от {' и '.join(manager_names[:2])} обновлённые шаги по зависшим сделкам без очередного переноса."
            )
    if personal_entry:
        action_items.append(
            f"До конца дня лично войти в {', '.join(_focus_deal_link(item) for item in personal_entry[:2])}."
        )
    if len(action_items) < 3 and opportunity_candidates:
        opportunity_count = len(opportunity_candidates)
        action_items.append(
            f"До конца дня закрыть {opportunity_count} "
            f"{_safe(_ru_noun(opportunity_count, 'провал', 'провала', 'провалов'))} между брифом и защитой КП: либо поставить встречу, либо снять ложное ожидание."
        )
    stale_total = sum(1 for item in enriched_deals if int(item.get("communication_gap_days") or 0) >= stale_days_limit)
    if len(action_items) < 3 and stale_total > 0:
        action_items.append(
            f"До 11:00 снять реальный статус по {stale_total} "
            f"{_safe(_ru_noun(stale_total, 'сделке', 'сделкам', 'сделкам'))} с тишиной более {_safe(str(stale_days_limit))} дней и убрать из прогноза мёртвые."
        )
    if len(action_items) < 3 and repeated_deals_count > 0:
        action_items.append(
            f"Пересобрать статус по {repeated_deals_count} "
            f"{_safe(_ru_noun(repeated_deals_count, 'сделке', 'сделкам', 'сделкам'))} с повторными переносами и не давать новый срок без решения."
        )
    if len(action_items) < 3:
        action_items.append("До конца дня пересобрать контроль по зависшим поздним сделкам и подтвердить реальный статус клиента.")
    action_items = action_items[:3]

    top_people = [
        item
        for item in sorted(
            prepared_manager_rows,
            key=lambda row: float((row.get("_scorecard") or {}).get("operational_score") or 0.0),
            reverse=True,
        )
        if float((item.get("_scorecard") or {}).get("operational_score") or 0.0) >= TOP_OPERATIONAL_ENGAGEMENT_MIN
    ]
    top_people_lines = [
        f"{_manager_html(item.get('manager_name') or 'без ответственного')} — "
        f"{_safe(_format_score_out_of_10((item.get('_scorecard') or {}).get('operational_score')))}"
        "/10 👏🔥"
        for item in top_people[:5]
    ]

    lines: list[str] = []
    if personal_entry_lines:
        lines.extend(
            [
                "",
                _heading_html("☎️ Где РОПу самому связаться с клиентом:"),
                *_bullet_list(personal_entry_lines, "Сделок, где РОПу нужно самому выйти на клиента, на сегодня не выделилось."),
            ]
        )
    if opportunity_lines:
        lines.extend(
            [
                "",
                _heading_html("🕳 Упущенные возможности:"),
                *_bullet_list(opportunity_lines, "Обязательных провалов между брифом и защитой КП на сегодня не видно."),
            ]
        )
    lines.extend(
        [
            "",
            _heading_html("Что РОП обязан сделать сегодня:"),
            *_bullet_list(action_items, "Пересобрать критичные сделки и статусы по отделу."),
        ]
    )
    lines.extend(
        [
            "",
            _heading_html("🔥 Молодцы за вчера"),
        ]
    )
    if top_people_lines:
        lines.extend(
            _bullet_list(
                top_people_lines,
                f"Лидеров с {TOP_OPERATIONAL_ENGAGEMENT_MIN:.0f}+/10 по операционной вовлечённости за вчера нет.",
            )
        )
    else:
        lines.append(f"• Лидеров с {TOP_OPERATIONAL_ENGAGEMENT_MIN:.0f}+/10 по операционной вовлечённости за вчера нет.")
    return lines


def _timed_entity_block(item: dict[str, Any], *, time_label: str = "дата") -> str:
    moved_at = item.get("moved_at")
    suffix = _format_dt(moved_at) if isinstance(moved_at, datetime) else "без даты"
    return f"{_entity_html(item)}\n{_safe(time_label)}: {_safe(suffix)}"


def _meeting_counts_by_manager(analysis: dict[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in (analysis or {}).get("conducted_meetings") or []:
        if not item.get("yesterday_moved"):
            continue
        manager_key = _manager_identity_key(item.get("assigned_id"), item.get("assigned_name"))
        if not manager_key:
            continue
        counts[manager_key] = counts.get(manager_key, 0) + 1
    return counts


def _communications_scorecard(
    item: dict[str, Any],
    *,
    meetings_count: int = 0,
    telemarketing_min_dials: int = DEFAULT_TELEMARKETING_MIN_DIALS,
) -> dict[str, Any]:
    role = str(item.get("employee_role") or "").strip().lower()
    if role not in {"sales", "telemarketing"}:
        role = "sales"

    dials = int(item.get("dials") or 0)
    normal_calls = int(item.get("normal_calls") or 0)
    messenger_dialogs = int(item.get("messenger_dialogs") or 0)
    connect_rate = item.get("connect_rate")
    connect_percent = int(round(float(connect_rate) * 100)) if connect_rate is not None else 0

    effective_meetings = 0 if role == "telemarketing" else meetings_count
    meetings_label = "-" if role == "telemarketing" else str(effective_meetings)
    empty_dials = max(dials - normal_calls, 0)
    empty_dial_minutes = min(empty_dials * DEFAULT_EMPTY_DIAL_MINUTES, DEFAULT_EMPTY_DIAL_MINUTES_CAP)
    call_minutes = normal_calls * (DEFAULT_TM_CALL_MINUTES if role == "telemarketing" else DEFAULT_SM_CALL_MINUTES)
    chat_minutes = messenger_dialogs * DEFAULT_CHAT_DIALOG_MINUTES
    meeting_minutes = effective_meetings * DEFAULT_MEETING_MINUTES
    operational_minutes = empty_dial_minutes + call_minutes + chat_minutes + meeting_minutes
    operational_score = min(10.0, (operational_minutes / DEFAULT_ACTIVE_CLIENT_MINUTES_TARGET) * 10.0)

    if role == "telemarketing":
        if dials <= 0 and normal_calls <= 0 and messenger_dialogs <= 0:
            status = (0, "❌", "СТОП")
        elif operational_score >= 6.0:
            status = (2, "🔥", "НОРМ")
        elif operational_score >= 3.0:
            status = (1, "⚠️", "РИСК")
        else:
            status = (0, "❌", "СТОП")
    else:
        if dials <= 0 and normal_calls <= 0 and messenger_dialogs <= 0 and effective_meetings <= 0:
            status = (0, "❌", "СТОП")
        elif operational_score >= 6.0:
            status = (2, "🔥", "НОРМ")
        elif operational_score >= 3.0:
            status = (1, "⚠️", "РИСК")
        else:
            status = (0, "❌", "СТОП")

    return {
        "employee_role": role,
        "connect_percent": connect_percent,
        "meetings_count": effective_meetings,
        "meetings_label": meetings_label,
        "empty_dials": empty_dials,
        "empty_dial_minutes": empty_dial_minutes,
        "call_minutes": call_minutes,
        "chat_minutes": chat_minutes,
        "meeting_minutes": meeting_minutes,
        "operational_minutes": operational_minutes,
        "operational_score": operational_score,
        "operational_score_label": f"{operational_score:.1f}",
        "status_rank": status[0],
        "status_icon": status[1],
        "status_code": status[2],
    }


def _communications_items(summary: dict[str, Any], analysis: dict[str, Any] | None = None) -> list[str]:
    managers = list(summary.get("managers") or [])
    if not managers:
        return []

    def _status_meta(item: dict[str, Any]) -> tuple[int, str, str]:
        return tuple(item.get("_scorecard_status") or (2, "❌", "СТОП"))  # type: ignore[return-value]

    meeting_counts = _meeting_counts_by_manager(analysis)
    telemarketing_min_dials = int(
        (summary.get("thresholds") or {}).get("telemarketing_min_dials") or DEFAULT_TELEMARKETING_MIN_DIALS
    )

    prepared_rows: list[dict[str, Any]] = []
    for item in managers:
        manager_key = _manager_identity_key(item.get("manager_id"), item.get("manager_name"))
        scorecard = _communications_scorecard(
            item,
            meetings_count=meeting_counts.get(manager_key, 0),
            telemarketing_min_dials=telemarketing_min_dials,
        )
        prepared_rows.append({**item, "_scorecard": scorecard, "_scorecard_status": (
            scorecard["status_rank"],
            scorecard["status_icon"],
            scorecard["status_code"],
        )})

    ordered = sorted(
        prepared_rows,
        key=lambda item: (
            -_status_meta(item)[0],
            -float((item.get("_scorecard") or {}).get("operational_score") or 0.0),
            -int((item.get("_scorecard") or {}).get("meetings_count") or 0),
            -int(item.get("total_known") or 0),
            -int(item.get("dials") or 0),
            str(item.get("manager_name") or "").casefold(),
        ),
    )

    manager_rows: list[str] = []
    total_dials = 0
    total_calls = 0
    total_messenger_dialogs = 0
    total_meetings = 0
    operational_scores: list[float] = []
    telemarketing_scores: list[float] = []
    sales_scores: list[float] = []
    ordered_rows: list[dict[str, Any]] = []

    for item in ordered:
        scorecard = item.get("_scorecard") or {}
        manager_name = _truncate_with_dots(_display_person_name(item.get("manager_name") or "без ответственного"), max_len=24)
        dials = int(item.get("dials") or 0)
        normal_calls = int(item.get("normal_calls") or 0)
        messenger_dialogs = int(item.get("messenger_dialogs") or 0)
        connect_percent = int(scorecard.get("connect_percent") or 0)
        total_dials += dials
        total_calls += normal_calls
        total_messenger_dialogs += messenger_dialogs
        total_meetings += int(scorecard.get("meetings_count") or 0)
        operational_scores.append(float(scorecard.get("operational_score") or 0.0))
        if str(scorecard.get("employee_role") or "") == "telemarketing":
            telemarketing_scores.append(float(scorecard.get("operational_score") or 0.0))
        else:
            sales_scores.append(float(scorecard.get("operational_score") or 0.0))
        _, _, status_code = _status_meta(item)
        ordered_rows.append(
            {
                "status_code": status_code,
                "manager_name": manager_name,
                "role_marker": _role_marker(scorecard.get("employee_role") or item.get("employee_role")),
                "dials": dials,
                "normal_calls": normal_calls,
                "connect_percent": connect_percent,
                "messenger_dialogs": messenger_dialogs,
                "meetings_label": str(scorecard.get("meetings_label") or "0"),
                "operational_score_label": str(scorecard.get("operational_score_label") or "1.0"),
            }
        )

    manager_width = max(
        len("Менеджер"),
        max(len(str(item.get("manager_name") or "")) for item in ordered_rows) if ordered_rows else 0,
    )
    role_width = max(
        len("Роль"),
        max(len(str(item.get("role_marker") or "")) for item in ordered_rows) if ordered_rows else 0,
    )
    manager_rows.append(
        f"{'Статус':<6} {'Менеджер':<{manager_width}} {'Роль':<{role_width}} {'Наб':>4} {'Дзв':>4} {'Конв':>5} {'Чаты':>4} {'Встр':>4} {'Опер':>4}"
    )
    for item in ordered_rows:
        manager_rows.append(
            f"{str(item['status_code']):<6} "
            f"{str(item['manager_name']):<{manager_width}} "
            f"{str(item['role_marker']):<{role_width}} "
            f"{int(item['dials']):>4} "
            f"{int(item['normal_calls']):>4} "
            f"{str(item['connect_percent']) + '%':>5} "
            f"{int(item['messenger_dialogs']):>4} "
            f"{str(item['meetings_label']):>4} "
            f"{str(item['operational_score_label']):>4}"
        )

    average_percent = (float(total_calls) / float(total_dials) * 100.0) if total_dials > 0 else None
    average_operational_score = sum(operational_scores) / len(operational_scores) if operational_scores else None
    if average_percent is None:
        average_label = "0%"
        average_comment = "Данных по дозвону пока недостаточно"
    else:
        rounded_average_percent = round(average_percent, 1)
        average_label = (
            f"{int(rounded_average_percent)}%"
            if float(rounded_average_percent).is_integer()
            else f"{rounded_average_percent:.1f}%"
        )
        sales_average = sum(sales_scores) / len(sales_scores) if sales_scores else None
        telemarketing_average = sum(telemarketing_scores) / len(telemarketing_scores) if telemarketing_scores else None
        if average_operational_score is not None and average_operational_score < 4.0:
            average_comment = "Чистой клиентской активности по команде ниже целевого уровня"
        elif telemarketing_average is not None and telemarketing_average < 4.0:
            average_comment = "Телемаркетинг недобирает клиентские минуты"
        elif sales_average is not None and sales_average < 4.5:
            average_comment = "Менеджеры продаж недобирают клиентские минуты"
        else:
            average_comment = "Клиентская активность в норме"

    rows: list[str] = [
        "Статус: 🔥 НОРМ | ⚠️ РИСК | ❌ СТОП",
        _preformatted_block(manager_rows),
    ]

    rows.extend(
        [
            "",
            "Итого по отделу:",
            _preformatted_block(
                [
                    (
                        f"Наб {int(total_dials):>4} | "
                        f"Дзв {int(total_calls):>4} | "
                        f"Конв {average_label:>5} | "
                        f"Чаты {int(total_messenger_dialogs):>4} | "
                        f"Встр {int(total_meetings):>4} | "
                        f"Опер {f'{average_operational_score:.1f}' if average_operational_score is not None else '0.0':>4}"
                    )
                ]
            ),
            "",
            _safe(average_comment),
        ]
    )
    return rows


def _communications_fallback(summary: dict[str, Any]) -> list[str]:
    if summary.get("managers"):
        return []
    items: list[str] = []
    department_filter = summary.get("department_filter") or {}
    if int(department_filter.get("allowlist_count") or 0) == 0:
        items.append("Фильтр продажных подразделений не собран")
        return items
    if not (summary.get("calls") or {}).get("available"):
        items.append("Данные по звонкам недоступны")
    else:
        items.append("Коммуникаций за предыдущий рабочий день не найдено")
    if not (summary.get("messengers") or {}).get("available"):
        items.append("Диалоги в мессенджерах недоступны")
    return items


def _summary_signal_lines(
    analysis: dict[str, Any],
    risk_report: dict[str, Any],
    *,
    communications_summary: dict[str, Any] | None = None,
    monthly_target: float | None = None,
) -> list[str]:
    communications_summary = communications_summary or {}
    metrics = analysis.get("metrics") or {}
    lines: list[str] = []
    lines.append(
        "В работе "
        f"{_safe(str(metrics.get('deals_in_work', 0)))} "
        f"{_safe(_ru_noun(int(metrics.get('deals_in_work') or 0), 'сделка', 'сделки', 'сделок'))} "
        f"на {_money_html(metrics.get('pipeline_amount'))}; "
        f"подтверждённое движение есть по {_safe(str(metrics.get('moving_deals_last_week', 0)))}, "
        f"без движения по {_safe(str(metrics.get('stagnant_deals_last_week', 0)))}."
    )

    risk_totals = risk_report.get("summary_totals") or risk_report.get("totals") or {}
    stale_count = int(metrics.get("stale_communication_deals") or 0)
    stale_days_limit = int((communications_summary.get("thresholds") or {}).get("stale_communication_days") or 14)
    risk_tail = []
    if stale_count > 0:
        risk_tail.append(
            f"{_safe(str(stale_count))} "
            f"{_safe(_ru_noun(stale_count, 'сделка', 'сделки', 'сделок'))} "
            f"без коммуникации более {_safe(str(stale_days_limit))} дн."
        )
    no_next_step_count = int(metrics.get("deals_without_next_step") or 0)
    if no_next_step_count > 0:
        risk_tail.append(
            f"{_safe(str(no_next_step_count))} "
            f"{_safe(_ru_noun(no_next_step_count, 'сделка', 'сделки', 'сделок'))} без следующего шага"
        )
    overdue_count = int(metrics.get("overdue_deal_task_deals") or 0)
    if overdue_count > 0:
        risk_tail.append(
            f"{_safe(str(overdue_count))} "
            f"{_safe(_ru_noun(overdue_count, 'сделка', 'сделки', 'сделок'))} с просроченными задачами"
        )
    risk_line = (
        f"Под риском {_safe(str(risk_totals.get('deal_risks', 0)))} "
        f"{_safe(_ru_noun(int(risk_totals.get('deal_risks') or 0), 'сделка', 'сделки', 'сделок'))} "
        f"на {_money_html(risk_totals.get('risk_amount'))}."
    )
    if risk_tail:
        risk_line = risk_line.rstrip(".") + "; " + "; ".join(risk_tail) + "."
    lines.append(risk_line)

    yesterday_bits: list[str] = []
    if int(metrics.get("new_deals_yesterday") or 0) > 0:
        yesterday_bits.append(f"новых сделок: {_safe(str(metrics.get('new_deals_yesterday', 0)))}")
    if int(metrics.get("conducted_meetings_yesterday") or 0) > 0:
        yesterday_bits.append(f"встреч: {_safe(str(metrics.get('conducted_meetings_yesterday', 0)))}")
    if int(metrics.get("accepted_briefs_yesterday") or 0) > 0:
        yesterday_bits.append(f"брифов: {_safe(str(metrics.get('accepted_briefs_yesterday', 0)))}")
    if int(metrics.get("lost_deals_yesterday") or 0) > 0:
        yesterday_bits.append(f"отказов: {_safe(str(metrics.get('lost_deals_yesterday', 0)))}")
    if yesterday_bits:
        lines.append("За предыдущий рабочий день: " + "; ".join(yesterday_bits) + ".")

    forecast_amount = metrics.get("expected_forecast_amount")
    if monthly_target is not None and forecast_amount is not None:
        gap = float(monthly_target) - float(forecast_amount)
        if gap > 0:
            lines.append(f"Недобор к плану по текущему прогнозу: {_safe(_format_money(gap))}.")

    limitations = list(dict.fromkeys(list(analysis.get("limitations") or []) + list(communications_summary.get("limitations") or [])))
    system_limitations = list(dict.fromkeys(communications_summary.get("system_limitations") or []))
    limitation_note = next(
        (
            item
            for item in [*system_limitations, *limitations]
            if item and "огранич" in str(item).casefold() and not _looks_like_machine_code(item)
        ),
        "",
    )
    if not limitation_note:
        limitation_note = next(
            (item for item in [*system_limitations, *limitations] if item and not _looks_like_machine_code(item)),
            "",
        )
    if not limitation_note:
        limitation_note = next((item for item in [*system_limitations, *limitations] if item), "")
    if limitation_note:
        lines.append(f"Ограничение: {_safe(limitation_note)}")

    return lines[:4]


def format_sales_brief(
    analysis: dict[str, Any],
    risk_report: dict[str, Any],
    *,
    communications_summary: dict[str, Any] | None = None,
    monthly_target: float | None = None,
) -> str:
    metrics = analysis.get("metrics") or {}
    communications_summary = communications_summary or {}
    report_now = analysis.get("now")
    new_deals_yesterday = list(analysis.get("new_deals_yesterday") or [])
    new_deal_sources_yesterday = list(analysis.get("new_deal_sources_yesterday") or [])
    conducted_meetings_yesterday = [
        item for item in (analysis.get("conducted_meetings") or []) if item.get("yesterday_moved")
    ]
    accepted_briefs_yesterday = [
        item for item in (analysis.get("accepted_briefs") or []) if item.get("yesterday_moved")
    ]
    postponed_deals_yesterday = list(analysis.get("postponed_deals_yesterday") or [])
    lost_deals_yesterday = list(analysis.get("lost_deals_yesterday") or [])
    hot_stage_deals = list(analysis.get("hot_stage_deals") or [])
    stagnant_deals = _sorted_stagnant_deals(
        [item for item in (risk_report.get("deal_risks") or []) if "stagnant" in (item.get("categories") or [])]
    )
    stale_communication_deals = _sorted_stale_deals(list(analysis.get("stale_communication_deals") or []))
    no_next_step_deals = _sorted_no_next_step_deals(list(analysis.get("deals_without_next_step_items") or []))
    communications_items = _communications_items(communications_summary, analysis)
    if not communications_items:
        communications_items = _communications_fallback(communications_summary)
    system_limitations = list(communications_summary.get("system_limitations") or [])[:5]

    limitations = list(analysis.get("limitations") or [])
    limitations.extend(item for item in (communications_summary.get("limitations") or []) if item and item not in system_limitations)
    stale_days_limit = 14
    thresholds = communications_summary.get("thresholds") or {}
    if thresholds:
        stale_days_limit = int(thresholds.get("stale_communication_days") or stale_days_limit)
    comparison = dict(analysis.get("daily_comparison") or {})
    previous_run = dict(comparison.get("previous_run") or {})
    previous_current_metrics = dict(previous_run.get("current_metrics") or {})
    previous_report_day_metrics = dict(previous_run.get("report_day_metrics") or {})
    report_day_label = _report_day_label(comparison.get("report_day"))
    yesterday_flow_lines = [
        _heading_html(f"Итоги за прошлый рабочий день, {report_day_label}"),
        _metric_line(
            "Новые сделки",
            len(new_deals_yesterday),
            previous_count=previous_report_day_metrics.get("new_deals_yesterday"),
        ),
        _metric_line(
            "Встречи",
            metrics.get("conducted_meetings_yesterday", 0),
            previous_count=previous_report_day_metrics.get("conducted_meetings_yesterday"),
        ),
        _metric_line(
            "Брифы",
            metrics.get("accepted_briefs_yesterday", 0),
            previous_count=previous_report_day_metrics.get("accepted_briefs_yesterday"),
        ),
        _metric_line(
            "Отложенные сделки",
            len(postponed_deals_yesterday),
            amount=_sum_amount(postponed_deals_yesterday),
            previous_count=previous_report_day_metrics.get("postponed_deals_yesterday"),
        ),
        _metric_line(
            "Отказы",
            len(lost_deals_yesterday),
            amount=_sum_amount(lost_deals_yesterday),
            previous_count=previous_report_day_metrics.get("lost_deals_yesterday"),
        ),
    ]
    funnel_lines = [
        _metric_line(
            "Активные сделки",
            metrics.get("deals_in_work", 0),
            amount=metrics.get("pipeline_amount"),
            previous_count=previous_current_metrics.get("deals_in_work"),
        ),
        _metric_line(
            "С движением",
            metrics.get("moving_deals_last_week", 0),
            previous_count=previous_current_metrics.get("moving_deals_last_week"),
        ),
        _metric_line(
            "Без движения",
            metrics.get("stagnant_deals_last_week", 0),
            previous_count=previous_current_metrics.get("stagnant_deals_last_week"),
        ),
        _metric_line(
            "В отложке",
            metrics.get("postponed_deals_now", 0),
            previous_count=previous_current_metrics.get("postponed_deals_now"),
        ),
        _metric_line(
            "Этап договора",
            metrics.get("hot_stage_deals", 0),
            amount=metrics.get("hot_stage_amount"),
            previous_count=previous_current_metrics.get("hot_stage_deals"),
        ),
    ]
    contract_lines = [_heading_html("На стадии договора")]
    if hot_stage_deals:
        for item in hot_stage_deals:
            contract_lines.extend(_hot_stage_deal_lines(item))
    else:
        contract_lines.append("Сделок на стадии договора нет.")
    sources_lines = [_heading_html("Источники новых сделок")]
    if new_deal_sources_yesterday:
        sources_lines.extend(f"• {_source_line(item)}" for item in new_deal_sources_yesterday)
    else:
        sources_lines.append("Новых сделок за прошлый рабочий день не было.")
    new_deals_lines = _daily_detail_lines(
        "🆕 Новые сделки за предыдущий рабочий день",
        new_deals_yesterday,
        item_builder=_new_deal_item,
        empty_text="Новых сделок за предыдущий рабочий день нет.",
    )
    meetings_lines = _daily_detail_lines(
        "🤝 Встречи за предыдущий рабочий день",
        conducted_meetings_yesterday,
        item_builder=_meeting_item,
        empty_text="Проведённых встреч за предыдущий рабочий день нет.",
        limit=None,
    )
    briefs_lines = _daily_detail_lines(
        "📝 Брифы за предыдущий рабочий день",
        accepted_briefs_yesterday,
        item_builder=_brief_item,
        empty_text="Принятых брифов за предыдущий рабочий день нет.",
        limit=None,
    )
    postponed_lines = _daily_detail_lines(
        "⏸ Отложенные сделки за предыдущий рабочий день",
        postponed_deals_yesterday,
        item_builder=lambda item: _postponed_deal_item(item, now=report_now if isinstance(report_now, datetime) else None),
        empty_text="Отложенных сделок за предыдущий рабочий день нет.",
        limit=None,
    )
    lost_lines = _daily_detail_lines(
        "📉 Отказы за предыдущий рабочий день",
        lost_deals_yesterday,
        item_builder=_lost_deal_item,
        empty_text="Отказов за предыдущий рабочий день нет.",
        limit=None,
    )
    lines = [
        _heading_html("📊 Сводка по продажам"),
        _heading_html("Лев Петрович"),
        "",
        f"Срез: {_safe(_format_dt(report_now))} МСК" if isinstance(report_now, datetime) else "Срез: текущее утро МСК",
        "",
        *yesterday_flow_lines,
        "",
        _heading_html("Воронка"),
        *(funnel_lines or ["• Данных по воронке недостаточно."]),
        "",
        *contract_lines,
        "",
        *sources_lines,
        "",
        _heading_html("📞 Коммуникации за предыдущий рабочий день"),
        *(communications_items or ["Данных по коммуникациям недостаточно."]),
        "",
        *new_deals_lines,
        "",
        *meetings_lines,
        "",
        *briefs_lines,
        "",
        *postponed_lines,
        "",
        *lost_lines,
    ]
    return "\n".join(_append_limitations(lines, list(dict.fromkeys(system_limitations + limitations))))


def format_pipeline_report(
    analysis: dict[str, Any],
    risk_report: dict[str, Any],
    *,
    monthly_target: float | None = None,
) -> str:
    return format_sales_brief(
        analysis,
        risk_report,
        communications_summary={},
        monthly_target=monthly_target,
    )


def format_risks_report(
    analysis: dict[str, Any],
    risk_report: dict[str, Any],
    *,
    communications_summary: dict[str, Any] | None = None,
) -> str:
    communications_summary = communications_summary or {}
    metrics = analysis.get("metrics") or {}
    report_now = analysis.get("now")
    stale_days_limit = int((communications_summary.get("thresholds") or {}).get("stale_communication_days") or 14)
    comparison = dict(analysis.get("daily_comparison") or {})
    previous_run = dict(comparison.get("previous_run") or {})
    previous_current_metrics = dict(previous_run.get("current_metrics") or {})
    risk_totals = dict(risk_report.get("summary_totals") or risk_report.get("totals") or {})
    category_totals = dict(risk_report.get("category_totals") or {})

    stagnant_deals = _sorted_stagnant_deals(
        [item for item in (risk_report.get("deal_risks") or []) if "stagnant" in (item.get("categories") or [])]
    )
    no_next_step_deals = _sorted_no_next_step_deals(list(analysis.get("deals_without_next_step_items") or []))
    stale_communication_deals = _sorted_stale_deals(list(analysis.get("stale_communication_deals") or []))
    overdue_deals = _overdue_risk_deals(analysis)

    summary_lines = [
        _metric_line(
            "Уникальные риск-сделки",
            risk_totals.get("deal_risks", 0),
            amount=risk_totals.get("risk_amount"),
            previous_count=previous_current_metrics.get("deal_risks"),
        ),
        _metric_line(
            "Без движения > 14 дн.",
            category_totals.get("stagnant_deals", 0),
            amount=category_totals.get("stagnant_amount"),
            previous_count=previous_current_metrics.get("stagnant_risk_deals"),
        ),
        _metric_line(
            "Без следующего шага",
            category_totals.get("deals_without_next_step", metrics.get("deals_without_next_step", 0)),
            amount=category_totals.get("deals_without_next_step_amount", metrics.get("deals_without_next_step_amount")),
            previous_count=previous_current_metrics.get("deals_without_next_step"),
        ),
        _metric_line(
            f"Без коммуникации > {stale_days_limit} дн.",
            category_totals.get("stale_communication_deals", metrics.get("stale_communication_deals", 0)),
            amount=category_totals.get("stale_communication_amount", metrics.get("stale_communication_amount")),
            previous_count=previous_current_metrics.get("stale_communication_deals"),
        ),
        _metric_line(
            "Сделки с просрочками",
            category_totals.get("overdue_deal_task_deals", metrics.get("overdue_deal_task_deals", 0)),
            amount=category_totals.get("overdue_deal_task_amount", metrics.get("overdue_deal_task_amount")),
            previous_count=previous_current_metrics.get("overdue_deal_task_deals"),
        ),
    ]

    stagnant_lines = _risk_category_block(
        "Без движения > 14 дн.",
        stagnant_deals,
        item_builder=_stagnant_deal_item,
        empty_text="Нет сделок без движения более 14 дней.",
    )
    no_next_step_lines = _risk_category_block(
        "Без следующего шага",
        no_next_step_deals,
        item_builder=_daily_no_next_step_item,
        empty_text="Нет сделок без следующего шага.",
    )
    stale_lines = _risk_category_block(
        f"Без коммуникации > {stale_days_limit} дн.",
        stale_communication_deals,
        item_builder=_stale_deal_item,
        empty_text=f"Нет сделок без коммуникации более {stale_days_limit} дней.",
    )
    overdue_lines = _risk_category_block(
        "Сделки с просрочками",
        overdue_deals,
        item_builder=_overdue_deal_item,
        empty_text="Нет сделок с просроченными задачами.",
    )

    lines = [
        _heading_html("⚠️ Риски по сделкам"),
        _heading_html("Лев Петрович"),
        "",
        f"Срез: {_safe(_format_dt(report_now))} МСК" if isinstance(report_now, datetime) else "Срез: текущее утро МСК",
        "",
        _heading_html("Сводка"),
        *(summary_lines or ["• Данных по рискам недостаточно."]),
        "",
        *stagnant_lines,
        "",
        *no_next_step_lines,
        "",
        *stale_lines,
        "",
        *overdue_lines,
    ]
    return "\n".join(_append_limitations(lines, list(analysis.get("limitations") or [])))


def format_focus_sales_report(
    analysis: dict[str, Any],
    risk_report: dict[str, Any],
    *,
    communications_summary: dict[str, Any] | None = None,
) -> str:
    lines = [_heading_html("🎯 Фокус РОПа"), *_build_rop_focus_lines(analysis, risk_report, communications_summary)]
    return "\n".join(lines)


def format_followup_report(analysis: dict[str, Any], risk_report: dict[str, Any]) -> str:
    del analysis
    followups = [
        f"{_entity_html(item)}\n{_safe(item['actions'][0])}"
        for item in (risk_report.get("high_risk_deals") or [])[:5]
        if item.get("actions")
    ]
    lines = [
        _heading_html("📌 Контроль до конца дня"),
        "",
        _heading_html("Что ещё висит"),
        *_bullet_list(followups[:3], "Критичных хвостов к вечеру нет."),
        "",
        _heading_html("Что требует реакции до конца дня"),
        *_bullet_list(followups[3:5], "Срочных реакций не найдено."),
    ]
    return "\n".join(lines)


def _in_period(value: Any, start: datetime, end: datetime) -> bool:
    return isinstance(value, datetime) and start <= value.astimezone(MOSCOW_TZ) < end


def _period_label(start_value: Any, end_value: Any) -> str:
    start = start_value.strftime("%d.%m") if hasattr(start_value, "strftime") else "-"
    end = end_value.strftime("%d.%m") if hasattr(end_value, "strftime") else "-"
    return f"{start}–{end}"


def _role_label(role: str) -> str:
    normalized = str(role or "").strip().lower()
    if normalized == "telemarketing":
        return "телемаркетолог"
    if normalized == "sales":
        return "менеджер по продажам"
    return "сотрудник"


def _connect_label(value: Any) -> str:
    if value in (None, ""):
        return "0%"
    percent = round(float(value) * 100)
    return f"{int(percent)}%"


def _count_with_noun(count: int, one: str, few: str, many: str) -> str:
    return f"{_safe(str(count))} {_safe(_ru_noun(count, one, few, many))}"


def _weekly_meeting_counts(analysis: dict[str, Any], start: datetime, end: datetime) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in analysis.get("conducted_meetings") or []:
        if not _in_period(item.get("moved_at"), start, end):
            continue
        manager_key = _manager_identity_key(item.get("assigned_id"), item.get("assigned_name"))
        counts[manager_key] = counts.get(manager_key, 0) + 1
    return counts


def _weekly_reschedule_stats(analysis: dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    by_manager: dict[str, int] = {}
    by_deal: dict[str, int] = {}
    for item in analysis.get("deadline_reschedule_focus_tasks") or []:
        manager_key = str(item.get("manager_id") or item.get("manager_name") or "").strip()
        deal_key = str(item.get("deal_id") or "").strip()
        if manager_key:
            by_manager[manager_key] = by_manager.get(manager_key, 0) + 1
        if deal_key:
            by_deal[deal_key] = max(by_deal.get(deal_key, 0), int(item.get("deadline_change_count") or 0))
    return (by_manager, by_deal)


def _weekly_overdue_by_deal(analysis: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in analysis.get("overdue_deal_tasks") or []:
        deal_id = str(item.get("deal_id") or "").strip()
        if not deal_id:
            continue
        result[deal_id] = max(result.get(deal_id, 0), int(item.get("days_overdue") or 0))
    return result


def _manager_comparison_note(current_item: dict[str, Any], previous_map: dict[str, dict[str, Any]]) -> str:
    manager_id = str(current_item.get("manager_id") or "").strip()
    previous = previous_map.get(manager_id) or {}
    previous_total = int(previous.get("total_known") or 0)
    current_total = int(current_item.get("total_known") or 0)
    if previous_total <= 0:
        return ""
    if current_total < previous_total * 0.6:
        return f"просадка к прошлой неделе: {previous_total} -> {current_total} коммуникаций"
    return ""


def _weekly_people_sections(
    analysis: dict[str, Any],
    risk_report: dict[str, Any],
    weekly_context: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    summary = weekly_context.get("communications_summary") or {}
    previous_summary = weekly_context.get("previous_communications_summary") or {}
    managers = list(summary.get("manager_stats") or summary.get("managers") or [])
    previous_map = {
        str(item.get("manager_id") or "").strip(): item
        for item in (previous_summary.get("manager_stats") or previous_summary.get("managers") or [])
        if str(item.get("manager_id") or "").strip()
    }
    if not managers:
        return (["• Данных по людям за неделю недостаточно."], [], [])

    start = weekly_context.get("start")
    end = weekly_context.get("end")
    meeting_counts = _weekly_meeting_counts(analysis, start, end) if isinstance(start, datetime) and isinstance(end, datetime) else {}
    reschedule_by_manager, _ = _weekly_reschedule_stats(analysis)

    risk_amount_by_manager: dict[str, float] = {}
    risk_count_by_manager: dict[str, int] = {}
    risky_deal_ids = {str(item.get("entity_id") or "").strip() for item in (risk_report.get("deal_risks") or [])}
    for deal in analysis.get("active_deals") or []:
        manager_key = str(deal.get("assigned_id") or deal.get("assigned_name") or "").strip()
        if not manager_key:
            continue
        if str(deal.get("id") or "").strip() in risky_deal_ids:
            risk_count_by_manager[manager_key] = risk_count_by_manager.get(manager_key, 0) + 1
            risk_amount_by_manager[manager_key] = risk_amount_by_manager.get(manager_key, 0.0) + float(deal.get("amount") or 0.0)

    sales_rows: list[dict[str, Any]] = []
    tele_rows: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for item in managers:
        role = str(item.get("employee_role") or "unknown").strip().lower()
        manager_key = str(item.get("manager_id") or item.get("manager_name") or "").strip()
        current_total = int(item.get("total_known") or 0)
        normal_calls = int(item.get("normal_calls") or 0)
        dials = int(item.get("dials") or 0)
        messenger_dialogs = int(item.get("messenger_dialogs") or 0)
        meetings = meeting_counts.get(_manager_identity_key(item.get("manager_id"), item.get("manager_name")), 0)
        missing_next_step_count = int(item.get("missing_next_step_count") or 0)
        stale_communication_count = int(item.get("stale_communication_count") or 0)
        late_stage_stuck_count = int(item.get("late_stage_stuck_count") or 0)
        overdue_tasks_count = int(item.get("overdue_tasks_count") or 0)
        reschedule_count = int(reschedule_by_manager.get(manager_key) or 0)
        risk_count = int(risk_count_by_manager.get(manager_key) or 0)
        risk_amount = float(risk_amount_by_manager.get(manager_key) or 0.0)
        comparison_note = _manager_comparison_note(item, previous_map)
        activity_imitation = role == "telemarketing" and dials >= 30 and normal_calls <= 1 and messenger_dialogs <= 1

        if role == "telemarketing":
            strength = (normal_calls * 3) + (dials / 8.0) + messenger_dialogs + (2 if (item.get("connect_rate") or 0) >= 0.2 else 0)
            weakness = (3 if activity_imitation else 0) + (2 if dials < DEFAULT_TELEMARKETING_MIN_DIALS else 0) + (
                2 if dials >= 15 and float(item.get("connect_rate") or 0.0) < 0.12 else 0
            ) + (1 if comparison_note else 0)
            row = {
                "role": role,
            "manager_name": _display_person_name(item.get("manager_name") or "без ответственного"),
            "summary_strong": (
                f"{_safe(_display_person_name(item.get('manager_name') or 'без ответственного'))} — "
                f"{_count_with_noun(dials, 'набор', 'набора', 'наборов')}, {_count_with_noun(normal_calls, 'дозвон', 'дозвона', 'дозвонов')}, "
                f"конверсия {_safe(_connect_label(item.get('connect_rate')))}, "
                f"{_count_with_noun(messenger_dialogs, 'чат', 'чата', 'чатов')}"
            ),
            "summary_weak": (
                f"{_safe(_display_person_name(item.get('manager_name') or 'без ответственного'))} — "
                f"{_count_with_noun(dials, 'набор', 'набора', 'наборов')}, {_count_with_noun(normal_calls, 'дозвон', 'дозвона', 'дозвонов')}, "
                f"конверсия {_safe(_connect_label(item.get('connect_rate')))}"
                + ("; признаки имитации активности" if activity_imitation else "")
            ),
            "summary_drop": (
                f"{_safe(_display_person_name(item.get('manager_name') or 'без ответственного'))} — {comparison_note}; "
                f"{_count_with_noun(normal_calls, 'дозвон', 'дозвона', 'дозвонов')}, {_count_with_noun(messenger_dialogs, 'чат', 'чата', 'чатов')}"
            )
                if comparison_note
                else "",
                "weakness": weakness,
                "strength": strength,
                "role_label": _role_label(role),
                "reason": (
                    "имитация активности" if activity_imitation else "слабый дозвон и конверсия"
                ),
            }
            tele_rows.append(row)
            all_rows.append(row)
            continue

        strength = (meetings * 3) + (normal_calls * 2) + messenger_dialogs + min(current_total, 8) - (
            risk_count + missing_next_step_count + stale_communication_count + overdue_tasks_count
        )
        weakness = (
            risk_count * 3
            + missing_next_step_count * 2
            + stale_communication_count * 2
            + late_stage_stuck_count * 2
            + overdue_tasks_count * 2
            + reschedule_count
            + (1 if comparison_note else 0)
        )
        weak_parts = [
            f"{_count_with_noun(missing_next_step_count, 'сделка', 'сделки', 'сделок')} без следующего шага" if missing_next_step_count else "",
            f"{_count_with_noun(late_stage_stuck_count, 'поздняя стадия', 'поздние стадии', 'поздних стадий')} без движения" if late_stage_stuck_count else "",
            f"{_count_with_noun(stale_communication_count, 'сделка', 'сделки', 'сделок')} без коммуникации > 14 дн." if stale_communication_count else "",
            f"{_count_with_noun(overdue_tasks_count, 'просроченная задача', 'просроченные задачи', 'просроченных задач')}" if overdue_tasks_count else "",
            f"{_count_with_noun(reschedule_count, 'задача', 'задачи', 'задач')} с 3+ переносами" if reschedule_count else "",
        ]
        weak_parts = [part for part in weak_parts if part]
        row = {
            "role": role,
            "manager_name": _display_person_name(item.get("manager_name") or "без ответственного"),
            "summary_strong": (
                f"{_safe(_display_person_name(item.get('manager_name') or 'без ответственного'))} — "
                f"{_count_with_noun(meetings, 'встреча', 'встречи', 'встреч')}, {_count_with_noun(normal_calls, 'дозвон', 'дозвона', 'дозвонов')}, "
                f"{_count_with_noun(missing_next_step_count, 'сделка', 'сделки', 'сделок')} без следующего шага"
            ),
            "summary_weak": (
                f"{_safe(_display_person_name(item.get('manager_name') or 'без ответственного'))} — "
                f"{'; '.join(weak_parts[:3]) if weak_parts else 'нужен разбор по рискам'}; "
                f"{_safe(_format_money(risk_amount))} под риском"
            ),
            "summary_drop": (
                f"{_safe(_display_person_name(item.get('manager_name') or 'без ответственного'))} — {comparison_note}; "
                f"сейчас {_count_with_noun(meetings, 'встреча', 'встречи', 'встреч')} и {_count_with_noun(normal_calls, 'дозвон', 'дозвона', 'дозвонов')}"
            )
            if comparison_note
            else "",
            "weakness": weakness,
            "strength": strength,
            "role_label": _role_label(role),
            "reason": "; ".join(weak_parts[:3]) if weak_parts else "деньги под риском",
        }
        sales_rows.append(row)
        all_rows.append(row)

    def _role_lines(title: str, rows: list[dict[str, Any]]) -> list[str]:
        if not rows:
            return [title, "• Данных недостаточно."]
        strong = [
            item["summary_strong"]
            for item in sorted(rows, key=lambda item: item["strength"], reverse=True)
            if item["strength"] >= 4 and int(item.get("weakness") or 0) == 0
        ][:2]
        weak = [item["summary_weak"] for item in sorted(rows, key=lambda item: item["weakness"], reverse=True) if item["weakness"] > 0][:2]
        drops = [item["summary_drop"] for item in rows if item.get("summary_drop")][:2]
        result = [title]
        result.extend(_bullet_list([f"Сильные: {'; '.join(strong)}"], "Сильных сигналов не найдено.") if strong else ["• Сильные: явных лидеров не выделено."])
        result.extend(_bullet_list([f"Слабые: {'; '.join(weak)}"], "Слабых сигналов не найдено.") if weak else ["• Слабые: выраженных просадок не найдено."])
        result.extend(_bullet_list([f"Просадка: {'; '.join(drops)}"], "Просадки к прошлой неделе не видно.") if drops else ["• Просадка: сравнение с прошлой неделей ограничено."])
        return result

    lines = [
        *_role_lines("Менеджеры по продажам", sales_rows),
        "",
        *_role_lines("Телемаркетинг", tele_rows),
    ]
    action_hints = [item["reason"] for item in sorted(all_rows, key=lambda item: item["weakness"], reverse=True) if item["weakness"] > 0][:3]
    return (
        lines,
        [item for item in sorted(all_rows, key=lambda item: item["weakness"], reverse=True) if int(item.get("weakness") or 0) > 0],
        action_hints,
    )


def _weekly_stage_lines(analysis: dict[str, Any], risk_report: dict[str, Any]) -> list[str]:
    risk_by_deal_id = {str(item.get("entity_id") or "").strip(): item for item in (risk_report.get("deal_risks") or [])}
    by_stage: dict[str, dict[str, Any]] = {}
    for deal in analysis.get("active_deals") or []:
        stage_name = str(deal.get("stage_name") or "Без стадии").strip()
        row = by_stage.setdefault(
            stage_name,
            {"stage_name": stage_name, "risk": 0, "missing_next_step": 0, "stuck": 0, "stale": 0, "late": 0, "amount": 0.0},
        )
        row["amount"] += float(deal.get("amount") or 0.0)
        if str(deal.get("id") or "").strip() in risk_by_deal_id:
            row["risk"] += 1
        if deal.get("missing_next_step"):
            row["missing_next_step"] += 1
        if int(deal.get("inactive_days") or 0) >= 5:
            row["stuck"] += 1
        if int(deal.get("communication_gap_days") or 0) >= 14:
            row["stale"] += 1
        if deal.get("late_stage"):
            row["late"] += 1

    problem_rows = [
        row
        for row in by_stage.values()
        if int(row["risk"]) or int(row["missing_next_step"]) or int(row["stuck"]) or int(row["stale"])
    ]
    problem_rows.sort(
        key=lambda item: (int(item["risk"]), int(item["missing_next_step"]), int(item["stuck"]), int(item["stale"]), float(item["amount"])),
        reverse=True,
    )
    return [
        f"{_safe(item['stage_name'])} — под риском {_safe(str(item['risk']))}, без следующего шага {_safe(str(item['missing_next_step']))}, без движения {_safe(str(item['stuck']))}, сумма {_money_html(item['amount'])}"
        for item in problem_rows[:3]
    ]


def _weekly_source_lines(analysis: dict[str, Any], weekly_context: dict[str, Any]) -> tuple[list[str], list[str]]:
    start = weekly_context.get("start")
    end = weekly_context.get("end")
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        return (["Блок пока ограничен: период недели не определён."], [])

    by_source: dict[str, dict[str, Any]] = {}
    for deal in analysis.get("active_deals") or []:
        source_name = str(deal.get("source_name") or "Источник не указан").strip()
        row = by_source.setdefault(source_name, {"source_name": source_name, "moving": 0, "stuck": 0, "high_probability": 0, "lost": 0})
        if int(deal.get("inactive_days") or 0) < 5:
            row["moving"] += 1
        else:
            row["stuck"] += 1
        if deal.get("high_probability"):
            row["high_probability"] += 1
    for deal in analysis.get("closed_deals") or []:
        if not deal.get("lost") or not _in_period(deal.get("moved_at"), start, end):
            continue
        source_name = str(deal.get("source_name") or "Источник не указан").strip()
        row = by_source.setdefault(source_name, {"source_name": source_name, "moving": 0, "stuck": 0, "high_probability": 0, "lost": 0})
        row["lost"] += 1

    if not by_source:
        return (["Блок пока ограничен: по источникам нет live-данных."], [])

    ordered = sorted(by_source.values(), key=lambda item: (int(item["moving"]), int(item["high_probability"]), -int(item["lost"]), -int(item["stuck"])), reverse=True)
    lines = []
    weak_sources: list[str] = []
    for item in ordered[:4]:
        line = (
            f"{_safe(item['source_name'])} — живые сделки {_safe(str(item['moving']))}, "
            f"Высокая вероятность {_safe(str(item['high_probability']))}, "
            f"зависание {_safe(str(item['stuck']))}, отказов {_safe(str(item['lost']))}"
        )
        lines.append(line)
        if int(item["lost"]) > 0 or int(item["stuck"]) > int(item["moving"]):
            weak_sources.append(str(item["source_name"]))
    return (lines, weak_sources[:2])


def _weekly_money_lines(analysis: dict[str, Any], risk_report: dict[str, Any], weekly_context: dict[str, Any]) -> tuple[list[str], list[str]]:
    summary = weekly_context.get("communications_summary") or {}
    manager_roles = {
        str(item.get("manager_id") or "").strip(): str(item.get("employee_role") or "unknown").strip().lower()
        for item in (summary.get("manager_stats") or summary.get("managers") or [])
        if str(item.get("manager_id") or "").strip()
    }
    risky_amount_by_manager: dict[str, float] = {}
    risky_deal_ids = {str(item.get("entity_id") or "").strip() for item in (risk_report.get("deal_risks") or [])}
    for deal in analysis.get("active_deals") or []:
        manager_id = str(deal.get("assigned_id") or "").strip()
        if manager_roles.get(manager_id) != "sales":
            continue
        deal_id = str(deal.get("id") or "").strip()
        if deal_id in risky_deal_ids or deal.get("missing_next_step") or int(deal.get("inactive_days") or 0) >= 5:
            risky_amount_by_manager[manager_id] = risky_amount_by_manager.get(manager_id, 0.0) + float(deal.get("amount") or 0.0)
    top_managers = []
    manager_name_map = {
        str(item.get("manager_id") or "").strip(): _display_person_name(item.get("manager_name") or "")
        for item in (summary.get("manager_stats") or summary.get("managers") or [])
    }
    for manager_id, amount in sorted(risky_amount_by_manager.items(), key=lambda item: float(item[1]), reverse=True)[:3]:
        top_managers.append(f"{_safe(manager_name_map.get(manager_id) or manager_id)} — {_money_html(amount)}")
    lines = [
        f"Деньги под риском: {_money_html(risk_report.get('totals', {}).get('risk_amount'))}",
        f"Без движения: {_money_html(sum(float(item.get('amount') or 0.0) for item in (analysis.get('active_deals') or []) if int(item.get('inactive_days') or 0) >= 5))}",
        f"Без следующего шага: {_money_html(analysis.get('metrics', {}).get('deals_without_next_step_amount'))}",
        f"Без коммуникации > 14 дн.: {_money_html(analysis.get('metrics', {}).get('stale_communication_amount'))}",
    ]
    if top_managers:
        lines.append(f"Основной риск у менеджеров: {'; '.join(top_managers)}")
    return (lines, top_managers)


def _weekly_problem_deal_lines(
    analysis: dict[str, Any],
    risk_report: dict[str, Any],
    weekly_context: dict[str, Any],
) -> tuple[list[str], list[str]]:
    start = weekly_context.get("start")
    end = weekly_context.get("end")
    reschedule_by_deal = _weekly_reschedule_stats(analysis)[1]
    overdue_by_deal = _weekly_overdue_by_deal(analysis)
    summary = weekly_context.get("communications_summary") or {}
    role_by_manager = {
        str(item.get("manager_id") or "").strip(): _role_label(str(item.get("employee_role") or "unknown"))
        for item in (summary.get("manager_stats") or summary.get("managers") or [])
    }
    risk_by_deal_id = {
        str(item.get("entity_id") or "").strip(): item
        for item in (risk_report.get("deal_risks") or [])
        if str(item.get("entity_id") or "").strip()
    }
    candidates: dict[str, dict[str, Any]] = {}
    for collection in (
        risk_report.get("high_risk_deals") or [],
        analysis.get("deals_without_next_step_items") or [],
        analysis.get("stale_communication_deals") or [],
    ):
        for item in collection:
            deal_id = str(item.get("id") or "").strip()
            if deal_id:
                candidates[deal_id] = item
    if isinstance(start, datetime) and isinstance(end, datetime):
        for item in analysis.get("closed_deals") or []:
            if item.get("lost") and _in_period(item.get("moved_at"), start, end) and float(item.get("amount") or 0.0) > 0:
                deal_id = str(item.get("id") or "").strip()
                if deal_id:
                    candidates[deal_id] = item

    def _priority(item: dict[str, Any]) -> tuple[int, int, int, int, float]:
        deal_id = str(item.get("id") or "").strip()
        risk_item = risk_by_deal_id.get(deal_id) or {}
        return (
            int((risk_item.get("severity") or 0)),
            int(reschedule_by_deal.get(deal_id) or 0),
            int(overdue_by_deal.get(deal_id) or 0),
            int(bool(item.get("late_stage"))) + int(bool(item.get("missing_next_step"))) + int(int(item.get("communication_gap_days") or 0) >= 14),
            float(item.get("amount") or 0.0),
        )

    lines: list[str] = []
    actions: list[str] = []
    for item in sorted(candidates.values(), key=_priority, reverse=True)[:5]:
        deal_id = str(item.get("id") or "").strip()
        reasons: list[str] = []
        if item.get("late_stage") and int(item.get("inactive_days") or 0) >= 5:
            reasons.append(f"поздняя стадия без движения {int(item.get('inactive_days') or 0)} дн.")
        if item.get("missing_next_step"):
            reasons.append("нет следующего шага")
        if int(item.get("communication_gap_days") or 0) >= 14:
            reasons.append(f"нет коммуникации {int(item.get('communication_gap_days') or 0)} дн.")
        if int(overdue_by_deal.get(deal_id) or 0) > 0:
            reasons.append(f"просроченная задача {int(overdue_by_deal.get(deal_id) or 0)} дн.")
        if int(reschedule_by_deal.get(deal_id) or 0) >= 3:
            reasons.append(f"{int(reschedule_by_deal.get(deal_id) or 0)} переноса срока")
        role_label = role_by_manager.get(str(item.get("assigned_id") or "").strip())
        extra_role = f"; роль: {role_label}" if role_label else ""
        reason_text = "; ".join(reasons[:3]) or "крупная сумма под риском"
        lines.append(
            f"{_entity_html(item)}{extra_role}\nпроблема: {_safe(reason_text)}"
        )
        actions.append(f"Поднять {_entity_html(item)} и закрыть проблему: {_safe(reason_text)}")
    return (lines, actions)


def format_weekly_review(
    analysis: dict[str, Any],
    risk_report: dict[str, Any],
    *,
    weekly_context: dict[str, Any] | None = None,
    monthly_target: float | None = None,
) -> str:
    weekly_context = weekly_context or {}
    metrics = analysis.get("metrics") or {}
    start = weekly_context.get("start")
    end = weekly_context.get("end")
    custom_period = bool(weekly_context.get("custom_period"))
    title = str(weekly_context.get("title") or "🗓 Еженедельный отчёт Льва Петровича")
    summary_heading = str(weekly_context.get("summary_heading") or "1. Что произошло за неделю")
    people_heading = str(weekly_context.get("people_heading") or "3. Люди за неделю")
    problem_deals_heading = str(weekly_context.get("problem_deals_heading") or "5. Проблемные сделки недели")
    period_start_label = weekly_context.get("start_date") or start
    period_end_label = weekly_context.get("end_date") or ((end - timedelta(days=1)) if isinstance(end, datetime) else end)
    period_label = _period_label(period_start_label, period_end_label) if period_start_label and period_end_label else "текущая рабочая неделя"

    new_deals_week = [
        item
        for item in (analysis.get("deals") or [])
        if _in_period(item.get("created_at"), start, end)
    ] if isinstance(start, datetime) and isinstance(end, datetime) else []
    lost_deals_week = [
        item
        for item in (analysis.get("closed_deals") or [])
        if item.get("lost") and _in_period(item.get("moved_at"), start, end)
    ] if isinstance(start, datetime) and isinstance(end, datetime) else []

    stage_lines = _weekly_stage_lines(analysis, risk_report)
    people_lines, weak_people, people_hints = _weekly_people_sections(analysis, risk_report, weekly_context)
    money_lines, _ = _weekly_money_lines(analysis, risk_report, weekly_context)
    problem_deal_lines, problem_actions = _weekly_problem_deal_lines(analysis, risk_report, weekly_context)
    source_lines, weak_sources = _weekly_source_lines(analysis, weekly_context)

    planorka_lines = []
    for item in weak_people[:3]:
        planorka_lines.append(
            f"{_safe(_display_person_name(item.get('manager_name') or 'без ответственного'))} — {_safe(item.get('role_label') or 'сотрудник')}. {_safe(item.get('reason') or 'нужен разбор')}"
        )

    actions: list[str] = []
    if problem_actions:
        actions.append(problem_actions[0])
    if weak_people:
        first = weak_people[0]
        role_label = str(first.get("role_label") or "сотрудник")
        if role_label == "телемаркетолог":
            actions.append(f"Отдельно разобрать {_safe(first.get('manager_name') or 'сотрудника')} по дозвону, конверсии и полезной отдаче.")
        else:
            actions.append(f"Отдельно пройти {_safe(first.get('manager_name') or 'сотрудника')} по сделкам без следующего шага и деньгам под риском.")
    if weak_sources:
        actions.append(f"Проверить качество источников: {_safe(', '.join(weak_sources))}.")
    if len(weak_people) > 1:
        second = weak_people[1]
        actions.append(f"Усилить контроль по {_safe(second.get('manager_name') or 'команде')}: {_safe(second.get('reason') or 'есть повторяющийся риск')}.")
    if people_hints:
        actions.append(f"Не упустить: {_safe(people_hints[0])}.")

    summary_lines = [
        f"В работу пришло: {_safe(str(len(new_deals_week)))} / {_money_html(sum(float(item.get('amount') or 0.0) for item in new_deals_week))}",
        f"Ушло в отказ: {_safe(str(len(lost_deals_week)))} / {_money_html(sum(float(item.get('amount') or 0.0) for item in lost_deals_week))}",
        f"Высокая вероятность: {_safe(str(metrics.get('high_probability_deals', 0)))} / {_money_html(metrics.get('high_probability_amount'))}",
        f"Под риском: {_safe(str(risk_report.get('totals', {}).get('deal_risks', 0)))} / {_money_html(risk_report.get('totals', {}).get('risk_amount'))}",
        f"Без следующего шага: {_safe(str(metrics.get('deals_without_next_step', 0)))} / {_money_html(metrics.get('deals_without_next_step_amount'))}",
        f"Без коммуникации > 14 дн.: {_safe(str(metrics.get('stale_communication_deals', 0)))} / {_money_html(metrics.get('stale_communication_amount'))}",
    ]

    limitations = list(analysis.get("limitations") or [])
    for item in (weekly_context.get("communications_summary") or {}).get("limitations") or []:
        if item not in limitations:
            limitations.append(item)

    lines = [
        title,
        "",
        f"Период: {_safe(period_label)}",
        "",
        summary_heading,
        *_bullet_list(summary_lines, "Данных по неделе недостаточно."),
        "",
        "2. Где воронка просела",
        *_bullet_list(stage_lines, "Явных недельных провалов по воронке не найдено."),
        "",
        people_heading,
        *people_lines,
        "",
        "4. Деньги под риском",
        *_bullet_list(money_lines, "Данных по денежным рискам недостаточно."),
        "",
        problem_deals_heading,
        *_bullet_list(problem_deal_lines, "Критичных проблемных сделок на этой неделе не выделено."),
        "",
        "6. Источники",
        *_bullet_list(source_lines, "Блок пока ограничен отсутствием live-источников качества."),
        "",
        "7. Кого разбирать на планёрке",
        *_bullet_list(planorka_lines, "Планёрка может пройти без персональных эскалаций."),
        "",
        "8. Что делать дальше" if custom_period else "8. Что делать на следующей неделе",
        *_numbered_list(actions[:5], "Поднять сделки без следующего шага и деньги под риском."),
    ]
    if monthly_target is not None:
        lines.extend(["", f"Цель месяца: {_money_html(monthly_target)}", f"Прогноз месяца: {_money_html(metrics.get('expected_forecast_amount'))}"])
    return "\n".join(_append_limitations(lines, limitations))
