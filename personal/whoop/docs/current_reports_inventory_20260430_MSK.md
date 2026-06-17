# Current reports inventory — 2026-04-30 МСК

## Status

Read-only inventory of active production report and notification contours.

No cron, env, systemd, Docker, runtime pointers, Telegram routes, or `/opt/openclaw` files were changed while collecting this inventory.

All times below are in Moscow time (`Europe/Moscow`). Server cron files use UTC expressions where noted.

## Summary table

| Report / job | Recipient / owner route | Schedule МСК | Cron source | Sender / entrypoint | Runtime contour | Data sources | Latest observed artifact | Current status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Larisa daily brief | Лариса Ивановна, route `larisa-ivanovna` | Daily `08:00` | `/etc/cron.d/cloudbot-larisa-daily-brief` (`0 5 * * *` UTC) | `/usr/local/bin/cloudbot-larisa-daily-brief.sh` | `/opt/cloudbot-runtime/larisa/current` -> `dev_2bb6635` | Bitrix calendar, Todo, OpenClaw env | `/opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260430_114947_MSK.txt` | Manual live-smoke OK, Telegram `delivered: true`; next scheduled run still pending |
| Sales morning report | Лев Петрович / Sales chat | Weekdays `09:30` | `/etc/cron.d/cloudbot-sales-reports` (`30 6 * * 1-5` UTC) | `/usr/local/bin/cloudbot-sales-daily-brief.sh` | `/opt/cloudbot-runtime/current` -> `codex_feature_self-healing_c329f60` | Bitrix app state, sales env, Telegram | `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_20260430_093001_MSK.txt` | Fresh on `2026-04-30`; current runtime still old |
| Sales morning delivery check | Лев Петрович / Sales health check | Weekdays `09:40` | `/etc/cron.d/cloudbot-sales-reports` (`40 6 * * 1-5` UTC) | `/usr/local/bin/cloudbot-sales-morning-check.sh` | `/opt/cloudbot-runtime/current` -> `codex_feature_self-healing_c329f60` | Sales dispatch history/logs | `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_check_20260430_094001_MSK.txt` | OK: confirmed focus and Sales Copilot delivery |
| Sales follow-up | Лев Петрович / Sales chat | Daily `17:00` | `/etc/cron.d/cloudbot-sales-reports` (`0 14 * * *` UTC) | `/usr/local/bin/cloudbot-sales-followup.sh` | `/opt/cloudbot-runtime/current` -> `codex_feature_self-healing_c329f60` | Bitrix app state, sales env, Telegram | `/home/ops/cloudbot-sales-agent/reports/sales_followup_20260429_170001_MSK.txt` | Problem observed: runtime rejects `--report followup` |
| Sales weekly review | Лев Петрович / Sales chat | Fridays `18:30` | `/etc/cron.d/cloudbot-sales-reports` (`30 15 * * 5` UTC) | `/usr/local/bin/cloudbot-sales-weekly-review.sh` | `/opt/cloudbot-runtime/current` -> `codex_feature_self-healing_c329f60` | Bitrix app state, sales env, Telegram | `/home/ops/cloudbot-sales-agent/reports/sales_weekly_review_20260424_183001_MSK.txt` | Problem observed: weekly format validation failed |
| WHOOP daily report | Telegram health route from WHOOP script | Daily `08:01` | `/etc/cron.d/openclaw-whoop-report` (`1 5 * * *` UTC) | `/usr/local/bin/send_whoop_report.py send-report` | Server-only `/usr/local/bin` script with `/etc/openclaw/whoop.env` | WHOOP API, Telegram | `/var/log/openclaw-whoop-report.log` | Fresh on `2026-04-30 08:01 МСК`, Telegram sent |
| Todo cache sync | Internal OpenClaw/Todo cache | Every 30 min plus pre-slots | `/etc/cron.d/openclaw-todo-digest` | `docker exec openclaw-openclaw-gateway-1 ... npm run sync` | `/opt/openclaw` server-only container workspace | Todo integration runtime, SQLite/cache | `/var/log/openclaw-todo-sync.log` | Fresh; latest snapshot saved |
| Todo reminders tick | Telegram task reminders when due | Every minute | `/etc/cron.d/openclaw-todo-digest` | `docker exec openclaw-openclaw-gateway-1 ... npm run reminders:tick` | `/opt/openclaw` server-only container workspace | Todo integration runtime | `/var/log/openclaw-todo-reminders.log` | Fresh; latest tick OK |
| Todo execution tick | Live assistant execution mode | Every 15 minutes | `/etc/cron.d/openclaw-todo-digest` | `docker exec openclaw-openclaw-gateway-1 ... npm run execution:tick` | `/opt/openclaw` server-only container workspace | Todo integration, calendar/free-time state | `/var/log/openclaw-execution-tick.log` | Fresh; latest tick OK |

