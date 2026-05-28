# Карта системы Cloudbot

Этот документ дополняет `ARCHITECTURE.md` и `docs/ARCHITECTURE.md` и фиксирует не только логическую схему, но и стартовую операционную реальность текущего runtime-репозитория.

## История миграции 2026-05-28

Runtime-код Cloudbot перенесён из `~/Desktop/OpenClo/projects/engineer/` в монорепо `~/Desktop/VibeCoding/`, в подпапку `cloudbot/`. Перенос сделан через `git subtree add --prefix=cloudbot codex-base/dev` — история коммитов engineer-репо (`codex-base.git`) сохранена в git log VibeCoding. Старая папка `OpenClo/projects/engineer/` остаётся на диске до полного удаления (после переписи deploy-bundle под новый путь).

## Канонический репозиторий

- **Локальный runtime-репозиторий:** `/Users/pro2kuror/Desktop/VibeCoding/cloudbot`
- **Внутри монорепо:** `VibeCoding/` (origin `github.com/Johnnie13Walker/VibeCoding`)
- **Историческое происхождение subtree:** `github.com/Johnnie13Walker/codex-base.git` (после миграции 2026-05-28 этот репо к боевой работе не используется, push идёт в VibeCoding)
- Боевая работа должна вестись в этом репозитории, если отдельно не подтвержден другой канонический runtime.

## Смежные контуры на текущей машине

### Внутри VibeCoding/cloudbot/

- `cloudbot/incubator/openclaw-extensions/` — инкубационный sandbox: Telegram CRM-lite, Search, Steps, Discord-hub, DevOps-SRE, providers, workflows (перенесён 2026-05-28 из `~/Desktop/OpenClo/incubator/`). Не канонический runtime, прототипы.
- `cloudbot/docs/legacy/commercial-director/` — historical knowledge layer retired-проекта «Коммерческий директор»; роль перенесена в `apps/lev_petrovich/` (перенесён 2026-05-28 из `~/Desktop/OpenClo/projects/commercial-director/`).

### Внешние артефакты на десктопе

- `~/Desktop/engineer-backup-2026-05-28/` — снапшот канонического runtime до миграции subtree merge (`codex-base.git` clone). Удалится после переписи VPS deploy-bundle под путь VibeCoding/cloudbot/.
- `~/Desktop/BelberryArchive/` — архив агентской работы (64 клиентских папки + брифы + брендбук + конкурентная разведка). Не в git по решению владельца. См. [[reference-belberry-archive-desktop]] в memory.

### Retired контуры (полностью удалены 2026-05-28)

- `~/Desktop/architect/` — control-plane / documentation workspace. Git-история сохранена в `shared/archive/architect-history-2026-04-28.bundle`.
- `~/Desktop/OpenClo/archive/restored-workspace/` — пустой архивный git-контур (был detached HEAD без коммитов).
- `~/Desktop/OpenClo/projects/whoop/` — стояла пустой к моменту миграции, удалена.

## Что не считать каноническим runtime без отдельной миграции

- `cloudbot/incubator/openclaw-extensions/` — sandbox / прототипы. Перенос в production — через явный design + смену контракта.
- `cloudbot/docs/legacy/*` — историческая документация, не source of truth.
- `logs`, `reports`, `tmp`, `cache` внутри runtime-репозитория — runtime-артефакты.

Дополнительная диагностика:

- На `2026-05-28` после миграции в `~/Desktop/` остался только один git-контур: `engineer-backup-2026-05-28/` (`codex-base.git` clone) — backup до переписи VPS deploy-bundle.
- Бывший `~/Desktop/architect/` git-контур заархивирован в `shared/archive/architect-history-2026-04-28.bundle`.
- Бывший `~/Desktop/OpenClo/archive/restored-workspace/` был detached HEAD без коммитов — git bundle создать не удалось (пустой репо), удалён.

## Подтвержденные live auxiliary-контуры на сервере

Помимо канонического runtime-репозитория, на live-хосте подтверждены ещё несколько активных operational-контуров:

- `/opt/cloudbot-runtime/larisa/current` — канонический live runtime Ларисы.
- `/opt/cloudbot-runtime/current` — отдельный generic runtime pointer; на `2026-03-29` используется server wrapper'ами sales (`/usr/local/bin/cloudbot-sales-*.sh`).
- `/etc/cron.d/cloudbot-sales-reports` — активный sales-cron слой с daily/check/followup/weekly задачами.
- `/etc/cron.d/openclaw-whoop-report` + `/usr/local/bin/send_whoop_report.py` — активный WHOOP reporting contour.
- `/etc/cron.d/openclaw-todo-digest` + `/root/.openclaw/workspace/todo-integration` — legacy server-only scheduler contour; `digest:evening`, `reminders:tick` и `execution:tick` всё ещё активны.
- `cloudbot-bitrix-app.service` с `WorkingDirectory=/opt/openclaw` и `ExecStart=/usr/bin/python3 /opt/openclaw/local/bitrix_app_server.py` — отдельный server-only Bitrix app contour.

## Ключевые приложения и compatibility layers

### `apps/larisa_ivanovna`

Персональный ассистентный контур:

- дневной бриф;
- встречи;
- задачи;
- погода;
- поиск;
- новости;
- планирование дня;
- создание встречи.

Compatibility shim:

- `agents/larisa_ivanovna`

### `apps/lev_petrovich`

Лев Петрович / Sales Copilot:

- управленческие sales-отчеты;
- аналитика Bitrix;
- сигналы риска по продажам;
- недельные и follow-up отчеты;
- отдельный bridge к live server state.

Архитектурная оговорка:

