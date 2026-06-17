#!/usr/bin/env python3
"""Расширяет существующий WD-Калькулятор Belberry (v1).

В отличие от build_calculator.py, который собирает Sheet с нуля, этот скрипт
ДОПИСЫВАЕТ к существующему калькулятору v1 (1AZ6I8Lz6Ppu5y2OLSG7Tw0p8X0pC3N1Fq3Yk8TG4RoY):

  - В конец листа «Бриф» — блок «0. Привязка к сделке Битрикс24»
    (ID сделки, авто-ссылка, менеджер, дата КП, срок отправки)
  - Новый лист «Текст КП» — Markdown по выбранному варианту (Strapi / Битрикс / Индивидуал)
    готовый к копи-пасте в карточку КП Битрикс24 (Pillar 1, 5)
  - Новый лист «Чек-лист 8 pillars» — 8 обязательных галочек до отправки
    (Pillar 3, 4, 6, 8)

Существующие листы (Бриф, Сравнение, Вариант 1-3, Калькулятор контента, Ставки)
НЕ ИЗМЕНЯЮТСЯ ниже строки 47 в Брифе.

Идемпотентен: повторный запуск перезаписывает «Текст КП» и «Чек-лист»,
а блок «Привязка к сделке» дописывается только если не найден маркер.

Запуск:
    python extend_v1.py [--spreadsheet-id <ID>] [--dry-run]
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
    from .rates import RATES, MANAGERS
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from rates import RATES, MANAGERS  # type: ignore


SHEET_ID_V1 = "1AZ6I8Lz6Ppu5y2OLSG7Tw0p8X0pC3N1Fq3Yk8TG4RoY"
DEFAULT_KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

DEAL_BINDING_MARKER = "━━━ 0. ПРИВЯЗКА К СДЕЛКЕ БИТРИКС24"
TAB_KP_TEXT = "Текст КП"
TAB_CHECKLIST = "Чек-лист 8 pillars"

VARIANTS = [
    "🟢 СТРАПИ",
    "🔵 БИТРИКС",
    "🟣 ИНДИВИДУАЛЬНЫЙ",
]
VARIANT_SHEET_MAP = {
    "🟢 СТРАПИ":         "Вариант 1 — Страпи",
    "🔵 БИТРИКС":        "Вариант 2 — Битрикс",
    "🟣 ИНДИВИДУАЛЬНЫЙ": "Вариант 3 — Индивидуал",
}


# ────────────────────────────────────────────────────────────────────────────
# Helpers


def open_sheets(key_path: str):
    creds = service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def get_meta(svc, sid: str) -> dict[str, Any]:
    return svc.spreadsheets().get(spreadsheetId=sid, includeGridData=False).execute()


def sheet_id_by_title(meta: dict[str, Any], title: str) -> int | None:
    for sh in meta.get("sheets", []):
        if sh["properties"]["title"] == title:
            return sh["properties"]["sheetId"]
    return None


def deal_binding_already_present(svc, sid: str) -> tuple[bool, int]:
    """Возвращает (есть_ли, первая_строка_блока_или_следующая_свободная)."""
    r = svc.spreadsheets().values().get(
        spreadsheetId=sid, range="Бриф!A1:A200", valueRenderOption="FORMATTED_VALUE",
    ).execute()
    values = r.get("values", [])
    last_filled = 0
    for i, row in enumerate(values, 1):
        if row and row[0]:
            last_filled = i
            if row[0].strip().startswith(DEAL_BINDING_MARKER):
                return True, i
    return False, last_filled + 2  # +1 пустая, +1 первая строка блока


# ────────────────────────────────────────────────────────────────────────────
# 1. Блок «Привязка к сделке» в конец Брифа


def build_deal_binding_rows(start_row: int) -> list[list[Any]]:
    """8 строк блока. start_row = строка где будет первая ячейка блока."""
    # row offsets от start_row:
    # 0: маркер-заголовок (объединённый), 1-7: поля
    rows: list[list[Any]] = [
        [DEAL_BINDING_MARKER, "Заполни ДО расчёта вариантов — обязательно (Pillar 7)"],
        ["ID сделки в Битрикс24", "", "Например 18538", "", "", "✓", "✓", "✓"],
        # Auto-ссылка — формула со ссылкой на ячейку D{start_row+1}
        [
            "Ссылка на сделку (auto)",
            "",  # пустое D
            "Формируется автоматически",
            f'=IF(D{start_row+1}="","",HYPERLINK("https://belberrycrm.bitrix24.ru/crm/deal/details/"&D{start_row+1}&"/","Открыть #"&D{start_row+1}))',
            "", "✓", "✓", "✓",
        ],
        ["Менеджер ответственный", "", "Выпадающий список", MANAGERS[0], "", "✓", "✓", "✓"],
        ["Какой вариант идёт в КП?", "Strapi / Битрикс / Индивидуал — выбирается на листе «Текст КП»", "Выпадающий", VARIANTS[0], "", "✓", "✓", "✓"],
        ["Дата подготовки КП", "", "Дата", "=TODAY()", "", "✓", "✓", "✓"],
        ["Срок отправки КП клиенту, раб.дней", f"По регламенту ≤ {RATES.budget.expected_send_business_days} раб.дней (Pillar 3)", "Число", RATES.budget.expected_send_business_days, "", "✓", "✓", "✓"],
        ["Срок действия КП, кал.дней", "", "Число", RATES.budget.quote_validity_days, "", "✓", "✓", "✓"],
    ]
    return rows


def write_deal_binding(svc, sid: str, start_row: int, rows: list[list[Any]]) -> None:
    svc.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"Бриф!A{start_row}",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()


def add_deal_binding_validations(svc, sid: str, brief_sheet_id: int, start_row: int) -> None:
    """Dropdown'ы для Менеджер и Вариант КП. start_row — строка маркера (1-based)."""
    # +3 = Менеджер (row start_row+3, col D = index 3)
    manager_row_zero = start_row + 3 - 1   # zero-based startRowIndex
    variant_row_zero = start_row + 4 - 1
    requests = [
        {"setDataValidation": {
            "range": {"sheetId": brief_sheet_id,
                      "startRowIndex": manager_row_zero, "endRowIndex": manager_row_zero + 1,
                      "startColumnIndex": 3, "endColumnIndex": 4},
            "rule": {
                "condition": {"type": "ONE_OF_LIST",
                              "values": [{"userEnteredValue": v} for v in MANAGERS]},
                "showCustomUi": True, "strict": True,
            },
        }},
        {"setDataValidation": {
            "range": {"sheetId": brief_sheet_id,
                      "startRowIndex": variant_row_zero, "endRowIndex": variant_row_zero + 1,
                      "startColumnIndex": 3, "endColumnIndex": 4},
            "rule": {
                "condition": {"type": "ONE_OF_LIST",
                              "values": [{"userEnteredValue": v} for v in VARIANTS]},
                "showCustomUi": True, "strict": True,
            },
        }},
    ]
    svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": requests}).execute()


