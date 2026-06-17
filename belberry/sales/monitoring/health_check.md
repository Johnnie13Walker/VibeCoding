# Health-check 09:40 — что именно проверяется

Модуль: `cloudbot/devops/sales_dispatch_health.py`.

Команда cron 09:40 МСК:
```
python3 -m cloudbot.devops.sales_dispatch_health --send-alert
```

## Логика

1. Определяет сегодняшнюю МСК-дату.
2. Окно поиска событий: `today_msk_00:00 + 09:30` … now.
3. Читает `/home/ops/cloudbot-sales-agent/reports/sales_agent.log`
   (JSONL построчно).
4. Фильтр: `date == today_msk`, `ts_msk >= 09:30`, `job_name == morning_sales_dispatch`.
5. Проверки:
   - есть ли `sales_dispatch_start`;
   - есть ли `sales_report_sent` для каждого из `sales / risks / focus`;
   - порядок отправки совпадает с `SALES_DISPATCH_SEQUENCE`;
   - нет ли `sales_error` / `sales_report_error` для этих типов;
   - совпадение `format_version`, `template_id`;
   - все обязательные markers присутствуют.

## Возможные verdicts

| verdict | условие | действие |
|---------|---------|----------|
| `ok` | trio доставлено, нет ошибок | alert не шлётся |
| `missing_start` | нет `sales_dispatch_start` | alert: «python не дошёл до отправки» |
| `missing_reports` | trio неполное | alert: «утренняя рассылка sales неполная» |
| `wrong_order` | порядок нарушен | alert: «нарушен sequence» |
| `format_violation` | секции/markers отсутствуют | alert: «нарушен формат» |
| `errors_seen` | есть `sales_error` | alert с причиной |

## Известная слепая зона

Сейчас health-check не различает:

- «cron не стартовал» (никаких событий за окно)
- «cron стартовал и python упал ДО `sales_dispatch_start`»
  (например на Bitrix snapshot — сегодняшний случай)

Оба дают `missing_start`. Текст алерта одинаковый, оператор должен
самостоятельно посмотреть `sales_daily_cron.log` или
`sales_morning_report_*.txt`, чтобы понять, что именно упало.

Fix-предложение: писать раннее событие `sales_job_process_start`
в `SalesAgent.run()` *до* `build_report_payload()`. Тогда:

- нет ни `process_start`, ни `dispatch_start` → cron не дошёл до python;
- есть `process_start`, нет `dispatch_start` → python упал на snapshot;
- есть оба, нет `report_sent` → отвалилась telegram-отправка.

## Где смотреть

- `/home/ops/cloudbot-sales-agent/reports/sales_agent.log` — JSONL события
- `/home/ops/cloudbot-sales-agent/reports/sales_daily_cron.log` — stdout cron
- `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_*.txt` — stdout python job
- `/home/ops/cloudbot-sales-agent/reports/sales_morning_check_cron.log` — stdout 09:40 check