- `apps/lev_petrovich` — канонический runtime entrypoint роли.
- `apps/lev_petrovich/legacy_sales_agent` — канонический implementation path для Sales legacy runtime layer.
- `agents/lev_petrovich` — compatibility shim.
- `agents/sales_agent` — временный compatibility-слой до полного переноса legacy-имени.

### `agents/news_agent`

Контур новостного дайджеста:

- RSS ingestion;
- фильтрация low-signal статей;
- сборка итогового текста;
- health-проверка news runtime.

### `agents/architect`

Контур архитектурного контроля:

- ревизия архитектуры;
- контроль runtime-путей;
- контроль change-control;
- приемка инженерных изменений.

## Основные интеграции

- Telegram
- OpenAI
- Bitrix24
- Todoist
- WHOOP
- RSS / Web Search
- Wazzup
- SSH / server state для live bridge отдельных контуров

## Основные контуры исполнения

### Telegram path

`cloudbot/bot/telegram/telegram_handler.py`
-> `cloudbot/orchestrator/orchestrator.py`
-> `cloudbot/orchestrator/router.py`
-> `cloudbot/workflows/*`
-> `apps/*`, compatibility `agents/*` или `cloudbot/providers/*`
-> ответ в Telegram

### Cron path

`configs/schedules.cron`
-> `infra/orchestrator/run_workflow.sh`
-> `infra/orchestrator/workflows/*.sh`
-> `python3 -m apps.*`, compatibility `python3 -m agents.*` или `scripts/*`
-> отчет в `reports/*`

### Manual operator path

- `make *`
- `infra/orchestrator/run_workflow.sh <workflow>`
- точечные canonical app CLI через `python3 -m apps.*`
- compatibility CLI через `python3 -m agents.*`

Ручной путь допустим для диагностики и controlled run. Боевой сценарий при наличии workflow должен идти через оркестратор.

### Health path

`/health`
-> `cloudbot/workflows/system_health.py`
-> `cloudbot/devops/system_health.py`
-> проверка internet / Telegram / OpenAI / Bitrix / RSS / news agent

### Sales live bridge path

`cloudbot/workflows/sales_brief.py`
-> `scripts/run_sales_copilot.py`
-> SSH на сервер
-> чтение live env/state
-> локальный запуск canonical `apps.lev_petrovich` или compatibility `agents.lev_petrovich` по wrapper-контракту

Этот контур критичен, потому что часть runtime-правды находится вне локального репозитория.

### Server delivery path

Целевой контур для agent runtime:

- source of truth: `origin -> https://github.com/Johnnie13Walker/codex-base.git`
- deploy bundle: `infra/orchestrator/workflows/larisa_agent_deploy.sh` и `infra/orchestrator/workflows/sales_agent_deploy.sh`
- release manifest: `infra/orchestrator/lib.sh::cloudbot_runtime_files`
- server releases: `/opt/cloudbot-runtime/larisa/releases/<release_id>`
- active runtime: `/opt/cloudbot-runtime/larisa/current`

Текущий статус:

- локальные deploy-скрипты и server wrappers уже переведены на release-based модель
- live server для `larisa` использует `/opt/cloudbot-runtime/larisa/current`
- scoped deploy path Ларисы защищён remote lock `/opt/cloudbot-runtime/larisa/.deploy.lock`
- operational rollback ingress: `infra/orchestrator/workflows/cloudbot_runtime_rollback.sh`
- operational verify ingress: `infra/orchestrator/workflows/cloudbot_runtime_verify.sh`
- legacy каталоги `/home/ops/cloudbot-larisa-agent` и `/home/ops/cloudbot-news-agent` оставлены только для отчётов и обратной совместимости
- `news` использует явный server env override в `/etc/openclaw/news_agent.env`
- `/opt/openclaw` остаётся отдельным platform/env/state контуром и не является источником agent-кода
- rollback/unlock/verify для Ларисы должны использовать scoped runtime `/opt/cloudbot-runtime/larisa/*` по умолчанию
- общий `/opt/cloudbot-runtime/current` не является каноническим runtime-путём Ларисы и на live-хосте сейчас используется отдельными sales-wrapper'ами

## Production-critical зоны

- `cloudbot/bot/telegram/*`
- `cloudbot/orchestrator/*`
- `cloudbot/workflows/*`
- `apps/larisa_ivanovna/*`
- `apps/lev_petrovich/*`
- `apps/lev_petrovich/legacy_sales_agent/*`
- `agents/larisa_ivanovna/*` как compatibility shim
- `agents/lev_petrovich/*` как compatibility shim
- `agents/sales_agent/*` как временный compatibility-слой
- `agents/news_agent/*`
- `cloudbot/providers/*`
- `infra/orchestrator/*`
- `configs/schedules.cron`
- `.env.integrations`, `infra/remote-ops.env` и серверный env/state как внешние runtime-зависимости

## Legacy / archive зоны

- `cloudbot/workflows/*/index.js` — compatibility/legacy workflow layer, требует явного статуса для каждого сценария.
- `cloudbot/orchestrator/router/index.js` — дополнительный JS-контур маршрутизации, не должен считаться каноническим автоматически.
- `/Users/pro2kuror/Desktop/OpenClo/archive/*` — архив вне канонического runtime.
- `/Users/pro2kuror/Desktop/OpenClo/incubator/*` — экспериментальные расширения вне канонического runtime.

## Зоны повышенного архитектурного риска

- Расхождение между Python workflow-контуром и legacy JS-контуром.
- Расхождение между локальным кодом и server state в Sales Copilot bridge.
- Расхождение между cron path и Telegram path для одного и того же сценария.
- Риск перепутать scoped lock Ларисы `/opt/cloudbot-runtime/larisa/.deploy.lock` и generic lock `/opt/cloudbot-runtime/.deploy.lock`.
- Неявный статус legacy-контуров и внешних папок `archive` / `incubator`.
