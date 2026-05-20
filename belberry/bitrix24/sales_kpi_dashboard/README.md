# sales_kpi_dashboard

Дашборд по продажам и телемаркетингу Belberry с обновлением 4 раза в сутки. Тянет данные из Bitrix24 belberrycrm, агрегирует в Python, пишет в отдельный Google Sheet, который читает Looker Studio.

## Статус

Phase 0 — Discovery (готов к старту). Полный план в Obsidian:

```
/Users/pro2kuror/Documents/Cloudbot-Vault/09-Projects/belberry-sales-kpi-dashboard/
├── _README.md          ← миссия проекта
├── PLAN.md             ← фазы реализации (вход для Codex)
├── METRICS-SPEC.md     ← формулы всех метрик
├── STATUS.md           ← прогресс
└── AI-AGENTS-SETUP.md  ← как работать AI-агентам
```

## Архитектура (после Phase 1)

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

# smoke: Bitrix profile + Google Sheet metadata + add/delete временной вкладки
python -m sales_kpi_dashboard.cli check

# Phase 1 refresh не пишет production-вкладки
python -m sales_kpi_dashboard.cli refresh --dry-run

# тесты
pytest -xvs tests/
```

## Ссылки

- Полный план: см. Obsidian-проект выше.
- Соседний проект: `../sales_dashboard/README.md`.
