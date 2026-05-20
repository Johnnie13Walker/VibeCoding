# UAT Phase 2 — Sales KPI Aggregator

- Timestamp: 2026-05-20T17:22:15+03:00
- Command: `PYTHONPATH=../sales_dashboard python -m sales_kpi_dashboard.cli refresh --dry-run`
- Mode: read-only Bitrix + read-only Sheet Plan; production output tabs were not written.

## Row Counts

| Tab | Rows |
|---|---:|
| tm_metrics | 3 |
| sales_plan | 25 |
| mop_metrics | 2 |
| sync_log | 1 |

## Preview

```json
{
  "tm_metrics": [
    ["date_calc", "period", "employee_id", "employee_name", "naborov_per_day", "calls_120s_per_day", "meetings_fact", "meetings_plan", "meetings_trend", "meetings_forecast", "conv_nabor_to_call", "conv_call_to_meeting", "meetings_per_week_avg"],
    ["2026-05-20", "2026-05", "ALL", "Все ТМ", 112.54, 9.08, 0, 0.0, 0.0, 0, 8.07, 0.0, 0.0],
    ["2026-05-20", "2026-05", 2832, "Вострецов Аркадий", 50.0, 3.77, 0, 0.0, 0.0, 0, 7.54, 0.0, 0.0],
    ["2026-05-20", "2026-05", 2772, "Исаева Дарья", 62.54, 5.31, 0, 0.0, 0.0, 0, 8.49, 0.0, 0.0]
  ],
  "sales_plan": [
    ["date_calc", "dimension_type", "dimension_value", "fact", "plan", "forecast", "trend", "percent_done"],
    ["2026-05-20", "product", "SEO", 526899.0, 0.0, 526899.0, 911768.43, 0.0],
    ["2026-05-20", "meetings_product", "SEO", 0.0, 0.0, 0, 0.0, 0.0],
    ["2026-05-20", "product", "PPC", 91500.0, 0.0, 91500.0, 91500.0, 0.0]
  ],
  "mop_metrics": [
    ["date_calc", "employee_id", "employee_name", "calls_60s", "tasks_closed", "kp_sent", "meetings_first", "meetings_repeat", "deals_signed"],
    ["2026-05-20", 2806, "Деговцова Елизавета", 49, 150, 12, 0, 0, 0],
    ["2026-05-20", 2846, "Семенихин Егор", 55, 99, 3, 0, 0, 0]
  ],
  "sync_log": [
    ["ts", "status", "phase"],
    ["2026-05-20T17:22:15+03:00", "ok", "phase 2"]
  ]
}
```

## Инварианты

- Dry-run два раза подряд дал идентичный output без timestamp-полей.
- Деления на 0 защищены: плановые значения пустые, поэтому `percent_done=0.0`, forecast возвращает fact.
- Все timestamps в Europe/Moscow.
- Production Sheet не изменялся.

## Ожидаемые проблемы и инварианты для Phase 3

- `Plan` пока пустой или отсутствует, поэтому все планы равны 0. Phase 3 должна создать и заполнить input-вкладку.
- Если у сделки нет productrows — она не попадает в продуктовую атрибуцию.
- Если PRODUCT_ID не входит в 10 основных продуктов — строка учитывается как `Прочее`.
- Если у ТМ/МОП нет звонков или встреч — метрики остаются 0 без exception.
