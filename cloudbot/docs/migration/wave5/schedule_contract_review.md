# Schedule Contract Review

Дата фиксации: 2026-04-28 МСК.

Статус: read-only review result. Этот документ не переносит `configs/schedule_contract.env` и не меняет cron/runtime.

## 1. Reviewed file

```text
configs/schedule_contract.env
```

Git status:

```text
M configs/schedule_contract.env
```

## 2. Diff summary

Изменения относительно git baseline:

```text
removed:
LARISA_MIDDAY_CRON_MSK
LARISA_ENABLE_MIDDAY_CRON

added:
LARISA_DAILY_CRON_EXPR_UTC
LARISA_EVENING_CRON_EXPR_UTC
OPENCLAW_HEALTH_DELIVERY_MODE
OPENCLAW_STATUS_DELIVERY_MODE
TODO_DIGEST_EVENING_ENABLED
```

Все значения проверялись в redacted-виде.

## 3. Secret review

Secret-like pattern scan:

```text
no matches
```

Файл содержит schedule/runtime contract variables, а не секреты.

## 4. Confirmed schedule areas

Файл содержит:

- local maintenance cron in MSK;
- Larisa schedule variables;
- OpenClaw scheduler job variables;
- Sales runtime cron expressions in UTC;
- WHOOP server-only cron expression in UTC;
- Todo integration cron variables in UTC.

## 5. Coupling review

Подтвержденные ссылки:

```text
configs/schedules.cron
docs/architecture/schedule_contract.md
docs/architecture/runtime_map.md
infra/orchestrator/lib.sh
checks/instruction_conflicts.sh
infra/orchestrator/workflows/*
```

`docs/architecture/schedule_contract.md` фиксирует:

```text
configs/schedule_contract.env
```

как канонический исполняемый источник расписаний.

## 6. Risk assessment

Риск переноса высокий, потому что:

- файл является schedule contract;
- файл dirty;
- содержит timezone-sensitive значения MSK/UTC;
- связан с Larisa, Sales, WHOOP, Todo/OpenClaw;
- связан с cron/runtime semantics;
- перенос может сломать workflow, который ожидает текущий path.

## 7. Recommendation

```text
do not move
create schedule contract gate
require runtime/schedule approval before any future move
```

## 8. Test result

Проверка:

```bash
python3 -m unittest discover -s tests/unit
```

Результат:

```text
Ran 12 tests
OK
```

## 9. Verdict

```text
review completed
schedule_contract.env remains blocked for migration
```
