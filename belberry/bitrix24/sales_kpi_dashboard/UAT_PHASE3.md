# UAT Phase 3 — Output Sheet schema + first production refresh

## Контекст

- Worktree: `/Users/pro2kuror/Desktop/VibeCoding/`
- Branch: `feat/sales-kpi-output-schema`
- Output Sheet: `1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE`
- TZ: `Europe/Moscow`

## Первый live bootstrap + refresh

- Bootstrap start: `2026-05-20T17:51:00+03:00`
- Refresh finish: `2026-05-20T17:54:44+03:00`

### bootstrap-schema report

```json
{
  "created": ["Plan", "tm_metrics", "sales_plan", "mop_metrics", "sync_log"],
  "kept": [],
  "seeded": ["Plan", "sync_log"],
  "archived": ["Лист1 → _archive_лист1 (hidden)"],
  "dry_run": ["false"]
}
```

### Tabs после live refresh

| Tab | Hidden | Rows total | Data rows | Header |
|---|---:|---:|---:|---|
| `_archive_лист1` | true | — | — | — |
| `Plan` | false | 30 | 29 | `Period, Metric, Dimension, Value, Comment` |
| `tm_metrics` | false | 4 | 3 | `date_calc, period, employee_id, employee_name, naborov_per_day, calls_120s_per_day, meetings_fact, meetings_plan, meetings_trend, meetings_forecast, conv_nabor_to_call, conv_call_to_meeting, meetings_per_week_avg` |
| `sales_plan` | false | 26 | 25 | `date_calc, dimension_type, dimension_value, fact, plan, forecast, trend, percent_done` |
| `mop_metrics` | false | 3 | 2 | `date_calc, employee_id, employee_name, calls_60s, tasks_closed, kp_sent, meetings_first, meetings_repeat, deals_signed` |
| `sync_log` | false | 2 | 1 | `ts, status, phase` |

## Наблюдения

- Первый production refresh прошёл успешно: CLI вернул `Refresh: OK`.
- `Лист1` не удалён, а переименован в `_archive_лист1` и скрыт.
- `Plan` содержит только структурный seed с нулевыми значениями; это input-вкладка для РОП.
- Enriched `sync_log` будет включён следующим коммитом Phase 3.
