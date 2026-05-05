# Inventory подготовки CODEX workspace

Дата inventory: 2026-05-02 09:14:36 МСК.

Рабочая ветка: `codex/codex-workspace-consolidation`.

Цель: read-only inventory текущих Desktop-контуров перед подготовкой единой рабочей папки `/Users/pro2kuror/Desktop/CODEX`.

Production runtime, `/opt/openclaw`, live env, cron, systemd, Docker, Telegram token/chat routing не изменялись.

## Проверенные папки

| Путь | Назначение | Размер | Файлы без `.git`/`node_modules`/venv/dist/build | Git status | Вывод |
| --- | --- | ---: | ---: | --- | --- |
| `/Users/pro2kuror/Desktop/OpenClo` | Старый общий workspace OpenClo. Внутри находится canonical repo `projects/engineer`, sandbox WHOOP, старые/архивные контуры и incubator. | 55M | 1075 | root не является git repo | Сохранять как старый контур до controlled cutover. Source of truth только вложенный `projects/engineer`. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | Канонический code source of truth Cloudbot/OpenClo. | входит в OpenClo | входит в OpenClo | `## codex/codex-workspace-consolidation`, чисто до создания этих документов | Основной контур для изменений, тестов, docs/control-plane и release packaging. |
| `/Users/pro2kuror/Desktop/Cloudbot` | Wrapper/navigation layer. | 8K | 2 | не git repo | Оставить как wrapper. Не считать source of truth. |
| `/Users/pro2kuror/Desktop/tools` | Внешние инструменты. Сейчас содержит `paperclip`. | 869M | 1273 | root не является git repo | Не смешивать с Cloudbot source. Можно подключать в CODEX как external tool/wrapper. |
| `/Users/pro2kuror/Desktop/tools/paperclip` | Отдельный git-контур Paperclip. | входит в tools | входит в tools | `## master...origin/master`, много modified файлов | Dirty external repo. Не переносить и не коммитить в рамках Cloudbot consolidation. |
| `/Users/pro2kuror/Desktop/architect` | Legacy docs workspace stub. | 37M | 5 | `## codex/docs-bootstrap`, без modified/untracked в `git status --short --branch` | Больше не source of truth. Содержит `.git`, `.gitignore`, `README.md`, `.serena` local metadata. |

`/Users/pro2kuror/Desktop/CODEX` на момент inventory отсутствует.

## Git-контуры

| Git root | Remote | Состояние |
| --- | --- | --- |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | `https://github.com/Johnnie13Walker/codex-base.git` | Рабочая ветка `codex/codex-workspace-consolidation`, создана от актуального `dev`. |
| `/Users/pro2kuror/Desktop/tools/paperclip` | `https://github.com/paperclipai/paperclip.git` | Dirty external repo: изменены файлы в `server`, `ui` и onboarding assets. Не трогать в этом этапе. |
| `/Users/pro2kuror/Desktop/architect` | remote отсутствует | Legacy stub branch `codex/docs-bootstrap`. |
| `/Users/pro2kuror/Desktop/OpenClo/archive/restored-workspace` | remote отсутствует | `No commits yet on master`, все файлы untracked. Архивный восстановленный workspace. |

## Symlink map

