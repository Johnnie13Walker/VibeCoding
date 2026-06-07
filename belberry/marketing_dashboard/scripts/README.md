# scripts

Служебные скрипты проекта.

Сейчас добавлен только безопасный шаблон `deploy.sh`:

- по умолчанию работает в dry-run;
- пишет таймстампы в МСК;
- не выполняет реальный deploy без `DRY_RUN=0`;
- должен быть дополнен шагами конкретного проекта.

Дополнительно используются служебные скрипты для Google Sheets:

- `run_marketing_dashboard_daily.sh` — deterministic runner ежедневного marketing dashboard без LLM;
- `refresh_marketing_dashboard_live.py` — читает live-данные Bitrix24 и считает JSON-слои;
- `build_ceo_dashboard.mjs` — собирает главный управленческий лист `CEO Dashboard`;
- `build_cohort_filter_sheet.mjs` — собирает интерактивный когортный лист с выбором месяцев;
- `build_event_filter_sheet.mjs` — собирает интерактивный событийный лист с выбором месяцев;
- `build_support_sheets.mjs` — собирает служебные вкладки и качество данных;
- `build_operational_sheets.mjs` — собирает операционные вкладки со сделками и продажами;
- `build_source_dynamics_sheet.mjs` — собирает вкладку `Динамика источников 2026`;
- `build_spam_source_sheet.mjs` — собирает вкладку `Спам по источникам`;
- `beautify_dashboard_tabs.mjs` — применяет оформление через Google Sheets batchUpdate;
- `compact_dashboard_tabs.mjs` — прячет дублирующие и сырьевые вкладки, оставляя компактный набор для работы.
- `check_marketing_dashboard_month_literals.mjs` — проверяет, что в дашборде нет жёстко прошитого месяца;
- `marketing_dashboard_period.mjs` — общий helper для выбора актуального периода;
- `verify_marketing_dashboard_live.mjs` — проверяет согласованность JSON и Google Sheets через batchGet;
- `send_marketing_dashboard_telegram_status.py` — отправляет короткий статус из готового status JSON.

Архитектурный контракт для дешевых регулярных отчетов без фоновых LLM loops:
`docs/architecture/automation_first_reporting.md`.
