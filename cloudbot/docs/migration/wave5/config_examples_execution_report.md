# Config Examples Execution Report

Дата фиксации: 2026-04-28 МСК.

Статус: completed for approved env example moves.

## 1. Выполненные moves

```text
configs/app_config.env.example -> config/env/examples/app_config.env.example
configs/integrations.env.example -> config/env/examples/integrations.env.example
```

Оба переноса выполнены без изменения содержимого файлов.

## 2. Проверки

### app_config.env.example

Проверки:

```bash
sed 's/=.*/=<redacted>/' config/env/examples/app_config.env.example
rg secret-like patterns config/env/examples/app_config.env.example
python3 -m unittest discover -s tests/unit
```

Результат:

```text
secret-like patterns: no matches
Ran 12 tests
OK
```

### integrations.env.example

Проверки:

```bash
sed 's/=.*/=<redacted>/' config/env/examples/integrations.env.example
rg secret-like patterns config/env/examples/integrations.env.example
python3 -m unittest discover -s tests/unit
```

Результат:

```text
secret-like patterns: no matches
Ran 12 tests
OK
```

## 3. Что не трогалось

Не менялись:

- `configs/schedule_contract.env`;
- `configs/schedules.cron`;
- live env;
- env loading;
- runtime pointers;
- cron/systemd/docker;
- deploy/rollback/verify scripts;
- production code;
- `agents/*`;
- `cloudbot/*`;
- `/opt/*`, `/etc/*`, `/root/*`, `/home/ops/*`.

## 4. Текущий config examples state

Target examples:

```text
config/env/examples/app_config.env.example
config/env/examples/integrations.env.example
```

Current compatibility path:

```text
configs/README.md
```

Runtime-sensitive files остаются в текущей зоне:

```text
configs/schedule_contract.env
configs/schedules.cron
```

## 5. Verdict

```text
config examples migration completed
schedule and cron files remain blocked
next safe step: env examples contract
```