## Larisa daily brief

Schedule:

- `08:00 МСК` daily;
- cron line: `0 5 * * * root /usr/local/bin/cloudbot-larisa-daily-brief.sh >> /home/ops/cloudbot-larisa-agent/reports/larisa_daily_brief_cron.log 2>&1`.

Execution path:

1. `/etc/cron.d/cloudbot-larisa-daily-brief`
2. `/usr/local/bin/cloudbot-larisa-daily-brief.sh`
3. `cd /opt/cloudbot-runtime/larisa/current`
4. `./run_larisa_daily_brief_from_runtime_env.sh`
5. `./infra/orchestrator/workflows/larisa_daily_brief.sh`

Runtime env loading:

- `/etc/openclaw/larisa.env`;
- `/opt/openclaw/.env`;
- `/etc/openclaw/whoop.env`;
- `BITRIX_APP_STATE_DIR` defaults to `/opt/openclaw/state/bitrix_app`.

Current status:

- current pointer: `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635`;
- manual live-smoke report: `/opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260430_114947_MSK.txt`;
- Telegram payload: `delivered: true`, route `larisa-ivanovna`, chat id resolved but redacted from docs;
- scheduled cron on new release still needs confirmation after `2026-05-01 08:00 МСК`.

## Sales reports

Schedule source:

`/etc/cron.d/cloudbot-sales-reports`

Jobs:

| Job | Schedule МСК | Wrapper | Workflow |
| --- | --- | --- | --- |
| Morning report | Weekdays `09:30` | `/usr/local/bin/cloudbot-sales-daily-brief.sh` | `/opt/cloudbot-runtime/current/infra/orchestrator/workflows/sales_morning_report.sh` |
| Morning check | Weekdays `09:40` | `/usr/local/bin/cloudbot-sales-morning-check.sh` | `/opt/cloudbot-runtime/current/infra/orchestrator/workflows/sales_morning_report_check.sh` |
| Follow-up | Daily `17:00` | `/usr/local/bin/cloudbot-sales-followup.sh` | `/opt/cloudbot-runtime/current/infra/orchestrator/workflows/sales_followup.sh` |
| Weekly review | Friday `18:30` | `/usr/local/bin/cloudbot-sales-weekly-review.sh` | `/opt/cloudbot-runtime/current/infra/orchestrator/workflows/sales_weekly_review.sh` |

Runtime env loading:

- `/opt/openclaw/.env`;
- `/etc/openclaw/sales_agent.env`;
- `BITRIX_APP_STATE_DIR` defaults to `/opt/openclaw/state/bitrix_app`;
- `REPORT_DIR` defaults to `/home/ops/cloudbot-sales-agent/reports`;
- `SALES_LOG_FILE` defaults to `/home/ops/cloudbot-sales-agent/reports/sales_agent.log`.

Latest observed artifacts:

| Artifact | Timestamp МСК | Status |
| --- | --- | --- |
| `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_20260430_093001_MSK.txt` | `2026-04-30 09:31:13` | fresh |
| `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_check_20260430_094001_MSK.txt` | `2026-04-30 09:40:01` | OK |
| `/home/ops/cloudbot-sales-agent/reports/sales_followup_20260429_170001_MSK.txt` | `2026-04-29 17:00:01` | failed |
| `/home/ops/cloudbot-sales-agent/reports/sales_weekly_review_20260424_183001_MSK.txt` | `2026-04-24 18:31:25` | failed |