# ────────────────────────────────────────────────────────────────────────────
# 2. Лист «Текст КП»


def kp_text_values(start_row: int) -> list[list[Any]]:
    """Markdown-сборка по выбранному варианту.

    start_row — строка маркера блока «Привязка к сделке» на листе Бриф.
    Конкретные адреса полей привязки:
      D{start_row+1} — ID сделки
      D{start_row+3} — Менеджер
      D{start_row+4} — Какой вариант идёт в КП
      D{start_row+5} — Дата КП
      D{start_row+6} — Срок отправки, раб.дней
      D{start_row+7} — Срок действия, кал.дней

    Лист «Текст КП»: A2 — большая ячейка с формулой Markdown.
    """
    id_cell        = f"'Бриф'!D{start_row+1}"
    manager_cell   = f"'Бриф'!D{start_row+3}"
    variant_cell   = f"'Бриф'!D{start_row+4}"
    date_cell      = f"'Бриф'!D{start_row+5}"
    valid_days_cell= f"'Бриф'!D{start_row+7}"

    client_cell = "'Бриф'!D6"        # «Бренд / название клиента»
    contact_cell = "'Бриф'!D7"       # «Контактное лицо…»
    budget_cell = "'Бриф'!D8"
    sphere_cell = "'Бриф'!D10"
    pain_cell = "'Бриф'!D12"         # «Почему обращаются за новым сайтом»

    # Целевые ячейки в листах вариантов — одинаковые во всех трёх (F49, F44, F47, F48, F53, F54)
    # Используем INDIRECT с подстановкой имени листа варианта
    def vcell(addr: str) -> str:
        """Подставляет адрес ячейки в выбранный лист варианта через INDIRECT.

        В Sheets INDIRECT с именем листа с пробелами требует кавычки. Имена
        листов жёстко зашиты в Бриф — варианты идентифицируются по эмодзи.
        """
        return f'INDIRECT("\'"&VLOOKUP({variant_cell},{{' + \
               '"🟢 СТРАПИ","Вариант 1 — Страпи";' + \
               '"🔵 БИТРИКС","Вариант 2 — Битрикс";' + \
               '"🟣 ИНДИВИДУАЛЬНЫЙ","Вариант 3 — Индивидуал"' + \
               f'}},2,FALSE)&"\'!{addr}")'

    total_cell    = vcell("F49")
    subtotal_cell = vcell("F44")
    discounted_cell = vcell("F47")
    vat_cell      = vcell("F48")
    status_cell   = vcell("F54")
    deviation_cell= vcell("F53")

    nl = "CHAR(10)"

    lines = [
        '"# Коммерческое предложение"',
        f'"## "&{client_cell}&" — Веб-разработка"',
        '""',
        f'"**Подготовлено:** Belberry · "&TEXT({date_cell},"dd.mm.yyyy")',
        f'"**Менеджер:** "&{manager_cell}',
        f'"**Сделка:** "&IF({id_cell}="","—","#"&{id_cell})',
        f'"**Контакт:** "&{contact_cell}',
        '""',
        '"## 1. Задача"',
        f'{pain_cell}',
        '""',
        '"## 2. Что предлагаем"',
        f'"**Вариант:** "&{variant_cell}',
        f'"**Сфера:** "&{sphere_cell}',
        '"Состав работ — см. детальную смету в Google Sheets (ссылка ниже)."',
        '""',
        '"## 3. Стоимость"',
        '"| Параметр | ₽ |"',
        '"|---|---|"',
        f'"| Работы без скидок и НДС | "&TEXT({subtotal_cell},"#,##0")&" |"',
        f'"| Со скидками | "&TEXT({discounted_cell},"#,##0")&" |"',
        f'"| НДС | "&TEXT({vat_cell},"#,##0")&" |"',
        f'"| **К ОПЛАТЕ** | **"&TEXT({total_cell},"#,##0")&" ₽** |"',
        '""',
        f'"**Бюджет клиента:** "&TEXT({budget_cell},"#,##0")&" ₽"',
        f'"**Соответствие бюджету:** "&{status_cell}',
        f'"**Отклонение:** "&TEXT({deviation_cell},"0%")',
        '""',
        '"## 4. Условия"',
        f'"- Срок действия КП: "&{valid_days_cell}&" дней с даты подготовки"',
        '"- Скидка 5% при подписании договора в течение этого срока"',
        '"- НДС 5% (УСН)"',
        '"- Оплата: 50% аванс / 30% после демо / 20% запуск"',
        '""',
        '"## 5. За что вы платите Belberry"',
        '"- **Медицинский фокус:** мы делаем сайты для медицины и сложных b2b (500+ кейсов)"',
        '"- **Медкопирайтер в команде:** врач-копирайтер пишет лично, не передаём фрилансерам"',
        '"- **SEO с первого дня:** структура + meta + sitemap встроены в шаблон"',
        '"- **Bitrix24-интеграция:** заявки попадают в вашу CRM с правильными UTM — 0 ₽ доп."',
        '"- **Сопровождение 3 мес после запуска:** включено в стоимость"',
        '""',
        '"## 6. Следующий шаг"',
        f'"Прошу подтвердить готовность подписать договор до "&TEXT({date_cell}+{valid_days_cell},"dd.mm.yyyy")&" для активации скидки за оперативность."',
        '""',
        '"---"',
        '"_Belberry · медицинский маркетинг_"',
    ]

    formula = "=" + ("&" + nl + "&").join(lines)

    return [
        ["ТЕКСТ КП — копируй ячейку A2 целиком в карточку КП Битрикс24"],
        [formula],
        [],
        ["ИНСТРУКЦИЯ"],
        ["1.", f"На листе «Бриф» в поле «Какой вариант идёт в КП?» (D{start_row+4}) выбери Strapi / Битрикс / Индивидуал"],
        ["2.", "Скопируй A2 (одна ячейка, текст с переносами)"],
        ["3.", "В Битрикс24 → твоя сделка → «Создать смарт-процесс» → «КП»"],
        ["4.", "В карточку КП в поле «Описание» вставь скопированный текст"],
        ["5.", "Заполни статус КП = «Готово к отправке»"],
        ["6.", "Отправь клиенту по тому же каналу, где он привык общаться"],
        ["7.", "В сделке Битрикс24 поставь OPPORTUNITY = «К ОПЛАТЕ» из выбранного варианта"],
        [],
        ["⚠️ БЕЗ КАРТОЧКИ КП В СИСТЕМЕ — НЕ ОТПРАВЛЯТЬ КЛИЕНТУ (Pillar 1)"],
        [],
        ["Ссылка на калькулятор (для клиента):",
         f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{SHEET_ID_V1}/edit","Открыть калькулятор")'],
    ]


# ────────────────────────────────────────────────────────────────────────────
# 3. Лист «Чек-лист 8 pillars»


def checklist_values() -> list[list[Any]]:
    items = [
        ("1. Карточка КП заведена в Битрикс24 (Pillar 1)",
            "Без карточки — РОП не видит. КП мимо CRM = отвал."),
        ("2. Сумма проставлена в OPPORTUNITY сделки (Pillar 7)",
            "Сделка не подсвечивается руководству без суммы."),
        ("3. Превышение бюджета < 20% ИЛИ есть согласование РОП (Pillar 2)",
            "Проверь статус выбранного варианта. Если 🔴 — согласуй до отправки."),
        ("4. Только ОДНО КП на эту сделку (Pillar 4)",
            "Дополнительные услуги (SMM, контекст, ORM) = отдельные сделки."),
        ("5. КП будет отправлено клиенту в течение 3 раб.дней (Pillar 3)",
            "Если лежит дольше — клиент остывает, конкурент успевает."),
        ("6. Готов скрипт ответа на «А чем лучше бесплатного шаблона?» (Pillar 5)",
            "См. лист «Текст КП» раздел 5 «За что вы платите Belberry»."),
        ("7. Назначен «следующий шаг» с конкретной датой (Pillar 6)",
            "Первый звонок-проверка в день отправки или максимум на следующий рабочий."),
        ("8. После негативного сигнала клиента готов план Б (Pillar 8)",
            "Дата автоматического возврата / альтернативный канал."),
    ]
    rows: list[list[Any]] = [
        ["ЧЕК-ЛИСТ 8 ПУНКТОВ — Pillars of KP Success"],
        ["Все 8 галочек должны быть TRUE до отправки клиенту."],
        ["См. insights/8-pillars-of-kp-failure в Obsidian vault."],
        [],
        ["#", "Пункт", "Готово?", "Комментарий"],
    ]
    first = len(rows) + 1
    for title, comment in items:
        rows.append(["", title, False, comment])
    last = len(rows)
    rows.extend([
        [],
        ["ИТОГ", f'=COUNTIF(C{first}:C{last},TRUE)&" из {len(items)}"', "", ""],
        ["БАННЕР",
            f'=IF(COUNTIF(C{first}:C{last},TRUE)={len(items)}, "✅ КП ГОТОВО К ОТПРАВКЕ", "❌ КП НЕ ГОТОВО — закрой все галочки")',
            "", ""],
    ])
    return rows


# ────────────────────────────────────────────────────────────────────────────
# Apply


def ensure_tab(svc, sid: str, meta: dict[str, Any], title: str, rows: int = 60, cols: int = 8) -> int:
    """Возвращает sheetId. Создаёт лист если нет."""
    existing = sheet_id_by_title(meta, title)
    if existing is not None:
        return existing
    r = svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [
        {"addSheet": {"properties": {"title": title, "gridProperties": {"rowCount": rows, "columnCount": cols}}}}
    ]}).execute()
    return r["replies"][0]["addSheet"]["properties"]["sheetId"]


