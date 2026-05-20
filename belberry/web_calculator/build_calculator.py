#!/usr/bin/env python3
"""Билдер калькулятора веб-разработки Belberry v2.

Заполняет Google Sheet (SPREADSHEET_ID) шестью листами:

    01 Старт           — карточка клиента + сделки (закрывает Pillar 7)
    02 Конструктор     — выбор платформы, страниц, интеграций, SEO, контента
    03 Ставки          — single source of truth для всех цифр
    04 Смета           — авто-расчёт по этапам + светофор бюджета (Pillar 2)
    05 Текст КП        — Markdown для копи-пасты в карточку КП в Битрикс24 (Pillar 1, 5)
    06 Чек-лист        — 8 обязательных пунктов до отправки (Pillar 3, 4, 6, 8)

Перед запуском:
    1. Создай пустой Sheet в своём Google Drive
    2. Расшарь его как editor для сервис-аккаунта:
       finance-director-sheets@finance-director-sheets.iam.gserviceaccount.com
    3. Скопируй ID из URL (между /d/ и /edit)
    4. Запусти:
       python build_calculator.py --spreadsheet-id <ID>

Опции:
    --dry-run            — вывести структуру в stdout без записи в Sheet
    --check-only         — проверить доступ к Sheet и выйти
    --keep-existing-tabs — не удалять существующие листы
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# rates можно импортировать как модуль (если запускают как пакет)
# или как соседний файл (если запускают напрямую)
try:
    from .rates import (
        RATES, PLATFORMS, PAGE_TYPES, INTEGRATIONS, SEO_LEVELS,
        PROJECT_TYPES, MANAGERS, LEAD_SOURCES, SPHERES,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from rates import (  # type: ignore
        RATES, PLATFORMS, PAGE_TYPES, INTEGRATIONS, SEO_LEVELS,
        PROJECT_TYPES, MANAGERS, LEAD_SOURCES, SPHERES,
    )

# ────────────────────────────────────────────────────────────────────────────
# Config

DEFAULT_KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

# Имена листов и их sheetId-плейсхолдеры (реальные ID будут получены после создания)
TABS = [
    "01 Старт",
    "02 Конструктор",
    "03 Ставки",
    "04 Смета",
    "05 Текст КП",
    "06 Чек-лист 8 pillars",
]


# ────────────────────────────────────────────────────────────────────────────
# Helpers


def open_clients(key_path: str):
    creds = service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)
    return (
        build("sheets", "v4", credentials=creds, cache_discovery=False),
        build("drive", "v3", credentials=creds, cache_discovery=False),
    )


def get_sheet_meta(sheets, sid: str) -> dict[str, Any]:
    return sheets.spreadsheets().get(spreadsheetId=sid, includeGridData=False).execute()


def sheet_id_by_title(meta: dict[str, Any], title: str) -> int | None:
    for sh in meta.get("sheets", []):
        if sh["properties"]["title"] == title:
            return sh["properties"]["sheetId"]
    return None


# ────────────────────────────────────────────────────────────────────────────
# Content builders для каждого листа


def tab_start_values() -> list[list[Any]]:
    """Лист «01 Старт» — карточка клиента/сделки."""
    return [
        ["БРИФ ДЛЯ КП — ВЕБ-РАЗРАБОТКА BELBERRY"],
        ["Один калькулятор = одна сделка. Не используй для нескольких КП параллельно (Pillar 4)."],
        [],
        ["Параметр", "Значение", "Подсказка"],
        ["📌 ID сделки в Битрикс24", "", "Например: 18538. Без этого карточка КП не свяжется со сделкой."],
        ["📌 Ссылка на сделку (auto)", '=IF(B5="","",HYPERLINK("https://belberrycrm.bitrix24.ru/crm/deal/details/"&B5&"/","Открыть сделку #"&B5))', "Формируется автоматически"],
        ["📌 Менеджер ответственный", MANAGERS[0], f"Выпадающий список из {len(MANAGERS)} вариантов"],
        [],
        ["── КЛИЕНТ ──"],
        ["Клиент (юр.лицо)", "", "ООО/ИП и т.п."],
        ["Бренд / название", "", "Под которым известен на рынке"],
        ["Домен текущего сайта", "", "Если есть"],
        ["Сфера", SPHERES[0], f"{len(SPHERES)} вариантов"],
        ["Источник лида", LEAD_SOURCES[0], ""],
        [],
        ["── ЛПР ──"],
        ["ФИО", "", "Главный, кто подписывает счёт"],
        ["Должность", "", ""],
        ["Телефон", "", ""],
        ["Email", "", ""],
        [],
        ["── БЮДЖЕТ И СРОКИ ──"],
        ["📌 Заявленный бюджет клиента, ₽", 1_500_000, "Pillar 7: без этого нельзя считать"],
        ["Сроки запуска (дедлайн клиента)", "", "Когда сайт должен быть готов"],
        ["Дата подготовки КП", "=TODAY()", "Авто"],
        ["Срок отправки КП клиенту, раб.дней", RATES.budget.expected_send_business_days, f"По регламенту ≤ {RATES.budget.expected_send_business_days} раб.дней (Pillar 3)"],
        ["Срок действия КП, кал.дней", RATES.budget.quote_validity_days, ""],
        [],
        ["── ЗАДАЧА ──"],
        ["Главная боль клиента (зачем новый сайт?)", "", ""],
        ["Целевая аудитория", "", "Возраст, доход, боль"],
        ["Конкуренты (3-5 URL)", "", "На кого равняться/чем отличаться"],
        ["Примеры понравившихся сайтов", "", "Помогает понять вкус"],
        ["Логотип / гайдлайн / брендбук", "Нет", "Есть/Нет — экономия часов на айдентике"],
        [],
        ["⚠️ Заполни поля помеченные 📌 до перехода на лист «02 Конструктор»"],
    ]


def tab_constructor_values() -> list[list[Any]]:
    """Лист «02 Конструктор» — все опции продукта."""
    rows: list[list[Any]] = [
        ["КОНСТРУКТОР ПРОЕКТА"],
        ["Заполняй колонку B. Часы и формулы пересчитываются автоматически."],
        [],
        ["── A. ПЛАТФОРМА ──"],
        ["Платформа", list(PLATFORMS.values())[0].title, "Выпадающий из 5 вариантов"],
        ["Тип проекта", PROJECT_TYPES[0][1], f"{len(PROJECT_TYPES)} вариантов"],
        [],
        ["── B. СТРАНИЦЫ И БЛОКИ ──"],
        ["Тип страницы", "Кол-во", "Часов/шт", "Итого часов", "Комментарий"],
    ]

    page_block_first = len(rows) + 1
    for p in PAGE_TYPES:
        row_idx = len(rows) + 1
        rows.append([
            p.title,
            p.default_count,
            p.hours_per_unit,
            f"=B{row_idx}*C{row_idx}",
            "",
        ])
    page_block_last = len(rows)
    rows.append([
        "ВСЕГО часов на страницы", "", "",
        f"=SUM(D{page_block_first}:D{page_block_last})", "",
    ])
    pages_total_row = len(rows)

    rows.extend([
        [],
        ["── C. ИНТЕГРАЦИИ ──"],
        ["Интеграция", "Брать (TRUE/FALSE)", "Часов", "Итого часов", "Комментарий"],
    ])
    integ_first = len(rows) + 1
    for ig in INTEGRATIONS:
        row_idx = len(rows) + 1
        rows.append([
            ig.title,
            ig.default,
            ig.hours,
            f'=IF(B{row_idx}=TRUE,C{row_idx},0)',
            ig.note,
        ])
    integ_last = len(rows)
    rows.append([
        "ВСЕГО часов на интеграции", "", "",
        f"=SUM(D{integ_first}:D{integ_last})", "",
    ])
    integ_total_row = len(rows)

    rows.extend([
        [],
        ["── D. SEO ──"],
        ["Уровень SEO", "Часов", "Комментарий"],
    ])
    seo_first = len(rows) + 1
    for s in SEO_LEVELS:
        rows.append([s.title, s.hours, s.note])
    seo_last = len(rows)

    rows.extend([
        ["", "", ""],
        ["Выбран уровень SEO", SEO_LEVELS[1].title, "Выпадающий"],
        ["Часов на SEO (auto)", f'=VLOOKUP(B{len(rows)+1},A{seo_first}:B{seo_last},2,FALSE)', "Формула подтягивает из таблицы выше"],
    ])
    # ⬆️ formula references current row before it's appended; fix below
    seo_choice_row = len(rows) - 1
    seo_hours_row = len(rows)
    # Корректируем формулу VLOOKUP — индекс на seo_choice_row
    rows[seo_hours_row - 1][1] = f'=IFERROR(VLOOKUP(B{seo_choice_row},A{seo_first}:B{seo_last},2,FALSE),0)'

    rows.extend([
        [],
        ["── E. КОНТЕНТ ──"],
        ["Тип текста", "Кол-во", "Цена/шт, ₽", "Итого, ₽", "Кто пишет"],
    ])
    content_first = len(rows) + 1
    content_items = [
        ("Тексты страниц услуг",            RATES.content.text_service,  "Belberry"),
        ("Тексты карточек товаров",         RATES.content.text_product,  "Belberry"),
        ("Статьи блога (3000+ зн.)",        RATES.content.text_blog,     "Belberry"),
        ("ТЗ копирайту",                    RATES.content.text_brief,    "Belberry"),
        ("Блок текста для лендинга",        RATES.content.text_landing_block, "Belberry"),
    ]
    for title, price, by in content_items:
        row_idx = len(rows) + 1
        rows.append([title, 0, price, f"=B{row_idx}*C{row_idx}", by])
    content_last = len(rows)
    rows.append([
        "ВСЕГО за контент, ₽", "", "",
        f"=SUM(D{content_first}:D{content_last})", "",
    ])
    content_total_row = len(rows)

    rows.extend([
        [],
        ["── F. БУФЕРЫ ──"],
        ["Запас часов на правки клиента (% от часов)", f"{int(RATES.buffer.revisions_pct*100)}%", "По умолчанию 15%"],
        ["Запас на риски (% от итога)", f"{int(RATES.buffer.risk_pct_default*100)}%", "По умолчанию 10%"],
        [],
        ["── G. УСЛОВИЯ КП ──"],
        ["Скидка за копирайт «нами» (TRUE/FALSE)", True, f"-{int(RATES.discounts.copyright_inhouse*100)}% если копирайт делаем мы"],
        ["Скидка за оперативность (TRUE/FALSE)", True, f"-{int(RATES.discounts.speed_signing*100)}% если договор за {RATES.budget.quote_validity_days} дней"],
        ["НДС включён (TRUE/FALSE)", True, f"+{int(RATES.discounts.vat*100)}% (УСН)"],
        [],
        ["── H. УКАЗАТЕЛИ ДЛЯ ФОРМУЛ ──"],
        ["pages_hours_row",     pages_total_row,   "Не трогать — используется в '04 Смета'"],
        ["integ_hours_row",     integ_total_row,   "Не трогать"],
        ["seo_hours_row",       seo_hours_row,     "Не трогать"],
        ["content_total_row",   content_total_row, "Не трогать"],
    ])

    return rows


def tab_rates_values() -> list[list[Any]]:
    """Лист «03 Ставки» — single source of truth для всех цифр."""
    rows: list[list[Any]] = [
        ["СТАВКИ И НОРМАТИВЫ — Belberry WD"],
        ["Один источник правды. Меняешь здесь — пересчёт по всем листам."],
        [],
        ["── ЧАСОВЫЕ СТАВКИ ──"],
        ["Параметр", "Значение", "Ед.", "Комментарий"],
        ["Ставка час (база)",              RATES.hourly.base,            "₽/ч", "Backend, Frontend, QA"],
        ["Ставка час (дизайн премиум)",    RATES.hourly.design_premium,  "₽/ч", "Авторский дизайн"],
        ["Ставка час (техлид)",            RATES.hourly.tech_lead,       "₽/ч", "Архитектура, ревью"],
        ["Ставка час (PM)",                RATES.hourly.project_manager, "₽/ч", "Координация"],
        [],
        ["── ПЛАТФОРМЫ И ИХ ТРУДОЗАТРАТЫ ──"],
        ["Платформа", "Лицензия, ₽", "Discovery, ч", "Прототип, ч", "Дизайн доп, ч", "Бэк, ч", "Фронт, ч", "QA, ч", "Launch, ч"],
    ]
    for p in PLATFORMS.values():
        rows.append([
            p.title, p.license_cost,
            p.hours_discovery, p.hours_prototype, p.hours_design_extra,
            p.hours_backend, p.hours_frontend, p.hours_qa, p.hours_launch,
        ])

    rows.extend([
        [],
        ["── КОНТЕНТ ──"],
        ["Параметр", "Значение, ₽/шт"],
        ["Текст страницы услуги",  RATES.content.text_service],
        ["Текст карточки товара",  RATES.content.text_product],
        ["Статья блога",           RATES.content.text_blog],
        ["ТЗ копирайту",           RATES.content.text_brief],
        ["Блок лендинга",          RATES.content.text_landing_block],
        [],
        ["── СКИДКИ И НДС ──"],
        ["Скидка за копирайт «нами»",    f"{int(RATES.discounts.copyright_inhouse*100)}%"],
        ["Скидка за оперативность",      f"{int(RATES.discounts.speed_signing*100)}%"],
        ["НДС (УСН)",                    f"{int(RATES.discounts.vat*100)}%"],
        [],
        ["── ПРАВИЛА БЮДЖЕТА ──"],
        ["Допустимое превышение бюджета", f"{int(RATES.budget.over_budget_threshold*100)}%", "", "Выше — требуется согласование РОП (Pillar 2)"],
        ["Срок действия КП",              f"{RATES.budget.quote_validity_days} дн", "", ""],
        ["Срок отправки клиенту",         f"≤ {RATES.budget.expected_send_business_days} раб.дн", "", "Pillar 3"],
    ])
    return rows


# Ключевые адреса на листе Смета. Заполняются в tab_estimate_values и читаются tab_kp_text_values.
_ESTIMATE_ADDRS: dict[str, str] = {}


def tab_estimate_values() -> list[list[Any]]:
    """Лист «04 Смета» — авто-расчёт.

    Тянет данные:
      - '01 Старт'!B22       (бюджет клиента)
      - '02 Конструктор'!B5  (выбранная платформа)
      - '02 Конструктор'!D…  (часы по блокам через INDIRECT)
      - '03 Ставки'          (значения)
    """
    rate_first_row_of_platforms = 13   # шапка "Платформа..." на строке 12, данные с 13
    rate_last_row_of_platforms = rate_first_row_of_platforms + len(PLATFORMS) - 1
    plat_lookup = f"'03 Ставки'!A{rate_first_row_of_platforms}:I{rate_last_row_of_platforms}"

    base = "'03 Ставки'!B6"
    design_premium = "'03 Ставки'!B7"

    rows: list[list[Any]] = [
        ["СМЕТА"],
        ["Все формулы тянут данные из '01 Старт', '02 Конструктор', '03 Ставки'."],
        [],
        ["Параметр", "Значение", "Источник / комментарий"],
        ["Клиент",           "='01 Старт'!B10",  ""],                       # row 5
        ["Бренд",            "='01 Старт'!B11",  ""],                       # row 6
        ["Платформа",        "='02 Конструктор'!B5", ""],                   # row 7  <-- VLOOKUP key
        ["Тип проекта",      "='02 Конструктор'!B6", ""],                   # row 8
        ["Дата КП",          "='01 Старт'!B24",  ""],                       # row 9
        [],
        ["── ЭТАПЫ И ЧАСЫ ──"],
        ["Этап", "Часы", "Ставка, ₽/ч", "Стоимость, ₽", "Источник"],
    ]
    platform_cell = "B7"  # на этом листе

    # Этапы из платформы (lookup по выбранной)
    stages = [
        ("Discovery",            3, base,           "VLOOKUP колонка 3"),
        ("Прототип",             4, base,           "VLOOKUP колонка 4"),
        ("Дизайн (доп. часы)",   5, design_premium, "VLOOKUP колонка 5, ставка premium"),
        ("Бэкенд",               6, base,           "VLOOKUP колонка 6"),
        ("Фронтенд",             7, base,           "VLOOKUP колонка 7"),
        ("QA",                   8, base,           "VLOOKUP колонка 8"),
        ("Launch",               9, base,           "VLOOKUP колонка 9"),
    ]
    stage_first = len(rows) + 1
    stage_addrs: dict[str, int] = {}
    for title, col_idx, rate_cell, src in stages:
        row_idx = len(rows) + 1
        hours_formula = f'=IFERROR(VLOOKUP({platform_cell},{plat_lookup},{col_idx},FALSE),0)'
        cost_formula = f"=B{row_idx}*C{row_idx}"
        rows.append([title, hours_formula, f"={rate_cell}", cost_formula, src])
        stage_addrs[title] = row_idx

    # Дополнительные этапы из листа Конструктор — строим построчно (важно: row_idx считаем после append)
    extras = [
        ("Страницы и блоки",  'INDIRECT("\'02 Конструктор\'!D" & VLOOKUP("pages_hours_row", \'02 Конструктор\'!A:B, 2, FALSE))', base, "auto"),
        ("Интеграции",        'INDIRECT("\'02 Конструктор\'!D" & VLOOKUP("integ_hours_row", \'02 Конструктор\'!A:B, 2, FALSE))', base, "auto"),
        ("SEO",               'INDIRECT("\'02 Конструктор\'!B" & VLOOKUP("seo_hours_row", \'02 Конструктор\'!A:B, 2, FALSE))', base, "auto"),
    ]
    for title, hours_formula_raw, rate_cell, src in extras:
        row_idx = len(rows) + 1
        rows.append([
            title,
            f"={hours_formula_raw}",
            f"={rate_cell}",
            f"=B{row_idx}*C{row_idx}",
            src,
        ])
        stage_addrs[title] = row_idx
    stage_last = len(rows)

    rows.append(["── ИТОГО ЧАСОВ ──", f"=SUM(B{stage_first}:B{stage_last})", "", "", ""])
    total_hours_row = len(rows)

    # Стоимости
    rows.append([])
    rows.append(["── СТОИМОСТЬ (РАСЧЁТ) ──"])
    rows.append(["Параметр", "Значение, ₽", "Комментарий"])

    rows.append(["Работы (сумма этапов)", f"=SUM(D{stage_first}:D{stage_last})", "Auto"])
    labor_row = len(rows)

    rows.append(["Лицензия платформы (фикс)", f'=IFERROR(VLOOKUP({platform_cell},{plat_lookup},2,FALSE),0)', "Auto"])
    license_row = len(rows)

    rows.append(["Контент (всего)", '=INDIRECT("\'02 Конструктор\'!D" & VLOOKUP("content_total_row", \'02 Конструктор\'!A:B, 2, FALSE))', "Auto"])
    content_row = len(rows)

    rows.append(["Запас на правки (% от работ)", f"=B{labor_row}*0.15", "По умолчанию 15%"])
    revisions_row = len(rows)

    rows.append(["Запас на риски (% от работ)", f"=B{labor_row}*0.10", "По умолчанию 10%"])
    risks_row = len(rows)

    rows.append([])
    rows.append(["ИТОГО без скидок и НДС", f"=B{labor_row}+B{license_row}+B{content_row}+B{revisions_row}+B{risks_row}", "Auto"])
    subtotal_row = len(rows)

    rows.append([])
    rows.append(["── СКИДКИ И НАЛОГИ ──"])

    rows.append(["Скидка за копирайт «нами»",
                 f'=IF(\'02 Конструктор\'!B{find_constructor_row_index("Скидка за копирайт")}=TRUE,-B{subtotal_row}*0.10,0)',
                 "TRUE/FALSE на листе Конструктор"])
    discount_copyright_row = len(rows)

    rows.append(["Скидка за оперативность",
                 f'=IF(\'02 Конструктор\'!B{find_constructor_row_index("Скидка за оперативность")}=TRUE,-B{subtotal_row}*0.05,0)',
                 "TRUE/FALSE"])
    discount_speed_row = len(rows)

    rows.append(["ИТОГО после скидок", f"=B{subtotal_row}+B{discount_copyright_row}+B{discount_speed_row}", ""])
    after_disc_row = len(rows)

    rows.append(["НДС",
                 f'=IF(\'02 Конструктор\'!B{find_constructor_row_index("НДС включён")}=TRUE,B{after_disc_row}*0.05,0)',
                 ""])
    vat_row = len(rows)

    rows.append(["💰 К ОПЛАТЕ", f"=B{after_disc_row}+B{vat_row}", "Итог для клиента"])
    total_row = len(rows)

    rows.append([])
    rows.append(["── СРАВНЕНИЕ С БЮДЖЕТОМ ──"])
    rows.append(["Бюджет клиента, ₽", "='01 Старт'!B22", ""])
    budget_row = len(rows)

    rows.append(["Разница (Итог − Бюджет), ₽", f"=B{total_row}-B{budget_row}", ""])
    rows.append(["Превышение, %", f'=IF(B{budget_row}=0,"-",ROUND((B{total_row}-B{budget_row})/B{budget_row}*100,1)&"%")', ""])
    rows.append(["🚦 Статус",
                 f'=IF(B{budget_row}=0,"⬜ нет бюджета",IF(B{total_row}<=B{budget_row},"🟢 вписываемся",IF((B{total_row}-B{budget_row})/B{budget_row}<=0.20,"🟡 в зоне допуска (≤20%)","🔴 ПРЕВЫШЕНИЕ — согласование РОП (Pillar 2)")))',
                 "Цвет по статусу"])
    status_row = len(rows)

    rows.append([])
    rows.append(["── СРОКИ ──"])
    rows.append(["Часов всего", f"=B{total_hours_row}", ""])
    rows.append(["Срок (мес., при 1 разработчике 8ч/день)",
                 f"=ROUND(B{total_hours_row}/(8*20),1)", "20 раб.дней в месяц"])
    timeline_solo_row = len(rows)
    rows.append(["Срок (мес., команда из 2 разработчиков)",
                 f"=ROUND(B{total_hours_row}/(2*8*20),1)", ""])

    # Сохраняем адреса для последующего использования в Тексте КП
    _ESTIMATE_ADDRS.clear()
    _ESTIMATE_ADDRS.update({
        "discovery_hours":  f"B{stage_addrs['Discovery']}",
        "prototype_hours":  f"B{stage_addrs['Прототип']}",
        "design_hours":     f"B{stage_addrs['Дизайн (доп. часы)']}",
        "backend_hours":    f"B{stage_addrs['Бэкенд']}",
        "frontend_hours":   f"B{stage_addrs['Фронтенд']}",
        "qa_hours":         f"B{stage_addrs['QA']}",
        "launch_hours":     f"B{stage_addrs['Launch']}",
        "total_hours":      f"B{total_hours_row}",
        "labor_cost":       f"B{labor_row}",
        "license_cost":     f"B{license_row}",
        "content_cost":     f"B{content_row}",
        "revisions_cost":   f"B{revisions_row}",
        "risks_cost":       f"B{risks_row}",
        "subtotal":         f"B{subtotal_row}",
        "discount_copy":    f"B{discount_copyright_row}",
        "discount_speed":   f"B{discount_speed_row}",
        "after_discounts":  f"B{after_disc_row}",
        "vat":              f"B{vat_row}",
        "total":            f"B{total_row}",
        "budget":           f"B{budget_row}",
        "status":           f"B{status_row}",
        "timeline_solo":    f"B{timeline_solo_row}",
    })

    return rows


# В формулах для скидок нужно знать строки на листе Конструктор где лежат TRUE/FALSE.
# Получим их через предсказуемый алгоритм (tab_constructor_values вызывается до estimate).
_CONSTRUCTOR_ROW_CACHE: dict[str, int] = {}


def precompute_constructor_rows() -> None:
    """Заполняет _CONSTRUCTOR_ROW_CACHE для быстрого поиска формулами из других листов."""
    rows = tab_constructor_values()
    for idx, r in enumerate(rows, 1):
        if r and isinstance(r[0], str):
            _CONSTRUCTOR_ROW_CACHE[r[0]] = idx


def find_constructor_row_index(prefix: str) -> int:
    """Находит строку на листе Конструктор по началу заголовка."""
    if not _CONSTRUCTOR_ROW_CACHE:
        precompute_constructor_rows()
    for title, idx in _CONSTRUCTOR_ROW_CACHE.items():
        if title.startswith(prefix):
            return idx
    raise KeyError(f"Не найдена строка на листе Конструктор: {prefix!r}")


def tab_kp_text_values() -> list[list[Any]]:
    """Лист «05 Текст КП» — Markdown-сборка готового тела КП.

    Менеджер копирует ячейку A2 (всё одна большая ячейка с переносами строк)
    и вставляет в карточку КП в Битрикс24 (поле «Комментарий» / описание).

    Использует _ESTIMATE_ADDRS — поэтому tab_estimate_values должен вызываться раньше.
    """
    if not _ESTIMATE_ADDRS:
        # Прогреем — функция чистая, ничего не зальёт в Sheet
        tab_estimate_values()

    seo_choice_row = find_constructor_row_index("Выбран уровень SEO")
    nl = "CHAR(10)"
    addr = _ESTIMATE_ADDRS

    def smeta(key: str) -> str:
        return f"'04 Смета'!{addr[key]}"

    # Собираем большую формулу-конкатенацию по строкам Markdown
    lines = [
        '"# Коммерческое предложение"',
        '"## "&\'01 Старт\'!B11&" — Веб-разработка"',
        '""',  # blank line
        '"**Подготовлено:** Belberry · "&TEXT(\'01 Старт\'!B24,"dd.mm.yyyy")',
        '"**Менеджер:** "&\'01 Старт\'!B7',
        '"**Сделка:** "&IF(\'01 Старт\'!B5="","—","#"&\'01 Старт\'!B5)',
        '"**ЛПР:** "&\'01 Старт\'!B17&" ("&\'01 Старт\'!B18&")"',
        '""',
        '"## 1. Задача"',
        '\'01 Старт\'!B29',
        '""',
        '"## 2. Что входит"',
        '"- **Платформа:** "&\'02 Конструктор\'!B5',
        '"- **Тип проекта:** "&\'02 Конструктор\'!B6',
        '"- **Страниц/блоков:** см. лист «02 Конструктор», разделы B-C"',
        f'"- **SEO:** "&\'02 Конструктор\'!B{seo_choice_row}',
        '"- **Контент:** включён (тексты услуг/блога — наш медкопирайтер)"',
        '""',
        '"## 3. Этапы и сроки"',
        '"| Этап | Часов |"',
        '"|---|---|"',
        f'"| Discovery | "&{smeta("discovery_hours")}&" |"',
        f'"| Прототип | "&{smeta("prototype_hours")}&" |"',
        f'"| Дизайн | "&{smeta("design_hours")}&" |"',
        f'"| Бэкенд | "&{smeta("backend_hours")}&" |"',
        f'"| Фронтенд | "&{smeta("frontend_hours")}&" |"',
        f'"| QA | "&{smeta("qa_hours")}&" |"',
        f'"| Launch | "&{smeta("launch_hours")}&" |"',
        f'"**Всего часов:** "&TEXT({smeta("total_hours")},"#,##0")',
        f'"**Срок (1 разработчик):** ~"&{smeta("timeline_solo")}&" мес"',
        '""',
        '"## 4. Стоимость"',
        '"| Параметр | ₽ |"',
        '"|---|---|"',
        f'"| Работы | "&TEXT({smeta("labor_cost")},"#,##0")&" |"',
        f'"| Лицензия платформы | "&TEXT({smeta("license_cost")},"#,##0")&" |"',
        f'"| Контент | "&TEXT({smeta("content_cost")},"#,##0")&" |"',
        f'"| Запас на правки (15%) | "&TEXT({smeta("revisions_cost")},"#,##0")&" |"',
        f'"| Запас на риски (10%) | "&TEXT({smeta("risks_cost")},"#,##0")&" |"',
        f'"| **Итого без скидок и НДС** | **"&TEXT({smeta("subtotal")},"#,##0")&"** |"',
        f'"| Скидка за копирайт | "&TEXT({smeta("discount_copy")},"#,##0")&" |"',
        f'"| Скидка за оперативность | "&TEXT({smeta("discount_speed")},"#,##0")&" |"',
        f'"| **Итого после скидок** | **"&TEXT({smeta("after_discounts")},"#,##0")&"** |"',
        f'"| НДС (5% УСН) | "&TEXT({smeta("vat")},"#,##0")&" |"',
        f'"| **К ОПЛАТЕ** | **"&TEXT({smeta("total")},"#,##0")&" ₽** |"',
        '""',
        f'"**Бюджет клиента:** "&TEXT({smeta("budget")},"#,##0")&" ₽"',
        f'"**Соответствие бюджету:** "&{smeta("status")}',
        '""',
        '"## 5. Условия"',
        '"- Срок действия КП: "&\'01 Старт\'!B26&" дней с даты подготовки"',
        '"- Скидка 5% при подписании договора в течение "&\'01 Старт\'!B26&" дней"',
        '"- НДС 5% (УСН)"',
        '"- Оплата: 50% аванс / 30% после демо / 20% запуск"',
        '""',
        '"## 6. За что вы платите Belberry"',
        '"- **Медицинский фокус:** мы делаем сайты только для медицины и сложных b2b (500+ кейсов в портфолио)"',
        '"- **Медкопирайтер в команде:** тексты не перепродают фрилансерам, врач-копирайтер пишет лично"',
        '"- **SEO с первого дня:** структура + meta + sitemap встроены в шаблон, а не «доп. услуга»"',
        '"- **Bitrix24-интеграция:** заявки попадают в вашу CRM с правильными UTM — 0 ₽ доп."',
        '"- **Сопровождение 3 мес после запуска:** включено в стоимость"',
        '""',
        '"## 7. Следующий шаг"',
        '"Прошу подтвердить готовность подписать договор до "&TEXT(\'01 Старт\'!B24+\'01 Старт\'!B26,"dd.mm.yyyy")&" для активации скидки за оперативность."',
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
        ["1.", "Скопируй содержимое A2 (одна большая ячейка)"],
        ["2.", "В Битрикс24 → сделка → «Создать смарт-процесс» → «КП»"],
        ["3.", "В карточку КП в поле «Описание» вставь скопированный текст"],
        ["4.", "Заполни статус КП = «Готово к отправке» — это включит триггер РОП"],
        ["5.", "Отправь клиенту по тому же каналу, где он привык общаться"],
        ["6.", "В сделке Битрикс24 поставь OPPORTUNITY = «К ОПЛАТЕ» из листа «04 Смета»"],
        [],
        ["⚠️ БЕЗ КАРТОЧКИ КП В СИСТЕМЕ — НЕ ОТПРАВЛЯТЬ КЛИЕНТУ (Pillar 1)"],
    ]


def tab_checklist_values() -> list[list[Any]]:
    """Лист «06 Чек-лист 8 pillars» — обязательные условия до отправки."""
    items = [
        ("1. Карточка КП заведена в Битрикс24 (Pillar 1)",
            "TRUE/FALSE", "Без карточки — РОП не видит. КП мимо CRM = отвал."),
        ("2. Сумма проставлена в OPPORTUNITY сделки (Pillar 7)",
            "TRUE/FALSE", "Сделка не подсвечивается руководству без суммы."),
        ("3. Превышение бюджета < 20% ИЛИ есть согласование РОП (Pillar 2)",
            "TRUE/FALSE", "Проверь '04 Смета' статус. Если 🔴 — согласуй до отправки."),
        ("4. Только ОДНО КП на эту сделку (Pillar 4)",
            "TRUE/FALSE", "Дополнительные услуги (SMM, контекст, ORM) = отдельные сделки."),
        ("5. КП будет отправлено клиенту в течение 3 раб.дней (Pillar 3)",
            "TRUE/FALSE", "Если лежит дольше — клиент остывает, конкурент успевает."),
        ("6. Готов скрипт ответа на «А чем лучше бесплатного шаблона?» (Pillar 5)",
            "TRUE/FALSE", "См. лист 05 Текст КП раздел «За что вы платите»."),
        ("7. Назначен «следующий шаг» с конкретной датой (Pillar 6)",
            "TRUE/FALSE", "Первый звонок-проверка в день отправки или максимум на следующий рабочий."),
        ("8. После негативного сигнала клиента готов план Б (Pillar 8)",
            "TRUE/FALSE", "Дата автоматического возврата / альтернативный канал."),
    ]
    rows: list[list[Any]] = [
        ["ЧЕК-ЛИСТ 8 ПУНКТОВ — Pillars of KP Success"],
        ["Все 8 галочек должны быть TRUE до отправки клиенту. См. insights/8-pillars-of-kp-failure."],
        [],
        ["#", "Пункт", "Готово?", "Комментарий"],
    ]
    first = len(rows) + 1
    for title, _, comment in items:
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
# Apply to Sheets


def ensure_tabs(sheets, sid: str, keep_existing: bool) -> dict[str, int]:
    """Создаёт нужные листы и возвращает {title: sheetId}.

    Если keep_existing=False — удаляет все листы кроме первой пустой шапки,
    чтобы было чисто.
    """
    meta = get_sheet_meta(sheets, sid)
    existing = {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta["sheets"]}

    requests: list[dict[str, Any]] = []

    # 1. Если keep_existing=False — удаляем все листы которых нет в TABS, и переименовываем default
    if not keep_existing:
        for title, sheet_id in existing.items():
            if title not in TABS and len(existing) > 1:
                requests.append({"deleteSheet": {"sheetId": sheet_id}})

    # 2. Добавляем недостающие листы
    for title in TABS:
        if title in existing:
            continue
        requests.append({"addSheet": {"properties": {"title": title, "gridProperties": {"rowCount": 200, "columnCount": 10}}}})

    if requests:
        sheets.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": requests}).execute()

    # 3. Если осталась "Лист1" / "Sheet1" — переименуем её в первый из TABS если того ещё нет
    meta = get_sheet_meta(sheets, sid)
    existing = {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta["sheets"]}
    placeholder_titles = ("Лист1", "Sheet1", "Без названия")
    if TABS[0] not in existing:
        for title in placeholder_titles:
            if title in existing:
                requests = [{"updateSheetProperties": {
                    "properties": {"sheetId": existing[title], "title": TABS[0]},
                    "fields": "title",
                }}]
                sheets.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": requests}).execute()
                break

    meta = get_sheet_meta(sheets, sid)
    return {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta["sheets"]}


def write_tab(sheets, sid: str, title: str, values: list[list[Any]]) -> None:
    # Перед заливкой — очищаем
    sheets.spreadsheets().values().clear(
        spreadsheetId=sid, range=f"'{title}'!A1:Z500", body={},
    ).execute()
    sheets.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"'{title}'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def _dropdown_rule(values: list[str]) -> dict[str, Any]:
    return {
        "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in values]},
        "showCustomUi": True, "strict": True,
    }


def _checkbox_rule() -> dict[str, Any]:
    return {"condition": {"type": "BOOLEAN"}, "strict": True}


def apply_formatting(sheets, sid: str, tabs: dict[str, int]) -> None:
    """Форматирование: жирные заголовки, frozen rows, dropdown'ы, чекбоксы."""
    requests: list[dict[str, Any]] = []

    # ── общий стиль шапки + frozen row + auto-resize по всем листам ──────
    for title, sheet_id in tabs.items():
        if title not in TABS:
            continue
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True, "fontSize": 12},
                    "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })
        requests.append({
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        })
        requests.append({
            "autoResizeDimensions": {
                "dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS",
                               "startIndex": 0, "endIndex": 10},
            }
        })

    # ── 01 Старт: dropdown'ы ─────────────────────────────────────────────
    start_id = tabs.get("01 Старт")
    if start_id is not None:
        # Менеджер B7
        requests.append({"setDataValidation": {
            "range": {"sheetId": start_id, "startRowIndex": 6, "endRowIndex": 7, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": _dropdown_rule(MANAGERS),
        }})
        # Сфера B13
        requests.append({"setDataValidation": {
            "range": {"sheetId": start_id, "startRowIndex": 12, "endRowIndex": 13, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": _dropdown_rule(SPHERES),
        }})
        # Источник лида B14
        requests.append({"setDataValidation": {
            "range": {"sheetId": start_id, "startRowIndex": 13, "endRowIndex": 14, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": _dropdown_rule(LEAD_SOURCES),
        }})

    # ── 02 Конструктор: dropdown'ы и чекбоксы ────────────────────────────
    constr_id = tabs.get("02 Конструктор")
    if constr_id is not None:
        # Платформа B5
        platform_titles = [p.title for p in PLATFORMS.values()]
        requests.append({"setDataValidation": {
            "range": {"sheetId": constr_id, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": _dropdown_rule(platform_titles),
        }})
        # Тип проекта B6
        project_titles = [t for _, t in PROJECT_TYPES]
        requests.append({"setDataValidation": {
            "range": {"sheetId": constr_id, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": _dropdown_rule(project_titles),
        }})

        # Чекбоксы для интеграций (колонка B на диапазоне строк)
        # Заголовок интеграций - найдём по структуре; самый простой путь — вызвать precompute.
        precompute_constructor_rows()
        integ_header_row = _CONSTRUCTOR_ROW_CACHE.get("Интеграция")  # шапка таблицы интеграций
        if integ_header_row:
            # Сами интеграции начинаются строкой ниже шапки, длина = len(INTEGRATIONS)
            integ_start = integ_header_row
            integ_end = integ_header_row + len(INTEGRATIONS)
            requests.append({"setDataValidation": {
                "range": {"sheetId": constr_id,
                          "startRowIndex": integ_start, "endRowIndex": integ_end,
                          "startColumnIndex": 1, "endColumnIndex": 2},
                "rule": _checkbox_rule(),
            }})

        # Уровень SEO B<seo_choice_row>
        seo_choice_row = find_constructor_row_index("Выбран уровень SEO")
        seo_titles = [s.title for s in SEO_LEVELS]
        requests.append({"setDataValidation": {
            "range": {"sheetId": constr_id,
                      "startRowIndex": seo_choice_row - 1, "endRowIndex": seo_choice_row,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": _dropdown_rule(seo_titles),
        }})

        # Чекбоксы скидок/НДС
        for label in ("Скидка за копирайт", "Скидка за оперативность", "НДС включён"):
            row = find_constructor_row_index(label)
            requests.append({"setDataValidation": {
                "range": {"sheetId": constr_id,
                          "startRowIndex": row - 1, "endRowIndex": row,
                          "startColumnIndex": 1, "endColumnIndex": 2},
                "rule": _checkbox_rule(),
            }})

    # ── 06 Чек-лист: 8 чекбоксов в колонке C, строки 5..12 ───────────────
    check_id = tabs.get("06 Чек-лист 8 pillars")
    if check_id is not None:
        requests.append({"setDataValidation": {
            "range": {"sheetId": check_id,
                      "startRowIndex": 4, "endRowIndex": 12,
                      "startColumnIndex": 2, "endColumnIndex": 3},
            "rule": _checkbox_rule(),
        }})

    if requests:
        sheets.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": requests}).execute()


# ────────────────────────────────────────────────────────────────────────────
# Main


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Belberry WD Calculator v2")
    parser.add_argument("--spreadsheet-id", required=True, help="ID Google Sheet (из URL между /d/ и /edit)")
    parser.add_argument("--key", default=os.environ.get("GOOGLE_SHEETS_KEY", DEFAULT_KEY), help="Путь к service-account JSON")
    parser.add_argument("--dry-run", action="store_true", help="Вывести структуру в stdout без записи")
    parser.add_argument("--check-only", action="store_true", help="Только проверить доступ")
    parser.add_argument("--keep-existing-tabs", action="store_true", help="Не удалять существующие листы")
    args = parser.parse_args()

    # Прогреем кэш конструктора (нужен для формул в Смете)
    precompute_constructor_rows()

    if args.dry_run:
        builders = [
            ("01 Старт", tab_start_values),
            ("02 Конструктор", tab_constructor_values),
            ("03 Ставки", tab_rates_values),
            ("04 Смета", tab_estimate_values),
            ("05 Текст КП", tab_kp_text_values),
            ("06 Чек-лист 8 pillars", tab_checklist_values),
        ]
        for title, fn in builders:
            vals = fn()
            print(f"\n========== {title} ({len(vals)} строк) ==========")
            for i, row in enumerate(vals[:20], 1):
                print(f"{i:3}: {row}")
            if len(vals) > 20:
                print(f"... +{len(vals)-20} строк")
        return 0

    if not Path(args.key).is_file():
        print(f"ERROR: service-account key не найден: {args.key}", file=sys.stderr)
        return 2

    try:
        sheets, drive = open_clients(args.key)
    except Exception as e:
        print(f"ERROR: не удалось открыть API клиенты: {e}", file=sys.stderr)
        return 3

    try:
        meta = get_sheet_meta(sheets, args.spreadsheet_id)
    except HttpError as e:
        print(f"ERROR: не могу прочитать Sheet {args.spreadsheet_id}: {e}", file=sys.stderr)
        print("Проверь: 1) Sheet существует, 2) расшарен с finance-director-sheets@... как editor", file=sys.stderr)
        return 4

    print(f"OK access: {meta['properties']['title']}")
    print(f"Existing tabs: {[sh['properties']['title'] for sh in meta['sheets']]}")

    if args.check_only:
        return 0

    print("\n→ Создаю/обновляю листы…")
    tab_ids = ensure_tabs(sheets, args.spreadsheet_id, args.keep_existing_tabs)
    print(f"Tabs after sync: {list(tab_ids.keys())}")

    builders = [
        ("01 Старт", tab_start_values),
        ("02 Конструктор", tab_constructor_values),
        ("03 Ставки", tab_rates_values),
        ("04 Смета", tab_estimate_values),
        ("05 Текст КП", tab_kp_text_values),
        ("06 Чек-лист 8 pillars", tab_checklist_values),
    ]

    for title, fn in builders:
        print(f"→ Заливаю «{title}»…")
        write_tab(sheets, args.spreadsheet_id, title, fn())

    print("\n→ Применяю форматирование…")
    apply_formatting(sheets, args.spreadsheet_id, tab_ids)

    print(f"\n✅ Готово.")
    print(f"   https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
