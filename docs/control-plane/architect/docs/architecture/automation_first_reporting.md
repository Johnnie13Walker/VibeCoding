# Automation-first отчеты и автозаполнение таблиц

Дата: 2026-04-22 МСК

## Цель

Регулярные отчеты, обновление Google Sheets и отправка статусов должны выполняться
обычными скриптами по расписанию. LLM не участвует в cron-потоке и не генерирует
регулярный отчет. Модель используется только вручную: для анализа, объяснения,
разбора ошибки или разовой доработки логики.

## Что уже есть в проекте

### Cron / scheduler

- `/Users/pro2kuror/Desktop/architect/scripts/install_marketing_dashboard_cron.sh`
  устанавливает локальный cron-блок в `Europe/Moscow`.
- Текущий cron-блок:
  - `08:00 МСК` - запуск полного обновления маркетингового дашборда.
  - `08:15 МСК` - отправка короткого Telegram-статуса.
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/configs/schedules.cron`
  содержит локальный schedule-контракт инженерного контура.
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/bot/src/scheduler/daemonScheduler.js`
  содержит lightweight scheduler daemon для bot-задач с проверкой cron-like
  расписания раз в минуту.
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/infra/orchestrator/run_workflow.sh`
  запускает workflow-скрипты как тонкий orchestrator, без бизнес-логики внутри.

### Scripts / jobs

Готовый deterministic pipeline маркетингового дашборда:

- `/Users/pro2kuror/Desktop/architect/scripts/run_marketing_dashboard_daily.sh`
  главный runner: логирование, retry, шаги pipeline, verifier, status JSON.
- `/Users/pro2kuror/Desktop/architect/scripts/refresh_marketing_dashboard_live.py`
  читает live-данные Bitrix24, считает когорты и события, пишет JSON-слои в `/tmp`.
- `/Users/pro2kuror/Desktop/architect/scripts/build_cohort_filter_sheet.mjs`
- `/Users/pro2kuror/Desktop/architect/scripts/build_event_filter_sheet.mjs`
- `/Users/pro2kuror/Desktop/architect/scripts/build_ceo_dashboard.mjs`
- `/Users/pro2kuror/Desktop/architect/scripts/build_support_sheets.mjs`
- `/Users/pro2kuror/Desktop/architect/scripts/build_operational_sheets.mjs`
- `/Users/pro2kuror/Desktop/architect/scripts/beautify_dashboard_tabs.mjs`
- `/Users/pro2kuror/Desktop/architect/scripts/compact_dashboard_tabs.mjs`
- `/Users/pro2kuror/Desktop/architect/scripts/verify_marketing_dashboard_live.mjs`
- `/Users/pro2kuror/Desktop/architect/scripts/send_marketing_dashboard_telegram_status.py`

### Интеграции

- Bitrix24:
  - auth-логика: `/Users/pro2kuror/Desktop/architect/scripts/bitrix_field_audit_gd324.py`,
    функция `make_auth()`;
  - чтение сделок и stage history: `refresh_marketing_dashboard_live.py`;
  - batch-паттерны также есть в инженерном контуре:
    `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/providers/bitrix/bitrix_sales_adapter.py`.
- Google Sheets:
  - service account: путь задается в скриптах Google Sheets;
  - запись значений через `spreadsheets.values.update`;
  - форматирование, создание вкладок, скрытие вкладок и charts через
    `spreadsheets.batchUpdate`;
  - verifier читает диапазоны пачкой через `spreadsheets.values:batchGet`.
- Telegram:
  - marketing status отправляется отдельным deterministic Python-скриптом;
  - токен Ларисы хранится вне git через `LARISA_TELEGRAM_BOT_TOKEN_FILE`.

### Orchestrator / workers

- `run_workflow.sh` в инженерном контуре - тонкий orchestrator для shell workflows.
- `cloudbot/orchestrator/*` - пользовательский/агентный orchestration слой.
- `agents/*/providers/*` и `cloudbot/providers/*` - узкие providers/workers для
  внешних источников.
- Для scheduled pipelines бизнес-логика должна оставаться в scripts/providers,
  а orchestrator должен только выбирать и запускать нужный workflow.

### Env / credentials loading

- Основной integrations env:
  `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.integrations`.
- Фактический локальный secret/env путь:
  `/Users/pro2kuror/.config/openclo/assistant/.env.integrations`.
- Секреты не коммитятся. Token files и service account JSON должны оставаться вне git.

## Итоговая архитектура

```text
cron / scheduler
  |
  v
thin runner / orchestrator script
  |
  +-- read-only workers/providers
  |     +-- Bitrix24 batch/list API
  |     +-- Google Sheets batchGet
  |     +-- SQL/API/file sources
  |
  +-- local calculation layer
  |     +-- normalize rows
  |     +-- calculate aggregates
  |     +-- write JSON/CSV/Markdown artifacts
  |
  +-- write pipeline
  |     +-- Google Sheets values.update / values.batchUpdate
  |     +-- Google Sheets batchUpdate for formatting only
  |     +-- files/reports/status JSON
  |
  +-- verifier
  |     +-- batchGet ranges
  |     +-- compare source JSON totals with sheet totals
  |
  +-- notifier
        +-- short Telegram status from status JSON
```

Разделение ответственности:

- `orchestrator` запускает pipeline и передает параметры.
- `workers/providers` читают данные из конкретных источников.
- `scheduled pipelines` считают метрики и пишут результат.
- `report generation` строится кодом: API, batch reads, SQL, локальные агрегаты,
  batch writes.
- LLM не вызывается из cron и не участвует в регулярной генерации.

## Pipeline для отчета по расписанию

Базовый шаблон:

1. `refresh_<domain>_live.py`
   - загрузить данные из CRM/API/SQL;
   - читать пачками;
   - нормализовать поля;
   - посчитать агрегаты локально;
   - сохранить промежуточные артефакты в `/tmp` или `tmp/`.
2. `build_<domain>_report.mjs` или `.py`
   - собрать отчетные таблицы/markdown/json из готовых артефактов;
   - не вызывать LLM;
   - не делать повторные дорогие API-запросы, если данные уже сохранены.
3. `verify_<domain>.mjs` или `.py`
   - прочитать итоговые диапазоны пачкой;
   - сверить суммы, количество строк, ключевые инварианты.
4. `send_<domain>_telegram_status.py`
   - прочитать status JSON;
   - отправить короткий статус;
   - не пересчитывать отчет.

Текущая реализация этого шаблона:

- runner: `scripts/run_marketing_dashboard_daily.sh`;
- status JSON: `tmp/marketing_dashboard_daily_status.json`;
- latest log: `tmp/marketing_dashboard_daily_latest.log`;
- Telegram status: `scripts/send_marketing_dashboard_telegram_status.py`.

## Pipeline для обновления таблиц по расписанию

Для Google Sheets использовать такой порядок:

1. Получить access token по service account.
2. Прочитать metadata таблицы один раз:
   `GET /v4/spreadsheets/{spreadsheetId}`.
3. При необходимости создать вкладки через `spreadsheets.batchUpdate`.
4. Записать значения только в нужные диапазоны:
   - `spreadsheets.values.update` для одной плотной сетки;
   - `spreadsheets.values.batchUpdate` для нескольких несмежных диапазонов.
5. Оформление, скрытие вкладок, размеры колонок, conditional formatting и charts
   делать через один или несколько `spreadsheets.batchUpdate`.
6. Формулы и ручные зоны не чистить, если они не принадлежат pipeline.
7. После записи запустить verifier через `values:batchGet`.

В маркетинговом дашборде этот подход уже используется:

- `build_*_sheet.mjs` пишет значения и formatting requests;
- `compact_dashboard_tabs.mjs` скрывает служебные вкладки;
- `verify_marketing_dashboard_live.mjs` читает все контрольные диапазоны через
  `values:batchGet` и сверяет их с JSON.

## Batch-механизмы

### Google Sheets

- Чтение: `spreadsheets.values:batchGet`.
- Запись значений:
  - `spreadsheets.values.update` для одного плотного диапазона;
  - `spreadsheets.values.batchUpdate` для набора диапазонов.
- Структура/формат:
  - `spreadsheets.batchUpdate`.

Правило: один build-скрипт должен сначала собрать полный массив значений локально,
а затем отправить его одним запросом на диапазон. Не писать ячейки по одной.

### Bitrix24

- Для больших выборок использовать `list_method` со страницами или метод `batch`.
- Для связанных сущностей читать chunks по 50 ID.
- Для истории стадий использовать отдельный read-only этап и сохранять результат
  в JSON-слой.

Правило: сначала собрать raw/normalized rows, затем считать метрики локально.

## Cron entries

Текущий production-like cron для marketing dashboard:

```cron
CRON_TZ=Europe/Moscow
# BEGIN MARKETING_DASHBOARD_DAILY
0 8 * * * cd '/Users/pro2kuror/Desktop/architect' && /bin/zsh '/Users/pro2kuror/Desktop/architect/scripts/run_marketing_dashboard_daily.sh' >> '/Users/pro2kuror/Desktop/architect/tmp/marketing_dashboard_daily.cron.log' 2>&1
15 8 * * * cd '/Users/pro2kuror/Desktop/architect' && python3 '/Users/pro2kuror/Desktop/architect/scripts/send_marketing_dashboard_telegram_status.py' >> '/Users/pro2kuror/Desktop/architect/tmp/marketing_dashboard_telegram.cron.log' 2>&1
# END MARKETING_DASHBOARD_DAILY
```

Для нового pipeline использовать отдельный marked block:

```cron
CRON_TZ=Europe/Moscow
# BEGIN <DOMAIN>_DAILY
0 7 * * * cd '<repo>' && /bin/zsh '<repo>/scripts/run_<domain>_daily.sh' >> '<repo>/tmp/<domain>_daily.cron.log' 2>&1
15 7 * * * cd '<repo>' && python3 '<repo>/scripts/send_<domain>_telegram_status.py' >> '<repo>/tmp/<domain>_telegram.cron.log' 2>&1
# END <DOMAIN>_DAILY
```

## Логирование, retry и точки отказа

Runner должен иметь:

- `TZ=Europe/Moscow`;
- отдельный timestamped log;
- symlink/latest log;
- `run_step` с retry;
- `status.json` с полями:
  - `status`;
  - `started_at`;
  - `ended_at`;
  - `timezone`;
  - `log_path`;
  - `failed_step`;
  - `exit_code`;
  - `verification`.

Понятные точки отказа:

- auth/env не загружены;
- API недоступен;
- batch read вернул неполные данные;
- расчетные JSON не созданы;
- Sheets write не прошел;
- verifier нашел расхождение;
- Telegram token/chat_id не настроены.

Если шаг упал, runner пишет `FAIL` в status JSON и прекращает pipeline. Telegram
status отправляет короткое сообщение по этому JSON.

## Ручной прогон

Маркетинговый дашборд:

```bash
cd /Users/pro2kuror/Desktop/architect
./scripts/run_marketing_dashboard_daily.sh
node scripts/verify_marketing_dashboard_live.mjs
python3 scripts/send_marketing_dashboard_telegram_status.py --dry-run
python3 scripts/send_marketing_dashboard_telegram_status.py
```

Проверить cron:

```bash
crontab -l | sed -n '/BEGIN MARKETING_DASHBOARD_DAILY/,/END MARKETING_DASHBOARD_DAILY/p'
```

Проверить логи:

```bash
tail -n 120 /Users/pro2kuror/Desktop/architect/tmp/marketing_dashboard_daily_latest.log
tail -n 120 /Users/pro2kuror/Desktop/architect/tmp/marketing_dashboard_daily.cron.log
tail -n 120 /Users/pro2kuror/Desktop/architect/tmp/marketing_dashboard_telegram.cron.log
```

## Проверка работоспособности

Минимальный набор после изменений:

```bash
cd /Users/pro2kuror/Desktop/architect
bash -n scripts/run_marketing_dashboard_daily.sh
bash -n scripts/install_marketing_dashboard_cron.sh
python3 -m py_compile scripts/refresh_marketing_dashboard_live.py
python3 -m py_compile scripts/send_marketing_dashboard_telegram_status.py
node scripts/verify_marketing_dashboard_live.mjs
python3 scripts/send_marketing_dashboard_telegram_status.py --dry-run
```

Если token-file Ларисы настроен, проверить фактическую отправку:

```bash
python3 scripts/send_marketing_dashboard_telegram_status.py
```

Ожидаемый результат:

```text
telegram_status=sent
```

## Как не тратить токены

- Не запускать LLM из cron.
- Не использовать conversational agent для регулярного заполнения таблиц.
- Все scheduled jobs должны быть shell/Python/Node scripts.
- Отчеты считать кодом: API/SQL/JSON/CSV -> агрегаты -> Sheets/file/status.
- Human-readable summary формировать шаблоном из готового status JSON.
- LLM использовать только on-demand:
  - расследовать сбой;
  - изменить расчет;
  - объяснить метрики;
  - подготовить разовую аналитическую интерпретацию.

## Шаблон файлов для нового домена

```text
scripts/refresh_<domain>_live.py
scripts/build_<domain>_sheets.mjs
scripts/build_<domain>_report.py
scripts/verify_<domain>_live.mjs
scripts/send_<domain>_telegram_status.py
scripts/run_<domain>_daily.sh
scripts/install_<domain>_cron.sh
tmp/<domain>_daily_status.json
tmp/<domain>_daily_latest.log
tmp/<domain>_daily.cron.log
tmp/<domain>_telegram.cron.log
```

Для каждого нового домена сначала делать read-only refresh и verifier, только
после этого подключать write-path в таблицы и cron.

