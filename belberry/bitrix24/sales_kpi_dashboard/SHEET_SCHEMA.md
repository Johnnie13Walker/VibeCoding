# Output Sheet — структура вкладок

Sheet: `Дашборд Отдел продаж 2026`  
ID: `1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE`

## Plan

Input-вкладка РОП. ETL её не перезаписывает.

| Period | Metric | Dimension | Value | Comment |
|---|---|---|---:|---|

Seed Phase 3 создаёт структурные ключи за текущий месяц:

- ТМ: `Встречи_всего`, `Наборы_всем`, `Звонки_120_всем`, `Встречи_<user_id>`
- Sales: `План_<product>`, `План_встреч_<product>`, `План_Прочее`, `План_общий`
- МОП: `План_МОП_<user_id>`

## tm_metrics

Output-вкладка, перезаписывается при каждом refresh.

| date_calc | period | employee_id | employee_name | naborov_per_day | calls_120s_per_day | meetings_fact | meetings_plan | meetings_trend | meetings_forecast | conv_nabor_to_call | conv_call_to_meeting | meetings_per_week_avg |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## sales_plan

Output-вкладка, перезаписывается при каждом refresh.

| date_calc | dimension_type | dimension_value | fact | plan | forecast | trend | percent_done |
|---|---|---|---:|---:|---:|---:|---:|

## mop_metrics

Output-вкладка, перезаписывается при каждом refresh.

| date_calc | employee_id | employee_name | calls_60s | tasks_closed | kp_sent | meetings_first | meetings_repeat | deals_signed |
|---|---|---|---:|---:|---:|---:|---:|---:|

## sync_log

Output-вкладка, дописывается append-строкой при каждом успешном refresh.

| ts | status | phase | duration_ms | rows_written | error |
|---|---|---|---:|---:|---|

## Архив

Исходный пустой `Лист1` не удаляется: Phase 3 переименовал его в `_archive_лист1` и скрыл (`hidden=true`).
