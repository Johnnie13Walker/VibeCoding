# Schedules Cron Review

Дата фиксации: 2026-04-28 МСК.

Статус: read-only review result. Этот документ не переносит `configs/schedules.cron` и не меняет cron/runtime.

## 1. Reviewed file

```text
configs/schedules.cron
```

Git status:

```text
M configs/schedules.cron
```

## 2. Diff summary

Изменения относительно git baseline:

- источник расписаний теперь явно ссылается на `configs/schedule_contract.env`;
- файл описан как локальный cron-контур разработческой машины;
- время maintenance изменено с `03:00` на `06:00` МСК;
- Larisa daily brief изменен с будних `09:00` на ежедневный `08:00` МСК;
- добавлен `larisa_content_topics` в `19:30` МСК;
- path изменен с `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` на `/Users/pro2kuror/Desktop/Cloudbot/engineer`;
- Sales Copilot / WHOOP / OpenClaw scheduler явно вынесены в серверный контур.

## 3. Absolute path review

Найден absolute path:

```text
/Users/pro2kuror/Desktop/Cloudbot/engineer
```

Категория:

```text
local-machine path
```

Риск:

```text
migration-sensitive
```

Причина: `Cloudbot/engineer` является wrapper/symlink navigation layer, а canonical code source зафиксирован как:

```text
/Users/pro2kuror/Desktop/OpenClo/projects/engineer
```

Это не значит, что path надо менять сейчас. Это значит, что `configs/schedules.cron` нельзя переносить или править без отдельного cron/runtime approval.

## 4. Confirmed local cron entries

Файл содержит:

```text
CRON_TZ=Europe/Moscow
06:00 МСК agent_commit
08:00 МСК larisa_daily_brief
19:30 МСК larisa_content_topics
```

## 5. Server contour note

Файл явно говорит:

```text
Sales Copilot / WHOOP / OpenClaw scheduler управляются серверным контуром.
```

Это подтверждает, что смешивать local cron и server runtime нельзя.

## 6. Secret review

Secret-like pattern scan:

```text
no matches
```

## 7. Test result

Проверка:

```bash
python3 -m unittest discover -s tests/unit
```

Результат:

```text
Ran 12 tests
OK
```

## 8. Recommendation

```text
do not move
create cron template gate
require cron/runtime approval before any future move
```

## 9. Verdict

```text
review completed
schedules.cron remains blocked for migration
```
