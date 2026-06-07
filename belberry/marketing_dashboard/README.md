# Belberry Marketing Dashboard

Автоматический процесс обновления Google Sheet `Маркетинговый Даш`.

- Sheet: `https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit`
- Production runtime: `/opt/cloudbot-runtime/marketing-dashboard/current`
- Production cron: `/etc/cron.d/cloudbot-marketing-dashboard`
- Время: Europe/Moscow

## Что делает процесс

`scripts/run_marketing_dashboard_daily.sh` запускает deterministic pipeline без LLM:

1. `refresh_marketing_dashboard_live.py` читает live-данные Bitrix24 и пишет JSON-слои в `/tmp`.
2. `build_cohort_filter_sheet.mjs` собирает вкладку `Когортный фильтр`.
3. `build_event_filter_sheet.mjs` собирает вкладку `Событийный фильтр`.
4. `build_ceo_dashboard.mjs` собирает `CEO Dashboard`.
5. `build_support_sheets.mjs` собирает служебные вкладки и `Качество данных`.
6. `build_operational_sheets.mjs` собирает операционные вкладки.
7. `build_source_dynamics_sheet.mjs` собирает `Динамика источников 2026`.
8. `build_spam_source_sheet.mjs` собирает `Спам по источникам`.
9. `beautify_dashboard_tabs.mjs` применяет оформление.
10. `compact_dashboard_tabs.mjs` прячет сырьевые вкладки.
11. `check_marketing_dashboard_month_literals.mjs` проверяет, что нет жёстко прошитого месяца.
12. `verify_marketing_dashboard_live.mjs` сверяет JSON и Google Sheets.

## Бизнес-правила

- Обращение — всё входящее в sales/report-контур, включая спамные отказы.
- Лид — обращение, которое не закрыто в отказ с причиной `Спам`, `Вход: нет связи` или `Нет связи`.
- КП — сделка, где был факт перехода в стадию подготовки КП.
- Источник `Телемаркетинг` переопределяется по факту встречи: по сделке есть элемент смарт-процесса `Встречи`, а создатель встречи состоит в отделе телемаркетинга. Переход из отдельной воронки телемаркетинга не обязателен, потому что до марта 2026 телемаркетологи работали из лидов.
- Raw `SOURCE_ID=Телемаркетинг` сам по себе не считается телемаркетингом; если нет встречи, созданной сотрудником отдела телемаркетинга, такая сделка попадает в `Не выяснено`.
- Для источника `Телемаркетинг` месяц обращения берётся по полю `Дата встречи` первой встречи, созданной сотрудником телемаркетинга.
- Для источника `Телемаркетинг` полноценный лид считается, если по сделке есть проведённая встреча от телемаркетинга; перенос первой встречи не обнуляет лид.
- Спамные отказы (`Спам`, `Вход: нет связи`, `Нет связи`) дополнительно показываются на вкладке `Спам по источникам`.

## Локальный запуск

По умолчанию `MARKETING_DASHBOARD_ENGINEER_ROOT` указывает на `<repo>/cloudbot` (раньше — `~/Desktop/OpenClo/projects/engineer`, мигрировано 28.05.2026). Переменную можно переопределить, если нужно гонять с альтернативной копии engineer.

```bash
cd /Users/pro2kuror/Desktop/VibeCoding/belberry/marketing_dashboard
MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON=/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json \
bash scripts/run_marketing_dashboard_daily.sh
```

## Установка cron на Mac

```bash
cd /Users/pro2kuror/Desktop/VibeCoding/belberry/marketing_dashboard
bash scripts/install_marketing_dashboard_cron.sh
```

## Установка cron на сервере

На сервере запускать от root:

```bash
cd /opt/cloudbot-runtime/marketing-dashboard/current
bash scripts/install_marketing_dashboard_server_cron.sh
```

Cron обновляет дашборд ежедневно в 08:00 МСК и отправляет Telegram-статус в 08:15 МСК.
