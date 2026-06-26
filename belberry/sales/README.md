# Belberry / Sales — рабочая папка процесса Льва Петровича

Это рабочая копия и runbook-слой для production-процесса утреннего sales-отчёта
Льва Петровича (бот `icom_dir_Belberry_bot`).

Production исходники живут в каноническом repo
`OpenClo/projects/engineer` (ветка `codex/feature/sales-copilot-live-bitrix`
или `feature/sales-report-structure` в зависимости от того, что сейчас
выкачено в `/opt/cloudbot-runtime/current`).

Эта папка нужна, чтобы:

- держать актуальный runbook процесса в одном месте;
- хранить серверные диагностические/восстановительные скрипты,
  которые можно `scp` на VPS и запускать одной командой;
- фиксировать incident-логи по падениям утреннего dispatch;
- держать контракт обязательных секций отчёта и health-check схему.

## Структура

```
belberry/sales/
├── README.md                       # этот файл
├── contracts/                      # обязательные секции отчёта, sequence
├── docs/                           # архитектурные заметки, схема pipeline
├── monitoring/                     # health-check схема, alert templates
├── runbooks/                       # incident response, daily ops
├── scripts/                        # server-runnable .sh и .py
└── src/                            # копии ключевых исходников для review
```

## Production environment (сервер)

- host: `cloudbot-hz` (188.34.206.115), root
- runtime symlink: `/opt/cloudbot-runtime/current`
- env: `/opt/openclaw/.env`, `/etc/openclaw/sales_agent.env`
- bitrix OAuth state dir: `/opt/openclaw/state/bitrix_app/`
- reports dir: `/home/ops/cloudbot-sales-agent/reports/`
- log JSONL: `/home/ops/cloudbot-sales-agent/reports/sales_agent.log`
- telegram token file: `/root/.openclaw/telegram/commercial-director.bot_token`

## Cron расписание (server, UTC)

| UTC | МСК | команда |
|-----|-----|---------|
| 06:30 пн-пт | 09:30 | `/usr/local/bin/cloudbot-sales-daily-brief.sh` — основной утренний отчёт |
| 06:40 пн-пт | 09:40 | `/usr/local/bin/cloudbot-sales-morning-check.sh` — health-check |
| 14:00 daily | 17:00 | `/usr/local/bin/cloudbot-sales-followup.sh` — follow-up |
| 15:30 пт   | 18:30 | `/usr/local/bin/cloudbot-sales-weekly-review.sh` — еженедельный обзор |

Лежит в `/etc/cron.d/cloudbot-sales-reports`.

## Sequence контракт (что должен прислать утренний отчёт)

`shared/contracts/sales_report_contract.py`:

```
SALES_PRIMARY_REPORT     = "sales"
SALES_FOLLOWUP_REPORTS   = ("risks", "focus")
SALES_DISPATCH_SEQUENCE  = ("sales", "risks", "focus")
```

То есть один запуск `python3 -m agents.lev_petrovich --report sales --send`
обязан доставить три сообщения подряд: Sales Copilot → Риски → Фокус РОПа.

## Sales department scope (по умолчанию)

`apps/lev_petrovich/legacy_sales_agent/sales_team_scope.py`:

- Группа продаж Belberry
- Группа продаж Acoola Team
- Телемаркетинг

Override через env: `SALES_DEPARTMENT_IDS`, `SALES_DEPARTMENT_NAMES`,
`SALES_EXCLUDED_USER_*`.

## Bitrix entities

- сделки: `crm.deal.list`, `CATEGORY_ID=10`
- встречи: smart-process entity 1048, category 24, `crm.item.list`
- брифы: smart-process entity 1056, category 28, `crm.item.list`
- активности/звонки: `crm.activity.list`
- задачи: webhook fallback → `tasks.task.list` app OAuth
- сообщения: Wazzup archive в `/opt/openclaw/state/bitrix_app/wazzup.*.json`

## Куда смотреть при сбое утреннего dispatch

1. `/home/ops/cloudbot-sales-agent/reports/sales_daily_cron.log` — что вернул cron stdout/stderr
2. `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_YYYYMMDD_HHMMSS_MSK.txt` — stdout python job
3. `/home/ops/cloudbot-sales-agent/reports/sales_agent.log` — структурированные события (`sales_dispatch_start`, `sales_report_sent`, `sales_error`)
4. `/opt/openclaw/state/bitrix_app/install.latest.json` — текущий OAuth state, поле `saved_at`, `auth_refreshed_at`

См. [runbooks/morning_dispatch.md](runbooks/morning_dispatch.md) и
[runbooks/incident_2026-05-12_token_expired.md](runbooks/incident_2026-05-12_token_expired.md).
