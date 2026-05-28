# План подготовки CODEX workspace

Дата плана: 2026-05-02 МСК.

Target workspace: `/Users/pro2kuror/Desktop/CODEX`.

Текущий source of truth: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`.

Этот план не разрешает production changes. Любые изменения live runtime, `/opt/openclaw`, env, cron, systemd, Docker и Telegram routing требуют отдельного approval.

## Принципы

1. Сначала inventory, затем dry-run, затем controlled cutover.
2. Старые абсолютные пути не ломать.
3. Ничего не удалять на первом шаге.
4. Секреты, token/state files, runtime logs/cache/tmp/reports не переносить в git.
5. `agents/sales_agent` не удалять и не переименовывать.
6. `tools/paperclip` считать external dirty repo.
7. Все даты, cron и отчеты указывать в МСК.

## Целевая структура

| Target | Источник | Роль | Первая безопасная стратегия |
| --- | --- | --- | --- |
| `/Users/pro2kuror/Desktop/CODEX/engineer` | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | Canonical code source | Сначала symlink или dry-run copy. Physical move только после path remediation и тестов из нового пути. |
| `/Users/pro2kuror/Desktop/CODEX/control-plane` | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane` | Canonical control-plane docs | Symlink на canonical docs, без второй копии. |
| `/Users/pro2kuror/Desktop/CODEX/tools/paperclip` | `/Users/pro2kuror/Desktop/tools/paperclip` | External tool | Symlink/wrapper. Не коммитить и не чистить dirty state. |
| `/Users/pro2kuror/Desktop/CODEX/archive` | selected archive candidates | Исторические материалы | Только manifest-first archive, без secrets/runtime. |
| `/Users/pro2kuror/Desktop/CODEX/wrappers` | `/Users/pro2kuror/Desktop/Cloudbot` и будущие legacy shims | Старые entrypoints | Ссылки/README для обратимости. |

## Фаза 1: создать CODEX как navigation root

Безопасный первый шаг после этого commit:

1. Создать `/Users/pro2kuror/Desktop/CODEX`.
2. Создать README/manifest внутри CODEX вне git или в отдельном housekeeping контуре.
3. Добавить только symlink-и:
   - `CODEX/engineer -> /Users/pro2kuror/Desktop/OpenClo/projects/engineer`;
   - `CODEX/control-plane -> /Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane`;
   - `CODEX/tools/paperclip -> /Users/pro2kuror/Desktop/tools/paperclip`;
   - `CODEX/wrappers/Cloudbot -> /Users/pro2kuror/Desktop/Cloudbot`.
4. Не менять `/Users/pro2kuror/Desktop/OpenClo`, `/Users/pro2kuror/Desktop/Cloudbot`, `/Users/pro2kuror/Desktop/tools`, `/Users/pro2kuror/Desktop/architect`.

Проверка после фазы:

```bash
cd /Users/pro2kuror/Desktop/CODEX/engineer
git status --short --branch
git diff --check
python3 -m unittest tests.integration.test_app_compatibility_contract
```

## Фаза 2: dry-run copy manifest

Цель: понять, что именно будет скопировано при физическом переносе, не меняя старые пути.

Рекомендуемый dry-run:

```bash
rsync -a --dry-run --itemize-changes \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude 'cache' \
  --exclude 'logs' \
  --exclude 'tmp' \
  --exclude 'reports' \
  --exclude 'data/' \
  --exclude '**/__pycache__/' \
  --exclude '**/node_modules/' \
  --exclude '**/.venv/' \
  --exclude '**/venv/' \
  --exclude '**/dist/' \
  --exclude '**/build/' \
  /Users/pro2kuror/Desktop/OpenClo/projects/engineer/ \
  /Users/pro2kuror/Desktop/CODEX/dry-run/engineer/
```

Dry-run output сохранить как локальный artifact, не в git, если там появятся абсолютные пути к private окружению.

## Фаза 3: path remediation без live cutover

