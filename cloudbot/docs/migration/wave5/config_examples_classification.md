# Config Examples Classification

Дата фиксации: 2026-04-28 МСК.

Статус: classification only. Этот документ не переносит config-файлы, не меняет env, cron, runtime, systemd, docker или deploy scripts.

## 1. Цель

Цель шага - отделить безопасные config examples от файлов, которые могут быть связаны с расписаниями, live env или runtime contracts.

Это подготовка к будущему design-only шагу. Реальный перенос config-файлов этим документом не разрешен.

## 2. Current config area

Текущая активная зона:

```text
configs/
```

Найденные файлы:

```text
configs/app_config.env.example
configs/integrations.env.example
configs/schedule_contract.env
configs/schedules.cron
configs/README.md
```

Target skeleton уже существует:

```text
config/
config/env/
config/env/examples/
config/env/schemas/
config/schedules/
```

Target skeleton не является active runtime path.

## 3. Classification table

| Current path | Classification | Future target candidate | Migration decision | Reason |
| --- | --- | --- | --- | --- |
| `configs/app_config.env.example` | env example | `config/env/examples/app_config.env.example` | candidate for future move | Шаблон переменных окружения без значений, подходит для examples после approval |
| `configs/integrations.env.example` | env example | `config/env/examples/integrations.env.example` | candidate for future move | Шаблон интеграций без значений, но содержит много secret variable names; нужен secret-safe review |
| `configs/schedule_contract.env` | schedule contract / runtime-sensitive | `config/schedules/schedule_contract.env` | investigate first | Фиксирует cron expressions для Ларисы, Sales, WHOOP, Todo/OpenClaw; нельзя переносить без schedule/runtime review |
| `configs/schedules.cron` | cron template / local schedule-sensitive | `config/schedules/schedules.cron` | blocked for move now | Содержит конкретные cron lines и absolute path `/Users/pro2kuror/Desktop/Cloudbot/engineer`; может быть связан с локальным cron-контуром |
| `configs/README.md` | current boundary marker | keep in place | keep compatibility | Уже фиксирует, что `configs/` не live env directory и не approval на migration |

## 4. Safe candidates

Потенциально безопасные будущие candidates:

```text
configs/app_config.env.example
configs/integrations.env.example
```

Ограничение: перенос разрешается только после отдельного owner approval и проверки ссылок.

## 5. Runtime-sensitive files

Пока не переносить:

```text
configs/schedule_contract.env
configs/schedules.cron
```

Причины:

- содержат schedule/cron contract;
- могут быть связаны с local scheduler или server-only conventions;
- содержат timezone-sensitive значения;
- `configs/schedules.cron` содержит absolute local path;
- перенос может создать confusion между examples и active schedule contract.

## 6. No-touch scope

В рамках Wave 5 config classification запрещено:

- менять `configs/*`;
- создавать реальные `.env` файлы;
- менять live env;
- менять live cron;
- менять runtime pointers;
- менять systemd/docker;
- менять deploy/rollback/verify scripts;
- трогать `/opt/*`, `/etc/*`, `/root/*`, `/home/ops/*`;
- менять agent/runtime behavior.

## 7. Checks

Для этого шага обязательны проверки:

```bash
rg -n "app_config.env.example|integrations.env.example|schedule_contract.env|schedules.cron|live env|runtime|no-touch" docs/migration/wave5/config_examples_classification.md
python3 -m unittest discover -s tests/unit
```

## 8. Step verdict

```text
classification completed
config moves not approved
next safe step: documentation-only config examples boundary marker
```