def write_tab(svc, sid: str, title: str, values: list[list[Any]]) -> None:
    svc.spreadsheets().values().clear(spreadsheetId=sid, range=f"'{title}'!A1:Z200", body={}).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"'{title}'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def format_header_and_freeze(svc, sid: str, sheet_id: int) -> None:
    svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontSize": 12},
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
            }},
            "fields": "userEnteredFormat(textFormat,backgroundColor)",
        }},
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }},
        {"autoResizeDimensions": {
            "dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS",
                           "startIndex": 0, "endIndex": 8},
        }},
    ]}).execute()


def add_checkboxes(svc, sid: str, sheet_id: int, start_row: int, end_row: int, col: int) -> None:
    """Чекбоксы для диапазона строк в колонке (1-based row, 1-based col)."""
    svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [{
        "setDataValidation": {
            "range": {"sheetId": sheet_id,
                      "startRowIndex": start_row - 1, "endRowIndex": end_row,
                      "startColumnIndex": col - 1, "endColumnIndex": col},
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True},
        }
    }]}).execute()


# ────────────────────────────────────────────────────────────────────────────
# Main


def main() -> int:
    parser = argparse.ArgumentParser(description="Extend existing WD-Calculator v1")
    parser.add_argument("--spreadsheet-id", default=SHEET_ID_V1, help=f"По умолчанию: {SHEET_ID_V1}")
    parser.add_argument("--key", default=os.environ.get("GOOGLE_SHEETS_KEY", DEFAULT_KEY))
    parser.add_argument("--dry-run", action="store_true", help="Только показать что будет сделано")
    parser.add_argument("--check-only", action="store_true", help="Только проверить доступ")
    parser.add_argument("--skip-deal-binding", action="store_true", help="Не дописывать блок «Привязка к сделке» в Бриф")
    args = parser.parse_args()

    if not Path(args.key).is_file():
        print(f"ERROR: ключ не найден: {args.key}", file=sys.stderr)
        return 2

    try:
        svc = open_sheets(args.key)
        meta = get_meta(svc, args.spreadsheet_id)
    except HttpError as e:
        print(f"ERROR: нет доступа к Sheet {args.spreadsheet_id}: {e}", file=sys.stderr)
        return 4

    print(f"OK access: {meta['properties']['title']}")
    existing_tabs = [sh['properties']['title'] for sh in meta['sheets']]
    print(f"Existing tabs: {existing_tabs}")

    if args.check_only:
        return 0

    # Шаг 1. Бриф — блок «Привязка к сделке»
    if not args.skip_deal_binding:
        present, start_row = deal_binding_already_present(svc, args.spreadsheet_id)
        if present:
            print(f"→ Блок «Привязка к сделке» уже есть на строке {start_row}. Пропускаю дописывание (повторный запуск).")
        else:
            print(f"→ Дописываю блок «Привязка к сделке» в Бриф со строки {start_row}…")
            if args.dry_run:
                for i, r in enumerate(build_deal_binding_rows(start_row)):
                    print(f"   Бриф!A{start_row+i}: {r}")
            else:
                rows = build_deal_binding_rows(start_row)
                write_deal_binding(svc, args.spreadsheet_id, start_row, rows)
                # Refresh meta to get brief sheet id (already known but cleaner)
                brief_sheet_id = sheet_id_by_title(meta, "Бриф")
                if brief_sheet_id is not None:
                    add_deal_binding_validations(svc, args.spreadsheet_id, brief_sheet_id, start_row)
                print(f"   ✓ Записано {len(rows)} строк + dropdown'ы")

    # После записи Брифа — определим start_row блока для KP-Text
    if args.dry_run and not args.skip_deal_binding:
        # В dry-run используем расчётный start_row из шага выше
        pass
    present, start_row = deal_binding_already_present(svc, args.spreadsheet_id)

    # Шаг 2. Лист «Текст КП»
    print(f"→ Заливаю «{TAB_KP_TEXT}» (привязка к Бриф!A{start_row}, варианту D{start_row+4})…")
    kp_values = kp_text_values(start_row)
    if args.dry_run:
        for i, r in enumerate(kp_values[:5], 1):
            print(f"   {i}: {r}")
        print(f"   ... +{len(kp_values)-5} строк")
    else:
        kp_id = ensure_tab(svc, args.spreadsheet_id, meta, TAB_KP_TEXT, rows=20, cols=4)
        write_tab(svc, args.spreadsheet_id, TAB_KP_TEXT, kp_values)
        format_header_and_freeze(svc, args.spreadsheet_id, kp_id)
        print(f"   ✓ Создан/обновлён лист «{TAB_KP_TEXT}»")

    # Шаг 3. Лист «Чек-лист 8 pillars»
    print(f"→ Заливаю «{TAB_CHECKLIST}»…")
    check_values = checklist_values()
    if args.dry_run:
        for i, r in enumerate(check_values[:6], 1):
            print(f"   {i}: {r}")
        print(f"   ... +{len(check_values)-6} строк")
    else:
        check_id = ensure_tab(svc, args.spreadsheet_id, meta, TAB_CHECKLIST, rows=30, cols=4)
        write_tab(svc, args.spreadsheet_id, TAB_CHECKLIST, check_values)
        format_header_and_freeze(svc, args.spreadsheet_id, check_id)
        # Чекбоксы: строки 6-13 (8 пунктов), колонка C
        add_checkboxes(svc, args.spreadsheet_id, check_id, start_row=6, end_row=13, col=3)
        print(f"   ✓ Создан/обновлён лист «{TAB_CHECKLIST}»")

    print(f"\n✅ Готово.")
    print(f"   https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
