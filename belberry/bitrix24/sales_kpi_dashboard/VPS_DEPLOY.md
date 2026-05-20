# VPS deploy — Sales KPI Dashboard

## Discovery

- Дата: `2026-05-20`
- Host alias: `cloudbot-ssh-proxy`
- Hostname: `ams-1-vm-76ds`
- Пользователь: `root`
- Системная TZ VPS: `Etc/UTC`
- Python: `Python 3.12.3`
- `uv`: не установлен

## Existing runtime layout

```text
/opt/cloudbot-runtime/
├── current -> /opt/cloudbot-runtime/releases/dev_3b160ba
├── larisa/
│   └── current -> /opt/cloudbot-runtime/larisa/releases/dev_2bb6635
├── marketing-dashboard/
└── portfolio-clients/
```

Целевой путь Phase 4:

```text
/opt/cloudbot-runtime/larisa/sales-kpi-dashboard/
```

На момент discovery директории ещё нет.

## Bitrix OAuth state на VPS

Найдены файлы:

```text
/opt/openclaw/state/bitrix_app/install.latest.json
/opt/openclaw/state/bitrix_app/manual_probes/install.latest.json
/root/.openclaw/workspaces/commercial-director/integrations/bitrix/state/install.latest.json
```

Для cron wrapper используем default:

```bash
BITRIX_STATE=/opt/openclaw/state/bitrix_app/install.latest.json
BITRIX_SYNC_SCRIPT=/opt/openclaw/repos/vibecoding/shared/scripts/bitrix-sync-state.sh
```

## Larisa wrappers / cron pattern

Существующие wrappers:

```text
/usr/local/bin/cloudbot-larisa-daily-brief.sh
/usr/local/bin/cloudbot-larisa-midday-replan.sh
```

Пример wrapper:

```bash
#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow
cd '/opt/cloudbot-runtime/larisa/current'
exec ./run_larisa_daily_brief_from_runtime_env.sh "$@"
```

Существующий cron:

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Production Debian cron исполняет /etc/cron.d по системному UTC.
# 08:00 МСК = 05:00 UTC.
0 5 * * * root /usr/local/bin/cloudbot-larisa-daily-brief.sh >> /home/ops/cloudbot-larisa-agent/reports/larisa_daily_brief_cron.log 2>&1
```

Вывод: `/etc/cron.d/*` задаём в UTC. Для Sales KPI нужно `0 3,7,11,15 * * *`.

## Env для TG alerts

Файлы существуют:

```text
/opt/openclaw/.env
/etc/openclaw/larisa.env
```

Секреты не читаем и не коммитим. Wrapper экспортирует:

```bash
LARISA_TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
LARISA_TELEGRAM_CHAT_ID="$LARISA_TELEGRAM_CHAT_ID"
```

## sales_dashboard на VPS

`sales_dashboard` не найден в `/opt`, `/etc`, `/root` на момент discovery. Phase 4 deploy копирует локальные модули:

- `belberry/bitrix24/sales_dashboard/`
- `belberry/bitrix24/sales_kpi_dashboard/`

в целевой runtime `/opt/cloudbot-runtime/larisa/sales-kpi-dashboard/`.

## Live deploy result

Phase 4 live deploy выполнен 2026-05-20:

- `/opt/cloudbot-runtime/larisa/sales-kpi-dashboard/` создан.
- `.venv` создан через VPS `python3 -m venv`.
- `sales_dashboard` и `sales_kpi_dashboard` установлены editable.
- wrapper установлен в `/usr/local/bin/cloudbot-larisa-sales-kpi.sh`.
- cron установлен в `/etc/cron.d/cloudbot-larisa-sales-kpi`.
- два ручных запуска wrapper завершились `Refresh: OK`.
- `sync_log` Output Sheet получил 2 новые строки, `Plan` остался 30 строк.

См. подробный smoke-log в `UAT_PHASE4.md`.