| Symlink | Target | Классификация |
| --- | --- | --- |
| `/Users/pro2kuror/Desktop/Cloudbot/engineer` | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | Wrapper на canonical repo. |
| `/Users/pro2kuror/Desktop/Cloudbot/paperclip` | `/Users/pro2kuror/Desktop/tools/paperclip` | Wrapper на external tool. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.integrations` | `/Users/pro2kuror/.config/openclo/assistant/.env.integrations` | Secret/env no-touch. Не переносить в git. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cache` | `/Users/pro2kuror/Library/Application Support/OpenClo/assistant/cache` | Runtime/cache no-touch. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/logs` | `/Users/pro2kuror/Library/Application Support/OpenClo/assistant/logs` | Runtime/logs no-touch. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/tmp` | `/Users/pro2kuror/Library/Application Support/OpenClo/assistant/tmp` | Runtime/tmp no-touch. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/reports` | `/Users/pro2kuror/Library/Application Support/OpenClo/assistant/reports` | Runtime/reports no-touch. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop/.env` | `/Users/pro2kuror/.config/openclo/whoop/.env` | Secret/env no-touch. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop/.whoop_tokens.json` | `/Users/pro2kuror/Library/Application Support/OpenClo/whoop/.whoop_tokens.json` | Token state no-touch. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop/whoop-state.json` | `/Users/pro2kuror/Library/Application Support/OpenClo/whoop/whoop-state.json` | Runtime state no-touch. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop/progress_tracker.sqlite3` | `/Users/pro2kuror/Library/Application Support/OpenClo/whoop/progress_tracker.sqlite3` | Runtime DB no-touch. |
| `/Users/pro2kuror/Desktop/tools/paperclip/node_modules/*` | `.pnpm/...` | Package-manager symlinks. Exclude from consolidation. |

## Секреты и потенциальные секреты

Содержимое секретных файлов не раскрывалось. Зафиксированы только пути и классы риска.

| Путь | Тип риска | Решение |
| --- | --- | --- |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.integrations` | Symlink на private env | Не переносить в git. При dry-run copy исключать. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop/.env` | Symlink на private env | Не переносить. WHOOP standalone требует отдельного audit. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop/.whoop_tokens.json` | Token state symlink | Не переносить. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop/whoop-state.json` | Runtime health state symlink | Не переносить как source. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop/progress_tracker.sqlite3` | Runtime DB symlink | Не переносить как source. |
| `/Users/pro2kuror/Desktop/tools/paperclip/data/secrets/master.key` | Реальный secret key во внешнем repo | Не переносить, не коммитить, не копировать в CODEX source. |
| `*.env.example`, `.env.integrations.example` | Примеры env | Можно хранить в git только как templates без реальных значений. |
| `server_snapshots/*` внутри engineer | Исторические снимки server/runtime | Treat as potentially sensitive evidence. Не публиковать новые snapshots без отдельного review. |

## Runtime, logs, cache, build artifacts

| Контур | Найдено | Решение |
| --- | --- | --- |
| `engineer` | Symlink-и `cache`, `logs`, `tmp`, `reports`; ignored `data/`; ignored `apps/logs/sales_daily_history.json`; `cloudbot/logs` | Не считать source. При dry-run copy исключать runtime/log/cache/tmp/report paths. |
| `whoop` | `.venv`, token/env/state symlinks, sqlite state | Не переносить без отдельного WHOOP audit. |
| `commercial-director` | `assistant/output`, `assistant/tmp`, `.serena` | Archive candidate, не source of truth. |
| `incubator/openclaw-extensions` | `data/dialog-state.json`, `devops-sre/logs`, docx/png/generated assets | Archive/experiments candidate. Не runtime source. |
| `tools/paperclip` | `node_modules`, many `dist`, package-manager symlinks, `data/secrets/master.key` | External dirty repo. Не переносить как Cloudbot source. |
| `architect` | `.serena` local metadata | Не source. При archive можно сохранить вне git. |

## Дубликаты

Read-only checksum pass показал повторяющиеся файлы без `.git`, `node_modules`, venv, dist/build/cache/logs/tmp.

| Дубликат | Примеры | Классификация |
| --- | --- | --- |
| `commercial-director/core` и `engineer/docs/roles/lev_petrovich` | playbooks, templates, Bitrix integration docs, `TOOLS.md`, `SOUL.md`, report fixtures | Старый sales/knowledge contour уже перенесен в canonical docs/roles. `commercial-director` является archive candidate. |
| `Cloudbot/*` wrappers | `Cloudbot/engineer`, `Cloudbot/paperclip` | Symlink-дубли, не реальные source copies. |
| `engineer/docs/control-plane/architect/artifacts` | Несколько одинаковых audit artifacts с разными именами | Historical evidence, не runtime source. |
| `tools/paperclip` internal fixtures/configs | `tsconfig.json`, plugin examples, test helpers | Нормальная внутренняя структура external repo, вне Cloudbot consolidation. |

Вывод: source-of-truth дублей в `/Users/pro2kuror/Desktop/architect` после cleanup не найдено; оставшийся stub не должен получать новые документы.

## Абсолютные пути

### Runtime/config/scripts в canonical repo

Найдены оставшиеся абсолютные пути вне `docs/**`, `archive/**`, `server_snapshots/**`:

- `configs/schedules.cron` использует `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`.
- `scripts/larisa_finalize.sh` делает `cd "/Users/pro2kuror/Desktop/OpenClo/projects/engineer"`.
- `tools/control-plane/architect-scripts/scripts/*` содержит старые `/Users/pro2kuror/Desktop/architect`, `/Users/pro2kuror/Desktop/Cloudbot/architect`, `/Users/pro2kuror/Desktop/Cloudbot/engineer`.
- `ops/owner_operating_contract_MSK.md` и `ops/runbook_openclaw_security_profile_MSK.md` фиксируют старые canonical paths.

### Local crontab

`crontab -l` прочитан только read-only. В нем есть `CRON_TZ=Europe/Moscow`, но managed jobs закомментированы и помечены как disabled:

- старый local `agent_commit` через `/Users/pro2kuror/Desktop/Cloudbot/engineer`;
- старый local `larisa_daily_brief` через `/Users/pro2kuror/Desktop/Cloudbot/engineer`;
- старый local `news_digest` через `/Users/pro2kuror/Desktop/Cloudbot/engineer`;
- комментарий, что Sales Copilot / Фокус РОПа перенесены на server cron.

Изменений cron не выполнялось.

### Docs

В historical docs много ссылок на:

- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`;
- `/Users/pro2kuror/Desktop/Cloudbot`;
- `/Users/pro2kuror/Desktop/architect`;
- старые утверждения, что docs/control-plane находился в `/Users/pro2kuror/Desktop/architect`.

Новые документы должны считать source of truth таким:

- code/runtime/tests/migration docs: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`;
- control-plane: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane`;
- wrapper: `/Users/pro2kuror/Desktop/Cloudbot`;
- target workspace: `/Users/pro2kuror/Desktop/CODEX`.

### Incubator

`OpenClo/incubator/openclaw-extensions` содержит старые absolute paths к собственным `.env`, WHOOP sandbox и systemd examples. Этот контур не является canonical runtime source и должен идти в archive/experiments только после отдельной классификации.

## Source of truth

| Область | Source of truth |
| --- | --- |
| Cloudbot code/tests/workflows/deploy docs | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` |
| Control-plane docs/scripts после миграции | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane` и `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/tools/control-plane` |
| Larisa canonical app | `apps/larisa_ivanovna` |
| Lev canonical app | `apps/lev_petrovich` |
| Sales temporary compatibility layer | `agents/sales_agent` shim плюс `apps/lev_petrovich/legacy_sales_agent` canonical legacy compatibility layer |
| Finansist canonical app | `apps/finansist` |

## Wrapper

| Путь | Статус |
| --- | --- |
| `/Users/pro2kuror/Desktop/Cloudbot` | Wrapper/navigation layer. Оставить до отдельного wrapper cutover. |
| `/Users/pro2kuror/Desktop/Cloudbot/engineer` | Symlink на current canonical repo. |
| `/Users/pro2kuror/Desktop/Cloudbot/paperclip` | Symlink на external Paperclip repo. |

## Кандидаты на перенос в CODEX

| Target | Источник | Стратегия первого шага |
| --- | --- | --- |
| `/Users/pro2kuror/Desktop/CODEX/engineer` | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | Сначала symlink или dry-run copy без удаления старого пути. Physical move только после path remediation и полного тестового прогона. |
| `/Users/pro2kuror/Desktop/CODEX/control-plane` | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane` | Сначала symlink на canonical docs/control-plane, чтобы не плодить копии. |
| `/Users/pro2kuror/Desktop/CODEX/tools/paperclip` | `/Users/pro2kuror/Desktop/tools/paperclip` | Только wrapper/symlink на external dirty repo. Не смешивать git histories. |
| `/Users/pro2kuror/Desktop/CODEX/wrappers/Cloudbot` | `/Users/pro2kuror/Desktop/Cloudbot` | Сохранить как legacy wrapper reference. |
| `/Users/pro2kuror/Desktop/CODEX/archive` | selected archive candidates | Только после отдельного archive manifest. Не копировать secrets/runtime. |

## Кандидаты на archive

| Путь | Условие |
| --- | --- |
| `/Users/pro2kuror/Desktop/architect` | Можно архивировать как stub только после отдельного решения. Новые source docs сюда не добавлять. |
| `/Users/pro2kuror/Desktop/OpenClo/archive/restored-workspace` | Уже archive; можно сохранить в CODEX/archive manifest без включения в git. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` | Archive candidate: много дублей уже есть в `engineer/docs/roles/lev_petrovich`. |
| `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` | Archive/experiments candidate. Требует отдельной классификации, потому что есть env examples, systemd examples, WHOOP references. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` | Не archive автоматически. Сначала отдельный WHOOP audit из-за env/token/state symlinks. |

## No-touch зоны

- `/opt/openclaw` без отдельного server-only audit.
- `/opt/cloudbot-runtime/*` и production runtime symlinks без отдельного approval.
- live env files: `.env`, `.env.*`, `.env.integrations`, token/state files.
- cron/systemd/Docker/Telegram token/chat routing без отдельного approval.
- `agents/sales_agent`: active temporary compatibility shim, не legacy для удаления.
- `apps/lev_petrovich/legacy_sales_agent`: canonical legacy compatibility layer для Sales.
- dirty external repo `/Users/pro2kuror/Desktop/tools/paperclip`.
- runtime/cache/log/tmp/report/data directories and symlinks.
- `.git` directories and git histories.

## Готовность к физическому переносу

Статус: не готово к физическому переносу.

Причины:

1. В canonical repo и local crontab/docs/scripts остаются absolute path dependencies на `OpenClo`, `Cloudbot` и `architect`.
2. Есть secret/runtime symlinks, которые нельзя переносить как source.
3. `/Users/pro2kuror/Desktop/tools/paperclip` является dirty external git repo и не должен смешиваться с Cloudbot.
4. WHOOP standalone содержит env/token/state symlinks и требует отдельного audit.
5. Старые пути должны оставаться рабочими до controlled cutover.

Готово к следующему безопасному шагу: создать dry-run/wrapper strategy для `/Users/pro2kuror/Desktop/CODEX` без удаления старых папок и без изменения production runtime.
