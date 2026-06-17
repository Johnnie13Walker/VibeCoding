# Belberry — Portfolio Sync (ETL портфолио клиентов)

Трёхэтапный ETL-пайплайн, который ежедневно собирает портфолио проектов Belberry/Acoola из мастер-таблицы продаж в публикуемую таблицу «Клиенты» + базу данных + визуальный дашборд.

**Перенесено 2026-05-28** из `~/Desktop/OpenClo/projects/engineer/scripts/portfolio_*` и `infra/orchestrator/workflows/portfolio_*` в единый модуль.

## Зачем это нужно

Портфолио — главный источник кейсов по нишам для КП, разборов сделок и пресейл-материалов. **532 проекта на 28 мая 2026** (см. dry-run). Без этого ETL менеджеры вели бы кейсы вручную в Sheets.

См. также [reference-belberry-portfolio-sheet](file:///Users/pro2kuror/.claude/projects/-Users-pro2kuror-Desktop-VibeCoding/memory/reference_belberry_portfolio_sheet.md) — описание самих таблиц портфолио.

## Архитектура пайплайна

```
┌─────────────────────────────────────────────────┐
│ Мастер-таблица "Продажи"                        │
│ 17SBisFgKrf3hRP_zjVPC2e4wMzlq8j8HDC2bvkyS74Y    │
│ Лист "Все года" (gid=1482533080)                │
└──────────────────┬──────────────────────────────┘
                   │
        ┌──────────┴──────────┬──────────────────────┐
        ▼                     ▼                      ▼
 [1] clients_sync.mjs   [2] database_refresh    [3] dashboard_refresh
        │                     │                      │
        ▼                     ▼                      ▼
 Sheet "Клиенты"        Sheet "Данные"          Sheet "Дашборд"
 1TSEei_ncr3SQmiYT...   1TgWlFHOvSDtW0e60...    1om_oGYvDZrADYbAbz...
 (gid=1955270606)
        │
        ▼
 Telegram — Лариса
 Ивановна шлёт отбивку
 после синка
```

### [1] portfolio_clients_sync.mjs (основной, ежедневный)

Читает мастер-таблицу, группирует по проектам, для **новых** проектов:
- Проверяет живой ли сайт (HTTP с 5 fallback-URL)
- Классифицирует по нише regex'ами по тексту страницы (медицина — отдельный богатый классификатор: стоматология, ветеринария, репродуктология, диагностика, …)
- Добавляет в таблицу «Клиенты» с форматированием, валидацией ячеек, фильтрами

Для **существующих** — обновляет «безопасные» поля (услуги, годы, период, статус, опыт) без перезаписи категории/подкатегории. Также заполняет пустые бренды.

В конце — JSON-отчёт + отбивка в Telegram-чат Ларисы Ивановны.

### [2] portfolio_database_refresh.mjs

Refresh плоской базы записей в `1TgWlF...` лист "Данные". Это нормализованная база для аналитики (Продукт × Клиент × Год × Месяц).

### [3] portfolio_dashboard_refresh.mjs

Из базы (шаг 2) строит визуальный дашборд в `1om_oG...`: вкладки Дашборд, Категории, Продукты, Клиенты, Продукт × Клиент, Классификация, dash_data.

## Структура папки

```
portfolio_sync/
├── README.md
├── .env.example                    ← все env переменные с дефолтами
├── scripts/
│   ├── portfolio_clients_sync.mjs       — [1] клиенты
│   ├── portfolio_database_refresh.mjs   — [2] база
│   ├── portfolio_dashboard_refresh.mjs  — [3] дашборд
│   ├── build_portfolio_template_xlsx.py — генератор xlsx-шаблона
│   ├── run_portfolio_clients_daily.sh   — daily runner [1] + Telegram
│   └── run_portfolio_database_daily.sh  — daily runner [2]
├── install/
│   ├── install_portfolio_clients_server_cron.sh  — установка cron на VPS [1]
│   └── install_portfolio_database_server_cron.sh — установка cron на VPS [2]
├── workflows/
│   ├── portfolio_clients_sync_deploy.sh — оркестратор деплоя
│   └── portfolio_clients_sync_verify.sh — verify после деплоя
└── logs/                          — локальные логи и dry-run отчёты
```

## Зависимости

- **Node.js ≥18** (нативный fetch, проверено на v25.6.1)
- **Google service account**: `finance-director-sheets-903611b799c3.json` — read+write на все три таблицы
- **Python 3.10+** — только для `build_portfolio_template_xlsx.py` (генератор шаблона, не для синка)

Service account уже лежит локально:
```
/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json
```

## Запуск локально

### Smoke test (dry-run, ничего не пишет)

```bash
cd belberry/sales/portfolio_sync
node scripts/portfolio_clients_sync.mjs --dry-run --report-json logs/dry_run.json
```

Должен вывести JSON-отчёт: `sourceProjects`, `existingProjects`, `newProjectsFound`, `plannedAddCount` и т.д. На 28.05.2026: 566 source / 532 existing / 0 new.

### Боевой запуск (пишет в Sheets)

```bash
cd belberry/sales/portfolio_sync
PORTFOLIO_CLIENTS_SEND_TELEGRAM=0 bash scripts/run_portfolio_clients_daily.sh
```

`PORTFOLIO_CLIENTS_SEND_TELEGRAM=0` — выключает отбивку в Telegram. По умолчанию отбивка идёт, но требует `LARISA_TELEGRAM_BOT_TOKEN` + `LARISA_TELEGRAM_CHAT_ID`.

### Дашборд и база (отдельно)

```bash
node scripts/portfolio_database_refresh.mjs --dry-run
node scripts/portfolio_dashboard_refresh.mjs --dry-run
```

## Production на VPS

**Cron живёт на VPS уже, мы его не трогаем при миграции.**

- Live runtime: `/opt/cloudbot-runtime/portfolio-clients/current/`
- Env: `/etc/openclaw/portfolio_clients.env`
- SA на VPS: `/etc/openclaw/finance-director-sheets-903611b799c3.json`
- Cron: `/etc/cron.d/cloudbot-portfolio-clients` — **09:05 МСК ежедневно** (06:05 UTC)
- Logs: `${ROOT_DIR}/tmp/portfolio_clients_daily.cron.log`

VPS читает код из `codex-base.git` (старый репо engineer). После того как мы перенесём engineer → VibeCoding/cloudbot/ и перепишем deploy bundle, VPS будет читать из VibeCoding/belberry/sales/portfolio_sync/.

**До этого:** на VPS работает старая версия, локально — новая. На синк это не влияет: код по сути идентичный, ничего не сломается.

## Env переменные

См. `.env.example`. Все имеют разумные дефолты — без env файла скрипт запускается локально нормально.

Ключевые:
- `PORTFOLIO_SOURCE_SHEET_URL` — мастер-таблица продаж (дефолт зафиксирован)
- `PORTFOLIO_CLIENTS_SHEET_URL` — таблица «Клиенты» (дефолт зафиксирован)
- `PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON` — путь к SA JSON
- `PORTFOLIO_CLIENTS_SEND_TELEGRAM` — 0/1, отбивка в Telegram
- `LARISA_TELEGRAM_BOT_TOKEN`, `LARISA_TELEGRAM_CHAT_ID` — нужны для отбивки

## Что НЕ трогать без причины

- **Классификаторы ниш** в `portfolio_clients_sync.mjs` (функции `classifyByText`, `classifyMedicalByText`) — это годами накопленные regex'ы по реальным проектам, ломать их легко, проверять — долго.
- **Список исключений** `DEFAULT_EXCLUDED_PROJECTS`, `DEFAULT_EXCLUDED_SERVICES` — это бизнес-правила, проекты которые НЕ должны попасть в портфолио (agency/service записи + saturnia.ru).
- **PROJECT_CLASSIFICATION_OVERRIDES** — ручные привязки категорий для проектов где автоклассификатор не справляется (1c-bitrix.ru → IT, calltouch.ru → BI, …).
- **`HEADER_ROW_INDEX_1 = 13`** и **`DATA_START_ROW_INDEX_1 = 14`** — таблица «Клиенты» имеет шапку на 13-й строке (выше — summary-блок). Менять только если поменялась сама структура листа.

## Логи и отладка

- Локальные dry-run отчёты — `logs/*.json`
- VPS логи — `/opt/cloudbot-runtime/portfolio-clients/current/tmp/portfolio_clients_*.log`
- Telegram dry-run — `${LOG_DIR}/portfolio_clients_telegram.dry_run.txt` (если `LARISA_TELEGRAM_DRY_RUN=1`)

## История

- **2026-05-08** — последнее изменение скрипта в engineer (`portfolio_clients_sync.mjs`)
- **2026-05-28** — перенос в VibeCoding/belberry/sales/portfolio_sync/, замена пути SA с openclo → vibecoding, smoke test пройден (566/532/0).
