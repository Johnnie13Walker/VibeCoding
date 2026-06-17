# CODEX navigation root

Дата: 2026-05-02 09:24:47 МСК.

Статус: создан navigation root `/Users/pro2kuror/Desktop/CODEX`.

Это не physical cutover и не перенос source-кода. Старые пути сохранены, production runtime не изменялся.

## Что создано

| Путь | Тип | Target / назначение |
| --- | --- | --- |
| `/Users/pro2kuror/Desktop/CODEX` | directory | Navigation root. |
| `/Users/pro2kuror/Desktop/CODEX/README.md` | local manifest | Локальный README вне Cloudbot git. |
| `/Users/pro2kuror/Desktop/CODEX/archive` | directory | Пустой placeholder для будущего manifest-first archive. |
| `/Users/pro2kuror/Desktop/CODEX/tools` | directory | Container для external tools. |
| `/Users/pro2kuror/Desktop/CODEX/wrappers` | directory | Container для legacy wrappers. |
| `/Users/pro2kuror/Desktop/CODEX/engineer` | symlink | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`. |
| `/Users/pro2kuror/Desktop/CODEX/control-plane` | symlink | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane`. |
| `/Users/pro2kuror/Desktop/CODEX/tools/paperclip` | symlink | `/Users/pro2kuror/Desktop/tools/paperclip`. |
| `/Users/pro2kuror/Desktop/CODEX/wrappers/Cloudbot` | symlink | `/Users/pro2kuror/Desktop/Cloudbot`. |

## Что не менялось

- `/Users/pro2kuror/Desktop/OpenClo`;
- `/Users/pro2kuror/Desktop/Cloudbot`;
- `/Users/pro2kuror/Desktop/tools`;
- `/Users/pro2kuror/Desktop/architect`;
- `/opt/openclaw`;
- `/opt/cloudbot-runtime/*`;
- env files, token files, cron, systemd, Docker, Telegram token/chat routing.

## Проверки по шагам

После создания directories:

```bash
ls -la /Users/pro2kuror/Desktop/CODEX
git diff --check
python3 -m unittest tests.integration.test_app_compatibility_contract
```

Результат: OK.

После создания symlink map:

```bash
find /Users/pro2kuror/Desktop/CODEX -maxdepth 3 -type l -ls
git -C /Users/pro2kuror/Desktop/CODEX/engineer status --short --branch
git diff --check
python3 -m unittest tests.integration.test_app_compatibility_contract
```

Результат: OK.

После добавления local `/Users/pro2kuror/Desktop/CODEX/README.md`:

```bash
sed -n '1,220p' /Users/pro2kuror/Desktop/CODEX/README.md
git diff --check
python3 -m unittest tests.integration.test_app_compatibility_contract
```

Результат: OK.

Проверка работы из `CODEX/engineer`:

```bash
pwd
git rev-parse --show-toplevel
git status --short --branch
python3 -m unittest tests.integration.test_agents_import_guard tests.integration.test_app_compatibility_contract
```

Результат: OK. `pwd` и `git rev-parse --show-toplevel` резолвятся в `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`, что ожидаемо для symlink-first navigation root.

## Rollback

Rollback этого шага не затрагивает source/runtime:

```bash
rm /Users/pro2kuror/Desktop/CODEX/engineer
rm /Users/pro2kuror/Desktop/CODEX/control-plane
rm /Users/pro2kuror/Desktop/CODEX/tools/paperclip
rm /Users/pro2kuror/Desktop/CODEX/wrappers/Cloudbot
rm /Users/pro2kuror/Desktop/CODEX/README.md
rmdir /Users/pro2kuror/Desktop/CODEX/archive
rmdir /Users/pro2kuror/Desktop/CODEX/tools
rmdir /Users/pro2kuror/Desktop/CODEX/wrappers
rmdir /Users/pro2kuror/Desktop/CODEX
```

Rollback выполнять только вручную и только если navigation root больше не нужен.

## Следующий шаг

Следующий безопасный домен: path remediation без live cutover.

Кандидаты:

- `configs/schedules.cron`;
- `scripts/larisa_finalize.sh`;
- `tools/control-plane/architect-scripts/scripts/*`;
- будущий CODEX-aware verify script.

Перед любым изменением runtime-relevant paths нужен отдельный diff и тест после каждого шага.
