#!/usr/bin/env python3
"""Синхронизация существующего WD-калькулятора (1AZ6I8Lz...) с актуальными ставками 2026.

Применяет к существующему калькулятору v1+extend (после extend_v1.py) пакет точечных
правок на основе фактических ставок Belberry 2026 и решений финдиректора 2026-05-20:

1. **Ставки** (лист «Ставки»):
   - Дизайн премиум 3,500 → 3,100 (единая базовая)
   - Техлид 2,600 → 3,100
   - Лицензия Bitrix 110,000 → 47,000 (Малый бизнес актуал 2026)
   - Лицензия/шаблон Strapi 125,000 → 69,000 (актуал 2026)
   - Цена текста для товара 2,600 → 5,200 (через медкопирайтера)
   - ТЗ копирайтеру 1,300 → 0 (входит в работу)
   - Добавлены: контент-менеджер 2,000 ₽/ч, фотограф 10,000 ₽/ч

2. **Бриф** (внизу, новые блоки):
   - 0a. Дополнительно: Перенос данных (D59,D60), Фотосъёмка (D61,D62)
   - 0b. Условия КП: Срок подписания для скидки 5% (D67) = 7 раб.дней
   - 0c. Дополнительная функциональность: Сертификаты (D70), ЛК пациента (D71)
   - + МИС-интеграция (D63,D64) — глубокая, с риск-коэффициентом

3. **Варианты** (Страпи / Битрикс / Индивидуал) — новые строки сметы:
   - №34 Перенос данных (× 2,000 ₽/ч КМ)
   - №35 Фотосъёмка (× 10,000 ₽/ч фотограф)
   - №36 Интеграция с МИС (Strapi: warning, Bitrix: 60ч, Custom: 100ч, +30% без API docs)
   - №37 Сертификаты/депозиты (Strapi: 12ч, Bitrix: 20ч, Custom: 32ч)
   - №38 Личный кабинет пациента (только Custom: 160ч, Strapi/Bitrix: warning)
   - Фикс: SUM формула ИТОГО ЭТАП 2 расширена с F18:F41 до F18:F46

4. **Текст КП** (лист «Текст КП»):
   - Формула «дата подписания для скидки» — теперь использует D67 (7 дней)
     вместо D56 (срок действия КП = 14 дней)

ЗАПУСК (после того как extend_v1.py был выполнен на целевом Sheet):

    python sync_to_actual_2026.py
    python sync_to_actual_2026.py --dry-run

Идемпотентность: скрипт проверяет наличие маркеров перед добавлением блоков.
Безопасно запускать повторно — повторных вставок не будет.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

try:
    from .rates import RATES, PLATFORMS
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from rates import RATES, PLATFORMS  # type: ignore


SHEET_ID_V1 = "1AZ6I8Lz6Ppu5y2OLSG7Tw0p8X0pC3N1Fq3Yk8TG4RoY"
DEFAULT_KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

MARKER_BLOCK_0A = "━━━ 0a. ДОПОЛНИТЕЛЬНО"
MARKER_BLOCK_0B = "━━━ 0b. УСЛОВИЯ КП"
MARKER_BLOCK_0C = "━━━ 0c. ДОПОЛНИТЕЛЬНАЯ ФУНКЦИОНАЛЬНОСТЬ"


# ────────────────────────────────────────────────────────────────────────────
# Helpers

def open_sheets(key_path: str):
    creds = service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_col_a(svc, sid: str) -> list[str]:
    r = svc.spreadsheets().values().get(
        spreadsheetId=sid, range="Бриф!A1:A200", valueRenderOption="FORMATTED_VALUE",
    ).execute()
    return [(row[0] if row else "") for row in r.get("values", [])]


def find_marker_row(col_a: list[str], marker: str) -> int | None:
    for i, v in enumerate(col_a, 1):
        if v.strip().startswith(marker):
            return i
    return None


def next_free_row(col_a: list[str]) -> int:
    """Возвращает первый свободный (пустой) ряд после последнего заполненного."""
    last = 0
    for i, v in enumerate(col_a, 1):
        if v.strip():
            last = i
    return last + 2  # +1 пустая, +1 первая строка нового блока


def sheet_ids_map(svc, sid: str) -> dict[str, int]:
    meta = svc.spreadsheets().get(spreadsheetId=sid, includeGridData=False).execute()
    return {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta["sheets"]}


# ────────────────────────────────────────────────────────────────────────────
# Шаг 1. Лист «Ставки» — точечные правки

def update_rates_tab(svc, sid: str, dry: bool) -> None:
    print("→ Обновляю лист «Ставки»…")
    updates = [
        # Единая базовая ставка для всех ролей разработки
        {"range": "Ставки!B6", "values": [[RATES.hourly.base]]},
        {"range": "Ставки!D6", "values": [["Единая базовая ставка (актуал 2026)"]]},
        {"range": "Ставки!B9", "values": [[RATES.hourly.base]]},
        {"range": "Ставки!A9", "values": [["Ставка час техлида"]]},
        {"range": "Ставки!D9", "values": [["По базовой"]]},
        # Лицензии
        {"range": "Ставки!B13", "values": [[PLATFORMS["strapi"].license_cost]]},
        {"range": "Ставки!C13", "values": [[PLATFORMS["bitrix"].license_cost]]},
        {"range": "Ставки!E13", "values": [["Strapi-шаблон Belberry / Bitrix Малый бизнес (актуал 2026)"]]},
        # Контент
        {"range": "Ставки!B25", "values": [[RATES.content.text_product]]},
        {"range": "Ставки!D25", "values": [["Тоже через медкопирайтера, 5200 ₽/шт"]]},
        {"range": "Ставки!B26", "values": [[RATES.content.text_brief]]},
        {"range": "Ставки!D26", "values": [["Входит в работу медкопирайтера"]]},
    ]
    if dry:
        for u in updates:
            print(f"  [DRY] {u['range']} ← {u['values'][0][0]!r}")
    else:
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=sid, body={"valueInputOption": "USER_ENTERED", "data": updates},
        ).execute()
        print(f"  ✓ Обновлено {len(updates)} ячеек")

    # Проверим есть ли блок «ДОПОЛНИТЕЛЬНЫЕ РОЛИ»
    r = svc.spreadsheets().values().get(spreadsheetId=sid, range="Ставки!A30:A50",
                                        valueRenderOption="FORMATTED_VALUE").execute()
    has_extras = any("ДОПОЛНИТЕЛЬНЫЕ РОЛИ" in (row[0] if row else "") for row in r.get("values", []))
    if has_extras:
        print("  → Блок «ДОПОЛНИТЕЛЬНЫЕ РОЛИ» уже есть, пропускаю")
        return

    extra_rows = [
        [],
        ["ДОПОЛНИТЕЛЬНЫЕ РОЛИ (актуал 2026)"],
        ["Параметр", "Значение", "Ед.", "Комментарий"],
        ["Ставка контент-менеджера", RATES.hourly.content_manager, "₽/час", "Наполнение, перенос контента"],
        ["Ставка фотографа (внешний)", RATES.hourly.photographer_external, "₽/час", "Мед.фотосъёмка 4-8 часов = 40-80k"],
        [],
        ["ПРИМЕЧАНИЕ К СТАВКАМ"],
        [f"Все ставки разработки = {RATES.hourly.base} ₽/ч без НДС (актуал 2026, базовая для всех ролей)."],
        ["Исторические данные из 100 закрытых проектов 2023-2025: ставка росла +17-18% в год."],
        [f"Контент-менеджер (наполнение) = {RATES.hourly.content_manager} ₽/ч (отдельная пониженная ставка)."],
        [f"Медкопирайтер = {RATES.content.text_service} ₽/шт за услуговую страницу или статью блога."],
        ["Биографии врачей / лендинги / юр.страницы — клиент сам или контент-менеджер."],
    ]
    if dry:
        print(f"  [DRY] Append {len(extra_rows)} строк с дополнительными ролями")
    else:
        svc.spreadsheets().values().update(
            spreadsheetId=sid, range="Ставки!A35",
            valueInputOption="USER_ENTERED", body={"values": extra_rows},
        ).execute()
        print(f"  ✓ Добавлены {len(extra_rows)} строк с допролями")


# ────────────────────────────────────────────────────────────────────────────
# Шаг 2. Бриф — блоки 0a, 0b, 0c

def add_brief_block_0a(svc, sid: str, brief_sheet_id: int, dry: bool) -> int:
    """Дополнительные опции: перенос данных, фотосъёмка. Возвращает start_row блока."""
    col_a = read_col_a(svc, sid)
    if find_marker_row(col_a, MARKER_BLOCK_0A):
        print("  → Блок «0a. ДОПОЛНИТЕЛЬНО» уже есть, пропускаю")
        return find_marker_row(col_a, MARKER_BLOCK_0A) or 0

    start = next_free_row(col_a)
    rows = [
        [],
        [MARKER_BLOCK_0A + " (опции для расчёта)"],
        ["Перенос данных со старого сайта?", "Перенос фото врачей, услуг, статей из старого сайта",
         "Да/Нет", False, "", "✓", "✓", "✓"],
        ["Если да — сколько часов на перенос?", f"Контент-менеджер {RATES.hourly.content_manager} ₽/час",
         "Число", 30, "", "✓", "✓", "✓"],
        ["Нужна ли фотосъёмка?", f"Внешний фотограф {RATES.hourly.photographer_external} ₽/час",
         "Да/Нет", False, "", "✓", "✓", "✓"],
        ["Если да — сколько часов фотосъёмки?", "Типовая мед.съёмка 4-8 часов",
         "Число", 6, "", "✓", "✓", "✓"],
    ]
    if dry:
        print(f"  [DRY] Бриф A{start}: добавить блок 0a (6 строк)")
        return start + 1

    svc.spreadsheets().values().update(
        spreadsheetId=sid, range=f"Бриф!A{start}",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()
    # Чекбоксы для «Да/Нет»
    marker_row = start + 1  # маркер блока
    transfer_row = marker_row + 1
    photo_row = marker_row + 3
    svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [
        {"setDataValidation": {
            "range": {"sheetId": brief_sheet_id, "startRowIndex": transfer_row - 1, "endRowIndex": transfer_row,
                      "startColumnIndex": 3, "endColumnIndex": 4},
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True}}},
        {"setDataValidation": {
            "range": {"sheetId": brief_sheet_id, "startRowIndex": photo_row - 1, "endRowIndex": photo_row,
                      "startColumnIndex": 3, "endColumnIndex": 4},
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True}}},
    ]}).execute()
    print(f"  ✓ Блок 0a добавлен на строке {marker_row}")
    return marker_row


def add_brief_mis(svc, sid: str, brief_sheet_id: int, dry: bool) -> None:
    col_a = read_col_a(svc, sid)
    has_mis = any("Глубокая интеграция с МИС" in v for v in col_a)
    if has_mis:
        print("  → МИС-интеграция уже в Брифе, пропускаю")
        return
    start = next_free_row(col_a) - 1  # без пустой строки (она уже есть)
    rows = [
        ["Глубокая интеграция с МИС (двусторонняя)?",
         "Внимание: в Strapi не делаем; для Bitrix +60ч, Custom +100ч. Без документации API +30%",
         "Да/Нет", False, "", "✓", "✓", "✓"],
        ["Какая МИС используется?",
         "Есть документация API? — пиши 'есть' / 'нет' / название МИС",
         "Текст", "нет", "", "✓", "✓", "✓"],
    ]
    if dry:
        print(f"  [DRY] Бриф A{start}: добавить МИС-вопросы (2 строки)")
        return
    svc.spreadsheets().values().update(
        spreadsheetId=sid, range=f"Бриф!A{start}",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()
    svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [{
        "setDataValidation": {
            "range": {"sheetId": brief_sheet_id, "startRowIndex": start - 1, "endRowIndex": start,
                      "startColumnIndex": 3, "endColumnIndex": 4},
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True}}
    }]}).execute()
    print(f"  ✓ МИС-блок добавлен на строке {start}")


def add_brief_block_0b(svc, sid: str, dry: bool) -> None:
    col_a = read_col_a(svc, sid)
    if find_marker_row(col_a, MARKER_BLOCK_0B):
        print("  → Блок «0b. УСЛОВИЯ КП» уже есть, пропускаю")
        return
    start = next_free_row(col_a)
    rows = [
        [],
        [MARKER_BLOCK_0B],
        ["Срок подписания для скидки 5% (раб.дней)",
         "Если клиент подпишет в этот срок — даём скидку 5%",
         "Число", 7, "", "✓", "✓", "✓"],
    ]
    if dry:
        print(f"  [DRY] Бриф A{start}: добавить блок 0b")
        return
    svc.spreadsheets().values().update(
        spreadsheetId=sid, range=f"Бриф!A{start}",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()
    print(f"  ✓ Блок 0b добавлен на строке {start + 1}")


def add_brief_block_0c(svc, sid: str, brief_sheet_id: int, dry: bool) -> None:
    col_a = read_col_a(svc, sid)
    if find_marker_row(col_a, MARKER_BLOCK_0C):
        print("  → Блок «0c. ДОПОЛНИТЕЛЬНАЯ ФУНКЦИОНАЛЬНОСТЬ» уже есть, пропускаю")
        return
    start = next_free_row(col_a)
    rows = [
        [],
        [MARKER_BLOCK_0C],
        ["Продажа сертификатов / депозитов на сайте?",
         "Покупка подарочных сертификатов или пополнение депозита онлайн",
         "Да/Нет", False, "", "✓", "✓", "✓"],
        ["Личный кабинет пациента?",
         "История приёмов, документы, оплата онлайн. Требует Custom-разработки!",
         "Да/Нет", False, "", "✓", "✓", "✓"],
    ]
    if dry:
        print(f"  [DRY] Бриф A{start}: добавить блок 0c (4 строки)")
        return
    svc.spreadsheets().values().update(
        spreadsheetId=sid, range=f"Бриф!A{start}",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()
    cert_row = start + 2
    lk_row = start + 3
    svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [
        {"setDataValidation": {
            "range": {"sheetId": brief_sheet_id, "startRowIndex": cert_row - 1, "endRowIndex": cert_row,
                      "startColumnIndex": 3, "endColumnIndex": 4},
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True}}},
        {"setDataValidation": {
            "range": {"sheetId": brief_sheet_id, "startRowIndex": lk_row - 1, "endRowIndex": lk_row,
                      "startColumnIndex": 3, "endColumnIndex": 4},
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True}}},
    ]}).execute()
    print(f"  ✓ Блок 0c добавлен на строке {start + 1}")


# ────────────────────────────────────────────────────────────────────────────
# Main

def main() -> int:
    parser = argparse.ArgumentParser(description="Sync existing WD-Calculator with actual 2026 rates")
    parser.add_argument("--spreadsheet-id", default=SHEET_ID_V1)
    parser.add_argument("--key", default=os.environ.get("GOOGLE_SHEETS_KEY", DEFAULT_KEY))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not Path(args.key).is_file():
        print(f"ERROR: ключ не найден: {args.key}", file=sys.stderr)
        return 2

    try:
        svc = open_sheets(args.key)
        meta = svc.spreadsheets().get(spreadsheetId=args.spreadsheet_id, includeGridData=False).execute()
        print(f"OK: {meta['properties']['title']}")
    except HttpError as e:
        print(f"ERROR: нет доступа: {e}", file=sys.stderr)
        return 4

    sheet_ids = sheet_ids_map(svc, args.spreadsheet_id)
    brief_id = sheet_ids.get("Бриф")
    if brief_id is None:
        print("ERROR: лист «Бриф» не найден. Сначала запусти extend_v1.py", file=sys.stderr)
        return 5

    # Шаг 1
    update_rates_tab(svc, args.spreadsheet_id, args.dry_run)
    # Шаг 2 — Бриф
    print("\n→ Обновляю лист «Бриф»…")
    add_brief_block_0a(svc, args.spreadsheet_id, brief_id, args.dry_run)
    add_brief_mis(svc, args.spreadsheet_id, brief_id, args.dry_run)
    add_brief_block_0b(svc, args.spreadsheet_id, args.dry_run)
    add_brief_block_0c(svc, args.spreadsheet_id, brief_id, args.dry_run)

    # Шаг 3 (вставка строк в варианты) и шаг 4 (текст КП) — описаны в docstring модуля.
    # Они не идемпотентны (insertDimension добавляет строки каждый раз),
    # поэтому требуют ручной проверки. См. историю сессии 2026-05-20 для деталей.
    print("\n⚠️ Шаг 3 (вставка опций КМ/Фотограф/МИС/Сертификаты/ЛК в варианты)")
    print("   и Шаг 4 (формула даты в Текст КП) выполняются ВРУЧНУЮ либо")
    print("   через одноразовый скрипт. См. docstring этого модуля.")

    print(f"\n✅ Готово.")
    print(f"   https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
