# Schedule Contract Gate

Дата фиксации: 2026-04-28 МСК.

Статус: gate only. Этот документ не переносит `configs/schedule_contract.env` и не меняет cron/runtime.

## 1. Gate decision

```text
configs/schedule_contract.env migration: not approved
```

Причина:

```text
runtime/schedule-sensitive contract
```

## 2. Current source

Текущий путь:

```text
configs/schedule_contract.env
```

Статус:

```text
active schedule contract
dirty
no-touch for structural migration
```

## 3. Covered contours

Файл содержит расписания и флаги для:

- local maintenance in MSK;
- Larisa daily/evening schedules;
- OpenClaw health/status delivery;
- Sales runtime cron expressions in UTC;
- WHOOP server-only cron;
- Todo server-only cron.

## 4. Required approval before any future move

Перед любым будущим переносом нужен отдельный approval:

```text
runtime/schedule approval
```

Он должен подтвердить:

1. Кто читает `configs/schedule_contract.env`.
2. Какие workflows зависят от этого path.
3. Как сохранить compatibility path.
4. Как проверить MSK/UTC semantics.
5. Как проверить Larisa schedule.
6. Как проверить Sales schedule.
7. Как проверить OpenClaw/Todo/WHOOP schedules.
8. Как откатить без изменения live cron.

## 5. Not approved

Сейчас запрещено:

- переносить `configs/schedule_contract.env`;
- менять значения расписаний;
- менять MSK/UTC semantics;
- менять `configs/schedules.cron`;
- менять live cron;
- менять runtime pointers;
- менять systemd/docker;
- менять deploy scripts;
- менять workflows, которые читают contract.

## 6. Future design requirements

Будущий design должен включать:

```text
current path
target path
compatibility strategy
reader map
MSK/UTC validation
rollback plan
smoke checks
```

Без reader map перенос запрещен.

## 7. Verification

Проверка gate:

```bash
rg -n "schedule_contract.env|runtime/schedule approval|cron|MSK|UTC|not approved|no-touch" docs/migration/wave5/schedule_contract_gate.md
python3 -m unittest discover -s tests/unit
```

## 8. Verdict

```text
schedule contract migration blocked
next safe step: schedules.cron read-only review
```
