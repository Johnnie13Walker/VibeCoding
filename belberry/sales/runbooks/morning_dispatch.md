# Runbook — утренний sales-dispatch Льва Петровича

Документирует фактический live-flow: cron → shell wrapper → workflow →
python module → bitrix snapshot → analytics → telegram → log.

## 09:30 МСК — основной запуск

```
/etc/cron.d/cloudbot-sales-reports
   30 6 * * 1-5 root /usr/local/bin/cloudbot-sales-daily-brief.sh
```

`cloudbot-sales-daily-brief.sh`:
```bash
export TZ=Europe/Moscow
cd /opt/cloudbot-runtime/current
exec ./run_sales_morning_report_from_runtime_env.sh "$@"
```

`run_sales_morning_report_from_runtime_env.sh`:
```bash
export TZ=Europe/Moscow
source /opt/openclaw/.env
source /etc/openclaw/sales_agent.env

export BITRIX_APP_STATE_DIR="${BITRIX_APP_STATE_DIR:-/opt/openclaw/state/bitrix_app}"
export SALES_RUNTIME_ENV_FILE="${SALES_RUNTIME_ENV_FILE:-/etc/openclaw/sales_agent.env}"
export SALES_LOG_FILE="${SALES_LOG_FILE:-/home/ops/cloudbot-sales-agent/reports/sales_agent.log}"
export REPORT_DIR="${REPORT_DIR:-/home/ops/cloudbot-sales-agent/reports}"
export SALES_TRIGGER="${SALES_TRIGGER:-scheduled}"
export SALES_JOB_NAME="${SALES_JOB_NAME:-morning_sales_dispatch}"

exec ./infra/orchestrator/workflows/sales_morning_report.sh
```

`infra/orchestrator/workflows/sales_morning_report.sh` создаёт
`sales_morning_report_YYYYMMDD_HHMMSS_MSK.txt` и запускает:

```
python3 -m agents.lev_petrovich --report sales --send
```

## Python pipeline

`apps/lev_petrovich/agent.py` → `legacy_sales_agent/sales_agent.py`:

1. `SalesAgent.run()` → `build_report_payload()`.
2. `cloudbot/skills/bitrix_sales_data.py:get_sales_snapshot(env_data)` —
   тянет данные через `cloudbot/providers/bitrix/bitrix_sales_adapter.py`.
   Mode выбирается из env, на проде сейчас `app_oauth`.
3. `cloudbot/providers/bitrix/bitrix_app_auth.py` загружает state из
   `/opt/openclaw/state/bitrix_app/{handler,install}.latest.json`,
   сортирует по `saved_at`, берёт самый свежий.
4. `_call_payload_with_state()` дергает Bitrix REST. На 401/`EXPIRED_TOKEN`
   автоматически идёт `refresh_access_token()` (см. `call_payload` строки
   565-585 `bitrix_app_auth.py`). После refresh state пишется обратно.
5. После snapshot строится pipeline analysis + risk detection.
6. `sales_formatter.py` рендерит три текста по контракту
   `shared/contracts/sales_report_format_contract.py`.
7. `telegram_route.py` шлёт через `api.telegram.org/bot<TOKEN>/sendMessage`
   с `parse_mode=HTML` и chunk-разбиением.
8. Все события идут в JSONL `/home/ops/cloudbot-sales-agent/reports/sales_agent.log`.

## События, которые должны быть в логе после успешного 09:30

- `sales_department_filter`
- `sales_snapshot`
- `sales_analysis_scope`
- `sales_product_rows_attached`
- `sales_dispatch_start` ← ключевой маркер «python дошёл до отправки»
- `sales_report_sent` (×3: sales, risks, focus)
- `sales_dispatch_complete`

Если `sales_dispatch_start` есть, а `sales_report_sent` для одного из
трёх типов отсутствует — health-check 09:40 уйдёт в alert.

Если `sales_dispatch_start` отсутствует — python упал до отправки,
обычно на snapshot. Сегодняшний сбой 2026-05-12 — именно этот класс.

## 09:40 МСК — health-check

```
40 6 * * 1-5 root /usr/local/bin/cloudbot-sales-morning-check.sh
```

Запускает:
```
python3 -m cloudbot.devops.sales_dispatch_health --send-alert
```

Логика: окно «сегодня МСК ≥ 09:30», `job_name == morning_sales_dispatch`,
проверка trio sales/risks/focus, обязательные markers, format_version.
При расхождении — Telegram alert.

## Ручной запуск (отладка / тестовая рассылка)

На сервере, под root:

```bash
cd /opt/cloudbot-runtime/current
source /opt/openclaw/.env
source /etc/openclaw/sales_agent.env
export TZ=Europe/Moscow
export SALES_TRIGGER=manual
export SALES_JOB_NAME=manual_test_dispatch
python3 -m agents.lev_petrovich --report sales --send
```

Если нужен dry-run без отправки в боевой чат — переопределить
`SALES_CHAT_ID` на свой тестовый чат перед запуском.
См. `scripts/send_test_message.sh` в этой папке.
