# UAT Phase 2 — Sales KPI Aggregator

- Timestamp: 2026-05-20T17:36:43+03:00
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
    ["2026-05-20", "2026-05", "ALL", "Все ТМ", 112.54, 9.08, 14, 0.0, 13.66, 14, 8.07, 11.86, 5.38],
    ["2026-05-20", "2026-05", 2832, "Вострецов Аркадий", 50.0, 3.77, 10, 0.0, 10.83, 10, 7.54, 20.41, 3.85],
    ["2026-05-20", "2026-05", 2772, "Исаева Дарья", 62.54, 5.31, 4, 0.0, 4.62, 4, 8.49, 5.8, 1.54]
  ],
  "sales_plan": [
    ["date_calc", "dimension_type", "dimension_value", "fact", "plan", "forecast", "trend", "percent_done"],
    ["2026-05-20", "product", "SEO", 526899.0, 0.0, 526899.0, 911768.43, 0.0],
    ["2026-05-20", "meetings_product", "SEO", 16.0, 0.0, 16, 16.0, 0.0],
    ["2026-05-20", "product", "PPC", 91500.0, 0.0, 91500.0, 91500.0, 0.0]
  ],
  "mop_metrics": [
    ["date_calc", "employee_id", "employee_name", "calls_60s", "tasks_closed", "kp_sent", "meetings_first", "meetings_repeat", "deals_signed"],
    ["2026-05-20", 2806, "Деговцова Елизавета", 49, 150, 13, 12, 1, 0],
    ["2026-05-20", 2846, "Семенихин Егор", 55, 100, 3, 5, 1, 0]
  ],
  "sync_log": [
    ["ts", "status", "phase"],
    ["2026-05-20T17:36:43+03:00", "ok", "phase 2"]
  ]
}
```

## Инварианты

- Dry-run два раза подряд дал идентичный output без timestamp-полей.
- Деления на 0 защищены: плановые значения пустые, поэтому `percent_done=0.0`, forecast возвращает fact.
- Все timestamps в Europe/Moscow.
- Production Sheet не изменялся.
- ТМ-встречи считаются из smart-process `Встречи` (`entityTypeId=1048`) без productrow-фильтра, потому что ТМ назначает встречи до появления товаров на сделке.

## Ожидаемые проблемы и инварианты для Phase 3

- `Plan` пока пустой или отсутствует, поэтому все планы равны 0. Phase 3 должна создать и заполнить input-вкладку.
- Если у сделки нет productrows — она не попадает в продуктовую атрибуцию.
- Если PRODUCT_ID не входит в 10 основных продуктов — строка учитывается как `Прочее`.
- Если у ТМ/МОП нет звонков или встреч — метрики остаются 0 без exception.