До физического переноса надо убрать или параметризовать runtime-relevant absolute paths:

| Файл | Текущий риск | План |
| --- | --- | --- |
| `configs/schedules.cron` | Hardcoded `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | Подготовить template с `CLOUDBOT_ENGINEER_ROOT`, не применять live cron без approval. |
| `scripts/larisa_finalize.sh` | Hardcoded `cd` в old engineer path | Перевести на вычисление repo root от location скрипта или env override. |
| `tools/control-plane/architect-scripts/scripts/*` | Старые `Cloudbot/architect`, `Cloudbot/engineer`, `architect` paths | Перевести на env override и documented defaults. Не запускать live dashboard scripts без отдельной проверки. |
| `Cloudbot/bin/verify_workspace.sh` | Проверяет старый wrapper path | После создания CODEX добавить CODEX-aware verify script, старый оставить совместимым. |
| docs/control-plane historical docs | Старые утверждения о source of truth | Не переписывать историю массово. Новые docs должны фиксировать актуальный target. |

После каждого изменения:

```bash
git diff --check
python3 -m unittest tests.integration.test_app_compatibility_contract
```

Если меняются shell workflows:

```bash
bash -n <changed-files>
```

## Фаза 4: controlled physical cutover

Выполнять только после успешной фазы 3.

1. Freeze: проверить, что `engineer/dev` или feature branch clean.
2. Snapshot: зафиксировать manifest текущих старых путей.
3. Создать физический `/Users/pro2kuror/Desktop/CODEX/engineer` как git clone/move source с сохранением history.
4. Старый `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` не удалять. Сначала заменить на compatibility symlink только после отдельного approval.
5. `/Users/pro2kuror/Desktop/Cloudbot/engineer` оставить working wrapper или перенаправить на CODEX только после проверок.
6. Запустить тесты из `/Users/pro2kuror/Desktop/CODEX/engineer`.
7. Проверить, что legacy paths еще открываются и `python3 -m agents.*` работает.

Rollback:

- удалить только новые CODEX symlink-и или dry-run copy;
- вернуть wrapper symlink-и на прежние targets;
- не трогать production runtime pointers.

## Фаза 5: archive cleanup

Cleanup делать отдельно, только после controlled cutover:

| Кандидат | Действие |
| --- | --- |
| `/Users/pro2kuror/Desktop/architect` | Archive stub или оставить как historical git shell. Не удалять без manifest. |
| `/Users/pro2kuror/Desktop/OpenClo/archive/restored-workspace` | Сохранить в CODEX/archive manifest. Не добавлять в Cloudbot git. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` | Archive after duplicate confirmation against `engineer/docs/roles/lev_petrovich`. |
| `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` | Archive/experiments after separate classification. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` | Отдельный WHOOP audit перед любым переносом. |

## Wrapper cutover design для `python -m agents.*`

Это следующий технический домен. На этом этапе зафиксирована только read-only map, без изменений runtime wrappers.

| Call site | Сейчас | Целевой canonical вариант | Комментарий |
| --- | --- | --- | --- |
| `infra/orchestrator/workflows/larisa_daily_brief.sh` | `python3 -m agents.larisa_ivanovna --command get_day_brief` | `python3 -m apps.larisa_ivanovna --command get_day_brief` | Нужен contract test на output/exit code. |
| `infra/orchestrator/workflows/larisa_midday_replan.sh` | `python3 -m agents.larisa_ivanovna --command get_midday_replan` | `python3 -m apps.larisa_ivanovna --command get_midday_replan` | Менять только после dry-run. |
| `infra/orchestrator/workflows/larisa_evening_review.sh` | `python3 -m agents.larisa_ivanovna --command get_evening_review` | `python3 -m apps.larisa_ivanovna --command get_evening_review` | Сохранить shim. |
| `infra/orchestrator/workflows/larisa_content_topics.sh` | `python3 -m agents.larisa_ivanovna --command ... --period ...` | `python3 -m apps.larisa_ivanovna --command ... --period ...` | Проверить content/search env отдельно. |
| `infra/orchestrator/workflows/larisa_send_note.sh` | `from agents.larisa_ivanovna.providers.telegram_provider import ...` | `from apps.larisa_ivanovna.providers.telegram_provider import ...` | Import-only cutover candidate. |
| `infra/orchestrator/workflows/sales_morning_report.sh` | `"$PYTHON_BIN" -m agents.lev_petrovich --report sales --send` | `"$PYTHON_BIN" -m apps.lev_petrovich --report sales --send` | Не менять Telegram routing. |
| `infra/orchestrator/workflows/sales_followup.sh` | `python3 -m agents.lev_petrovich --report "$REPORT_TYPE"` | `python3 -m apps.lev_petrovich --report "$REPORT_TYPE"` | Follow-up production path already sensitive; cutover separately. |
| `infra/orchestrator/workflows/sales_weekly_review.sh` | `python3 -m agents.lev_petrovich --report "$REPORT_TYPE"` | `python3 -m apps.lev_petrovich --report "$REPORT_TYPE"` | Нужен report-format contract gate. |
| `infra/orchestrator/workflows/sales_agent_deploy.sh` | `exec python3 -m agents.lev_petrovich --report focus --send` | `exec python3 -m apps.lev_petrovich --report focus --send` | Deploy workflow; require bash syntax and packaging tests. |
| `scripts/run_sales_copilot.py` | subprocess `-m agents.lev_petrovich` | subprocess `-m apps.lev_petrovich` | Keep compatibility fallback until runtime cutover. |
| `shared/contracts/sales_report_format_contract.py` | `FORMATTER_MODULE = "agents.sales_agent.sales_formatter"` | Candidate: `apps.lev_petrovich.legacy_sales_agent.sales_formatter` | Do not change until consumers of metadata are mapped. |

`agents/finansist` shim exists, but listed workflow call sites did not show a current `python3 -m agents.finansist` runtime call.

## Tests для будущего wrapper cutover

Перед изменением call sites:

```bash
python3 -m unittest tests.integration.test_agents_import_guard
python3 -m unittest tests.integration.test_app_compatibility_contract
python3 -m unittest tests.integration.test_release_packaging_contract
```

После изменения shell workflows:

```bash
bash -n infra/orchestrator/workflows/larisa_daily_brief.sh \
  infra/orchestrator/workflows/larisa_midday_replan.sh \
  infra/orchestrator/workflows/larisa_evening_review.sh \
  infra/orchestrator/workflows/larisa_content_topics.sh \
  infra/orchestrator/workflows/larisa_send_note.sh \
  infra/orchestrator/workflows/sales_morning_report.sh \
  infra/orchestrator/workflows/sales_followup.sh \
  infra/orchestrator/workflows/sales_weekly_review.sh \
  infra/orchestrator/workflows/sales_agent_deploy.sh
```

Для deploy/packaging changes:

```bash
bash -n infra/orchestrator/lib.sh \
  infra/orchestrator/workflows/larisa_agent_deploy.sh \
  infra/orchestrator/workflows/sales_agent_deploy.sh
python3 -m unittest tests.integration.test_release_packaging_contract
```

Финальный прогон после CODEX path work:

```bash
python3 -m unittest discover -s tests/unit
python3 -m unittest discover -s tests/integration
cd bot && npm test
cd ..
python3 checks/smoke_test.py
git diff --check
git status --short --branch
```

`npm test` в `bot` и `python3 checks/smoke_test.py` запускать только последовательно.

## Go / no-go

Go для следующего шага: создать CODEX navigation root с symlink-и и README/manifest без удаления старых путей.

No-go для физического переноса сейчас:

- есть absolute path dependencies;
- есть secret/runtime symlinks;
- есть dirty external `tools/paperclip`;
- есть WHOOP standalone с token/state paths;
- старые wrappers нужны для обратимости.
