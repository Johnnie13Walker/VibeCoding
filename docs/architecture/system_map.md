# Карта системы OpenClo / Cloudbot

Этот документ дополняет `ARCHITECTURE.md` и `docs/ARCHITECTURE.md` и фиксирует не только логическую схему, но и стартовую операционную реальность текущего runtime-репозитория.

## Канонический репозиторий

- Локальный runtime-репозиторий: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- Git remote: `origin -> https://github.com/Johnnie13Walker/codex-base.git`
- Боевая работа должна вестись в этом репозитории, если отдельно не подтвержден другой канонический runtime.

## Смежные контуры на текущей машине

- `/Users/pro2kuror/Desktop/architect` — control-plane / documentation workspace; это не runtime-код, а слой контрактов, чеклистов и статусов.
- `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` — внешний локальный knowledge/migration contour без `.git`; по зафиксированному контракту больше не должен считаться source of truth после переноса роли в `apps/lev_petrovich`.
- `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` — отдельный локальный WHOOP-модуль без `.git`, со своим `.venv` и скриптами; это standalone/sandbox контур, а не канонический runtime Cloudbot без отдельного deploy-контракта.

## Что не считать каноническим runtime без отдельной миграции

- `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` — внешний локальный контур без git-источника; использовать только как вспомогательный knowledge/archive слой.
- `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` — локальный standalone WHOOP sandbox; live `openclaw-whoop-report` сейчас идёт не из этой папки.
- `/Users/pro2kuror/Desktop/OpenClo/archive/restored-workspace` — архивный контур.
- `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` — инкубационный и экспериментальный контур.
- `logs`, `reports`, `tmp`, `cache` внутри runtime-репозитория — runtime-артефакты, а не source of truth.

Дополнительная диагностика:

- Полный scan `find /Users/pro2kuror/Desktop -name .git -type d` на `2026-03-29` дал только три git-контура: `architect`, `projects/engineer` и архивный `archive/restored-workspace`.
- `/Users/pro2kuror/Desktop/OpenClo/archive/restored-workspace` содержит отдельный `.git`, но сейчас находится в detached `HEAD` и должен считаться историческим архивом.
- `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` не содержит `.git` и представляет собой набор экспериментальных модулей/прототипов.

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
- deploy bundle: `infra/orchestrator/workflows/larisa_agent_deploy.sh` и `infra/orchestrator/workflows/news_agent_deploy.sh`
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
