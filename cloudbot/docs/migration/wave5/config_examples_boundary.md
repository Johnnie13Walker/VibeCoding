# Config Examples Boundary

Дата фиксации: 2026-04-28 МСК.

Статус: documentation-only marker. Этот документ не переносит config-файлы и не меняет env/runtime.

## 1. Boundary decision

Target path:

```text
config/env/examples/
```

is for future examples only.

It is not:

- active runtime config;
- live env directory;
- secret storage;
- cron config;
- deploy config;
- server config.

## 2. Current source area remains unchanged

Current path:

```text
configs/
```

остается текущей compatibility area.

Файлы `configs/*` не переносились в этом шаге.

## 3. Allowed later by approval

Только после отдельного approval можно рассматривать:

```text
configs/app_config.env.example -> config/env/examples/app_config.env.example
configs/integrations.env.example -> config/env/examples/integrations.env.example
```

## 4. Not allowed in this step

Запрещено:

- переносить `configs/*`;
- создавать реальные `.env` файлы;
- менять live env;
- менять env loading;
- менять cron/systemd/docker;
- менять runtime pointers;
- менять deploy scripts;
- переносить `schedule_contract.env`;
- переносить `schedules.cron`.

## 5. Verification

Проверка этого шага:

```bash
rg -n "not an active runtime path|Do not store real env|Live env remains no-touch|separate owner approval" config/env/examples/README.md
python3 -m unittest discover -s tests/unit
```