Observed Sales issues:

1. Sales follow-up currently fails with invalid report type:

   ```text
   argument --report: invalid choice: 'followup' (choose from 'focus', 'pipeline', 'risks', 'sales', 'weekly')
   ```

2. Sales weekly review currently fails format validation:

   ```text
   Sales Copilot error: Ошибки доставки sales-отчетов: weekly (format_validation): Отсутствуют обязательные секции формата: 📊 Отчёт Льва Петровича по продажам
   ```

These issues are in the still-old Sales/generic runtime:

`/opt/cloudbot-runtime/current` -> `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60`

They should be handled in the Lev/Sales dry-run and cutover track, not inside the Larisa cutover observation.

## WHOOP daily report

Schedule:

- `08:01 МСК` daily;
- cron line: `1 5 * * * root /usr/bin/env WHOOP_ENV_FILE=/etc/openclaw/whoop.env /usr/local/bin/send_whoop_report.py send-report >> /var/log/openclaw-whoop-report.log 2>&1`.

Execution path:

1. `/etc/cron.d/openclaw-whoop-report`
2. `/usr/local/bin/send_whoop_report.py send-report`
3. WHOOP API fetches recovery, sleep, cycle and workout/activity data
4. Telegram send

Latest status:

- log timestamp: `2026-04-30 08:01:03 МСК`;
- latest log says `Отчёт отправлен в Telegram`;
- latest metrics were selected for `2026-04-30 МСК`.

Note: the script may refresh and persist WHOOP refresh tokens in the configured env file during normal operation. This inventory did not print secret values.

## Todo / OpenClaw jobs

Schedule source:

`/etc/cron.d/openclaw-todo-digest`

Active jobs:

| Job | Schedule МСК | Command | Log | Latest observed status |
| --- | --- | --- | --- | --- |
| Cache sync | every 30 min, plus `07:55`, `18:55`, `13:55` pre-slots | `npm run sync` inside `openclaw-openclaw-gateway-1` | `/var/log/openclaw-todo-sync.log` | `snapshot_saved`, `tasks=137` |
| Reminders tick | every minute | `npm run reminders:tick` inside `openclaw-openclaw-gateway-1` | `/var/log/openclaw-todo-reminders.log` | `reminders_ok` |
| Execution tick | every 15 minutes | `npm run execution:tick` inside `openclaw-openclaw-gateway-1` | `/var/log/openclaw-execution-tick.log` | `execution_ok` |

Disabled digest slots:

- morning Todo digest at `09:30 МСК`;
- midday Todo digest at `14:00 МСК`;
- evening Todo digest at `19:00 МСК`;
- focus tick.

The cron comments say these were disabled after Larisa cutover steps in March/April 2026.

Important boundary:

- these jobs run inside the OpenClaw gateway container and depend on `/opt/openclaw`, which is a dirty server-only contour;
- this inventory is read-only and does not approve OpenClaw cleanup or migration.

## Operational findings

Confirmed healthy or fresh:

- Larisa manual live-smoke on new runtime;
- Sales morning report and morning check;
- WHOOP daily report;
- Todo sync/reminders/execution ticks.

Needs follow-up:

1. Confirm first scheduled Larisa cron run on `dev_2bb6635` after `2026-05-01 08:00 МСК`.
2. Investigate and repair Sales follow-up report failure.
3. Investigate and repair Sales weekly review format validation failure.
4. Keep `/opt/openclaw` no-touch until the planned server-only audit.

## Recommended next steps

1. Proceed with Phase 4 Lev/Sales dry-run validation without runtime changes.
2. Include the observed follow-up and weekly failures in the Phase 4 report.
3. Do not switch `/opt/cloudbot-runtime/current` until Sales dry-run and approval package explicitly cover these report contracts.
