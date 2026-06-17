# Cron Template Gate

Дата фиксации: 2026-04-28 МСК.

Статус: gate only. Этот документ не переносит `configs/schedules.cron` и не меняет cron/runtime.

## 1. Gate decision

```text
configs/schedules.cron migration: not approved
```

Причина:

```text
cron/runtime-sensitive template with local absolute paths
```

## 2. Current file

```text
configs/schedules.cron
```

Статус:

```text
dirty
local cron contour
no-touch for structural migration
```

## 3. Confirmed risks

Подтвержденные риски:

- содержит `CRON_TZ=Europe/Moscow`;
- содержит concrete cron lines;
- содержит absolute path `/Users/pro2kuror/Desktop/Cloudbot/engineer`;
- запускает `./scripts/agent_commit.sh`;
- запускает `./infra/orchestrator/run_workflow.sh larisa_daily_brief`;
- запускает `./infra/orchestrator/run_workflow.sh larisa_content_topics`;
- разделяет local cron и server scheduler contours.

## 4. Approval required before any future move

Перед любым будущим переносом нужен отдельный:

```text
cron/runtime approval
```

Он должен подтвердить:

1. Это только template или реально применяемый cron source.
2. Какой local path должен быть canonical: `Cloudbot/engineer` или `OpenClo/projects/engineer`.
3. Как сохранить compatibility с текущим cron.
4. Как проверить, что live cron не изменился.
5. Как проверить Larisa daily/content topics schedule.
6. Как откатить без изменения live cron.

## 5. Not approved

Сейчас запрещено:

- переносить `configs/schedules.cron`;
- менять cron expressions;
- менять absolute path;
- менять `CRON_TZ`;
- менять `run_workflow` targets;
- менять local crontab;
- менять `/etc/cron.d/*`;
- менять deploy/runtime scripts;
- менять `configs/schedule_contract.env`.

## 6. Future design requirements

Будущий design должен включать:

```text
current path
target path
absolute path decision
local vs server contour decision
cron validation plan
rollback plan
owner approval
```

Без решения по absolute path перенос запрещен.

## 7. Verification

Проверка gate:

```bash
rg -n "schedules.cron|absolute path|Cloudbot/engineer|cron approval|runtime approval|no-touch" docs/migration/wave5/cron_template_gate.md
python3 -m unittest discover -s tests/unit
```

## 8. Verdict

```text
cron template migration blocked
next safe step: Wave 6 gate
```
