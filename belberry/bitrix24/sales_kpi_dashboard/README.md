# sales_kpi_dashboard

Дашборд по продажам и телемаркетингу Belberry с обновлением 4 раза в сутки. Тянет данные из Bitrix24 belberrycrm, агрегирует в Python, пишет в отдельный Google Sheet, который читает Looker Studio.

## Статус

Phase 3 — Output Sheet schema + первый production refresh. Полный план в Obsidian:

```
/Users/pro2kuror/Documents/Cloudbot-Vault/09-Projects/belberry-sales-kpi-dashboard/
├── _README.md          ← миссия проекта
├── PLAN.md             ← фазы реализации (вход для Codex)
├── METRICS-SPEC.md     ← формулы всех метрик
├── STATUS.md           ← прогресс
└── AI-AGENTS-SETUP.md  ← как работать AI-агентам
```

## Архитектура

```
Bitrix24 REST
   │ через sales_dashboard.bitrix_client (переиспользуем)
   ▼
sales_kpi_dashboard/aggregator.py
   │ считает план/факт/тренд/прогноз
   ▼
Google Sheet «Дашборд Отдел продаж 2026»
SHEET_ID=1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE
   │
   ▼
Looker Studio dashboard (3 страницы: ТМ + План ОП + Эффективность МОПов)
```

## Что переиспользуется

- `belberry/bitrix24/sales_dashboard/sales_dashboard/bitrix_client.py` — BitrixClient
- `belberry/bitrix24/sales_dashboard/sales_dashboard/sheets_client.py` — SheetsClient
- `shared/config/bitrix24-state/install.latest.json` — OAuth state (общий с cloudbot на VPS)
- `~/.config/vibecoding/assistant/secrets/finance-director-sheets-*.json` — Google service account

## Зачем отдельный модуль (а не расширение sales_dashboard)

- `sales_dashboard` — это **raw ETL** (Bitrix → Sheet с сырыми deals/calls/users).
- `sales_kpi_dashboard` — **aggregation layer** поверх raw + входная вкладка с планами от РОП.
- Cron-cycle разный: sales_dashboard каждые 15 минут, sales_kpi_dashboard 4 раза в сутки. Их независимость снижает blast radius при поломке агрегатора.

## Установка

```bash
cd belberry/bitrix24/sales_kpi_dashboard
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e .
uv pip install -e ../sales_dashboard
uv pip install -e ".[dev]"
```

## Запуск

```bash
# read-only discovery Bitrix → DISCOVERY.md
python discovery_probe.py

# read-only probe UF-полей SP «Встречи» → DISCOVERY.md appendix
python discovery_sp1048_probe.py

# smoke: Bitrix profile + Google Sheet metadata + add/delete временной вкладки
python -m sales_kpi_dashboard.cli check

# посмотреть, что будет создано в Output Sheet, без записи
python -m sales_kpi_dashboard.cli bootstrap-schema --dry-run

# live bootstrap вкладок Output Sheet: Plan, tm_metrics, sales_plan, mop_metrics, sync_log
python -m sales_kpi_dashboard.cli bootstrap-schema

# dry-run агрегатора: печатает preview, в Sheet не пишет
python -m sales_kpi_dashboard.cli refresh --dry-run

# production refresh: перезаписывает output-вкладки, sync_log дописывает строку
python -m sales_kpi_dashboard.cli refresh

# тесты
pytest -xvs tests/
```

Перед Bitrix-вызовами обнови OAuth state штатным скриптом:

```bash
bash /Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh
```

`Plan` — input-вкладка РОП. `SheetsWriter` намеренно падает при попытке писать в `Plan` или `Plan_MRR`.

## Output Sheet

Текущая схема вкладок описана в `SHEET_SCHEMA.md`.

## Production cron на VPS

Phase 4 развёрнут на `cloudbot-hz`:

- runtime: `/opt/cloudbot-runtime/larisa/sales-kpi-dashboard/`
- wrapper: `/usr/local/bin/cloudbot-larisa-sales-kpi.sh`
- cron: `/etc/cron.d/cloudbot-larisa-sales-kpi`
- log: `/var/log/cloudbot-larisa-sales-kpi.log`
- schedule: `0 3,7,11,15 * * *` UTC = `06/10/14/18` МСК

Ручной smoke на VPS:

```bash
ssh root@cloudbot-hz /usr/local/bin/cloudbot-larisa-sales-kpi.sh
```

Freshness-check для Cloudbot daily health-check:

```bash
python -m sales_kpi_dashboard.cli health-check --max-age-hours 6
```

Подробности deploy и UAT:

- `VPS_DEPLOY.md`
- `UAT_PHASE4.md`

## Ссылки

- Полный план: см. Obsidian-проект выше.
- Соседний проект: `../sales_dashboard/README.md`.
