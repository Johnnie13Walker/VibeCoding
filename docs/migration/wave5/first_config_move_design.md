# First Config Move Design

Дата фиксации: 2026-04-28 МСК.

Статус: design only. Этот документ не переносит config-файлы, не меняет env loading, runtime, cron, systemd, docker или deploy scripts.

## 1. Candidate

Первый возможный config move:

```text
configs/app_config.env.example -> config/env/examples/app_config.env.example
```

Тип:

```text
env example move
```

Это не live env move.

## 2. Почему выбран этот файл

`configs/app_config.env.example` выбран как первый config candidate, потому что:

- это `.env.example`, а не `.env`;
- файл предназначен как шаблон переменных окружения;
- значения должны быть placeholder/redacted;
- он не должен быть active runtime path;
- target `config/env/examples/` уже помечен как examples-only boundary.

## 3. Почему другие config-файлы не входят

| File | Decision | Reason |
| --- | --- | --- |
| `configs/integrations.env.example` | later | Содержит больше integration/secret variable names; нужен отдельный secret-safe review |
| `configs/schedule_contract.env` | blocked | Schedule contract, связан с cron/runtime semantics |
| `configs/schedules.cron` | blocked | Cron template с absolute local path и scheduler semantics |
| `configs/README.md` | keep | Current compatibility boundary marker |

## 4. Current dirty-state blocker

На момент design `configs/app_config.env.example` уже находится в dirty state:

```text
M configs/app_config.env.example
```

Это означает:

- перенос нельзя выполнять молча;
- нужно явно принять текущую версию файла как migration baseline;
- либо сначала отдельно завершить review dirty-state этого файла.

## 5. Exact future scope

Разрешенный будущий scope только после owner approval:

```text
current path:
configs/app_config.env.example

target path:
config/env/examples/app_config.env.example
```

Потенциально изменяемые файлы:

```text
configs/app_config.env.example
config/env/examples/app_config.env.example
```

Никакие другие config-файлы не должны меняться.

## 6. Anti-scope

В рамках будущего move запрещено:

- менять значения переменных;
- добавлять секреты;
- создавать `.env`;
- создавать `.env.local`;
- создавать `.env.production`;
- менять env loading;
- менять live env;
- менять `configs/integrations.env.example`;
- менять `configs/schedule_contract.env`;
- менять `configs/schedules.cron`;
- менять cron/systemd/docker;
- менять runtime pointers;
- менять deploy/rollback/verify scripts;
- менять production code;
- менять imports;
- трогать `/opt/*`, `/etc/*`, `/root/*`, `/home/ops/*`.

## 7. Preconditions before execution

Перед future execution нужно подтвердить:

| Check | Requirement | Status | Blocker |
| --- | --- | --- | --- |
| W5-CONFIG-01 | Owner принимает текущий dirty `configs/app_config.env.example` как baseline | not confirmed | yes |
| W5-CONFIG-02 | Подтверждено, что файл не содержит real secret values | not confirmed | yes |
| W5-CONFIG-03 | Подтверждено, что файл не является live runtime env | not confirmed | yes |
| W5-CONFIG-04 | Target boundary `config/env/examples/README.md` существует | pass | no |
| W5-CONFIG-05 | Unit tests проходят | pass | no |
| W5-CONFIG-06 | `schedule_contract.env` и `schedules.cron` остаются no-touch | pass | no |

Итог:

```text
config move blocked until owner approval and secret-safe review
```

## 8. Checks before future move

Перед будущим approved move:

```bash
sed 's/=.*/=<redacted>/' configs/app_config.env.example
rg -n "config/env/examples|app_config.env.example|configs/app_config.env.example" docs configs config
python3 -m unittest discover -s tests/unit
```

Ожидаемый результат:

- нет secret values в выводе;
- нет ссылок, которые делают `configs/app_config.env.example` active runtime path;
- unit tests проходят.

## 9. Checks after future move

После будущего approved move:

```bash
sed 's/=.*/=<redacted>/' config/env/examples/app_config.env.example
rg -n "configs/app_config.env.example|config/env/examples/app_config.env.example" docs configs config
python3 -m unittest discover -s tests/unit
git status --short configs/app_config.env.example config/env/examples/app_config.env.example
```

Success criteria:

- файл находится в `config/env/examples/`;
- значения не раскрыты;
- unit tests проходят;
- `configs/schedule_contract.env` не изменен;
- `configs/schedules.cron` не изменен;
- live env/runtime/deploy не тронуты.

## 10. Rollback

Rollback:

```text
config/env/examples/app_config.env.example -> configs/app_config.env.example
```

После rollback:

```bash
python3 -m unittest discover -s tests/unit
git status --short configs/app_config.env.example config/env/examples/app_config.env.example
```

Rollback не должен требовать:

- server access;
- deploy;
- restart;
- runtime pointer changes;
- live env changes;
- cron/systemd/docker changes.

## 11. Required approval text

Для фактического переноса нужен отдельный approval:

```text
APPROVE W5-CONFIG-APP-EXAMPLE
Accept current configs/app_config.env.example as migration baseline.
Move only configs/app_config.env.example to config/env/examples/app_config.env.example.
No value changes.
No live env changes.
No runtime/deploy/cron/systemd/docker changes.
Do not touch schedule_contract.env or schedules.cron.
```

## 12. Final verdict

```text
first config move design completed
actual config move blocked
```
