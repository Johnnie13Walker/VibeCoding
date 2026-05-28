# Проект безопасной реорганизации OpenCloud / Cloudbot

Дата: 2026-04-23 МСК  
Режим: архитектурный проект, без применения изменений.

Ограничения:

- ничего не удалять;
- ничего не перемещать;
- ничего не переименовывать;
- ничего не коммитить;
- ничего не деплоить;
- ничего не перезапускать;
- не менять `cron`, `systemd`, `docker`, `env`, symlink, runtime pointers;
- этот документ описывает target state и migration plan, но не выполняет миграцию.

## 1. Executive recommendation

Рекомендация: делать **частичный rebuild** в новой чистой структуре, но не переписывать систему с нуля.

Что делать:

- зафиксировать текущую систему как baseline;
- отделить `apps/` для Ларисы и Льва от `shared/`;
- развести env по агентам;
- развести runtime pointers по агентам;
- оставить legacy-контуры временно, пока не будет доказан полный cutover;
- переносить слоями, с проверкой обоих Telegram-контуров после каждой волны.

Чего не делать:

- не переносить физически `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` до подготовки target branch/target workspace;
- не менять одновременно Ларису и Льва;
- не удалять `agents/sales_agent`, пока `agents/lev_petrovich` полностью не заменит compatibility layer;
- не трогать server-only integrations без отдельной live dependency map;
- не переключать `/opt/cloudbot-runtime/*/current` до smoke-check и rollback plan;
- не смешивать cleanup docs, env и runtime в одной волне.

Почему:

- рабочее ядро уже есть: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`;
- live runtime на сервере уже разделен частично:
  - Лариса: `/opt/cloudbot-runtime/larisa/current`;
  - Лев/Sales: `/opt/cloudbot-runtime/current`;
- проблема не в отсутствии кода, а в смешении prod/dev/archive/incubator, shared env, shared providers/orchestrator и исторических entrypoint'ах.

## 2. Internal contradictions in the audit

1. **`Cloudbot` выглядит как проект, но фактически это symlink-обертка.**
   - `/Users/pro2kuror/Desktop/Cloudbot/engineer -> /Users/pro2kuror/Desktop/OpenClo/projects/engineer`
   - `/Users/pro2kuror/Desktop/Cloudbot/architect -> /Users/pro2kuror/Desktop/architect`
   - Вывод: `Cloudbot` удобен как входная папка, но не source of truth.

2. **Папки из запроса и реальные имена не совпадают.**
   - Запрошено: `~/Desktop/OpenCloud`
   - Найдено: `/Users/pro2kuror/Desktop/OpenClo`
   - Запрошено: `~/Desktop/Архитект`
   - Найдено: `/Users/pro2kuror/Desktop/architect`
   - Запрошено: `~/Desktop/Tools`, найдено также `/Users/pro2kuror/Desktop/tools`; на текущей файловой системе это один контур по фактическому содержимому.

3. **В раннем аудите server live сначала был не подтвержден из-за proxy, затем подтвержден прямым SSH.**
   - `cloudbot-ssh-proxy` зависит от локального SOCKS/proxy `127.0.0.1:2080`, который не слушал.
   - Прямой SSH подтвердил live-карту сервера.
   - Вывод: для future ops нужно либо восстановить proxy-alias, либо официально зафиксировать прямой SSH route как read-only audit path.

4. **Лариса уже отделена runtime pointer'ом, но не полностью отделена архитектурно.**
   - Сервер: `/opt/cloudbot-runtime/larisa/current`
   - Локально: Лариса все еще использует shared `cloudbot/orchestrator`, `cloudbot/providers`, `.env.integrations`.

5. **Лев Петрович канонизирован как роль, но `agents/sales_agent` остается рабочим compatibility layer.**
   - Canonical role: `agents/lev_petrovich`
   - Compatibility: `agents/sales_agent`
   - Вывод: удалять или резко переносить `sales_agent` нельзя.

6. **`/opt/cloudbot-runtime/current` называется generic current, но фактически сейчас обслуживает Sales/Льва.**
   - Это риск naming ambiguity.
   - Target state должен либо переименовать концепт в scoped sales runtime, либо оставить generic только как explicitly legacy pointer.

## 3. Target architecture

Целевая структура проекта:

```text
OpenCloud/
  apps/
    larisa_ivanovna/
      agent/
      commands/
      workflows/
      providers/
      formatters/
      schemas/
      prompts/
      telegram/
      tests/
      README.md

    lev_petrovich/
      agent/
      workflows/
      analytics/
      formatters/
      prompts/
      telegram/
      legacy_sales_agent/
      tests/
      README.md

    finansist/
      agent/
      workflows/
      providers/
      schemas/
      prompts/
      tests/
      README.md

    news_agent/
      agent/
      workflows/
      config/
      tests/
      README.md

    bot_gateway/
      telegram_ingress/
      command_router/
      delivery/
      tests/
      README.md

  shared/
    orchestrator/
      router/
      context/
      dispatcher/
      search_state/
    providers/
      bitrix/
      todo/
      whoop/
      search/
      telegram/
      openai/
      wazzup/
    skills/
      bitrix_sales_data/
      bitrix_calendar/
      todo_tasks/
      whoop_data/
      web_search/
    devops/
      health/
      monitoring/
      diagnostics/
      self_healing/
    compat/
    time/
    logging/
    formatting/

  config/
    env/
      examples/
        shared.env.example
        larisa.env.example
        lev_petrovich.env.example
        finansist.env.example
        news_agent.env.example
        whoop.env.example
      schemas/
        shared.env.schema.md
        larisa.env.schema.md
        lev_petrovich.env.schema.md
    schedules/
      schedule_contract.env
      local.cron
      server.cron
      README.md

  infra/
    orchestrator/
      run_workflow.sh
      lib.sh
      workflows/
    deploy/
      larisa/
      lev_petrovich/
      news_agent/
      shared/
      rollback/
      verify/
    systemd/
      README.md
    cron/
      README.md
      active/
      legacy/
    docker/
      openclaw/
      searxng/
    server_snapshots/
    remote_ops/

  docs/
    architecture/
    runbooks/
    audits/
    roles/
      larisa_ivanovna/
      lev_petrovich/
      finansist/
    status/
    decisions/
    migration/

  tests/
    unit/
    integration/
    smoke/
    fixtures/

  runtime/
    README.md
    local_state_links.md
    server_runtime_map.md

  data/
    README.md
    .gitkeep

  reports/
    README.md
    .gitkeep

  archive/
    README.md
    commercial-director-pre-lev/
    whoop-standalone/
    incubator-openclaw-extensions/
    restored-workspace/
```

Целевой принцип:

- `apps/*` содержит agent-specific код.
- `shared/*` содержит код, изменение которого потенциально влияет на несколько агентов.
- `config/env/examples/*` не содержит секретов.
- реальные env живут только на сервере или в локальном private config вне git.
- `infra/*` содержит способы запуска, деплоя, cron/systemd/docker templates и verification.
- `archive/*` не участвует в runtime.

## 4. Current-to-target mapping

| Current path | Target path | Decision | Rationale |
|---|---|---|---|
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | target repo root `OpenCloud/` или новая branch layout внутри этого repo | migrate with cleanup | Канонический инженерный source of truth; переносить структуру нужно внутри контролируемой migration branch, не физическим перемещением сразу. |
| `/Users/pro2kuror/Desktop/Cloudbot` | оставить как launcher/workspace wrapper или заменить позже на documented entrypoint | keep as legacy temporarily | Это symlink-обертка, не source of truth. Удобна для навигации, но не должна быть runtime truth. |
| `/Users/pro2kuror/Desktop/Cloudbot/engineer` | ссылка на target repo после миграции | keep as legacy temporarily | Сейчас symlink на `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`; менять symlink нельзя до отдельной волны. |
| `/Users/pro2kuror/Desktop/Cloudbot/architect` | ссылка на docs/control-plane после миграции | keep as legacy temporarily | Сейчас symlink на `/Users/pro2kuror/Desktop/architect`; не трогать до docs migration. |
| `/Users/pro2kuror/Desktop/architect` | `docs/`, `docs/status/`, `docs/runbooks/`, `docs/audits/`, `docs/decisions/` | migrate with cleanup | Это docs/control-plane, но содержит смешанные маркетинговые артефакты и tmp/output; нужен отбор документов. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/larisa_ivanovna` | `apps/larisa_ivanovna/agent`, `apps/larisa_ivanovna/workflows`, `apps/larisa_ivanovna/providers`, `apps/larisa_ivanovna/formatters`, `apps/larisa_ivanovna/schemas`, `apps/larisa_ivanovna/commands` | migrate as-is first, then cleanup | Source of truth для Ларисы. Сначала перенести без логических изменений, затем чистить зависимости. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/lev_petrovich` | `apps/lev_petrovich/agent`, `apps/lev_petrovich/telegram`, `apps/lev_petrovich/workflows` | migrate as-is | Source of truth роли Лев Петрович. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/sales_agent` | `apps/lev_petrovich/legacy_sales_agent` | keep as legacy temporarily | Compatibility layer. Нельзя удалять до завершения migration и прохождения sales tests. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/finansist` | `apps/finansist` | investigate first | Активность роли вне текущего запроса не подтверждена полностью; перенести после отдельного role audit. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/news_agent` | `apps/news_agent` | investigate first | В аудите упоминается news runtime/env; нужна отдельная проверка текущей live-активности. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/bot/telegram` | `apps/bot_gateway/telegram_ingress` и `apps/bot_gateway/delivery` | migrate with cleanup | Telegram слой должен стать тонким gateway, без бизнес-логики. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/orchestrator` | `shared/orchestrator` | migrate with cleanup | Общий слой маршрутизации; изменения ломают несколько агентов. Требует contract tests. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/providers` | `shared/providers` | migrate with cleanup | Общие Bitrix/Todo/WHOOP/Search/Telegram/Wazzup providers. Нужно отделить shared от agent-specific adapters. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/skills` | `shared/skills` | migrate with cleanup | Навыки используются разными workflow; нужна явная ownership map. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/workflows/larisa_*` | `apps/larisa_ivanovna/workflows` | migrate with cleanup | Agent-specific workflow должен жить рядом с агентом Ларисы. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/workflows/sales_brief.py` | `apps/lev_petrovich/workflows` | migrate with cleanup | Sales/Lev workflow, не shared. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/workflows/finance_*`, `pnl_*`, `cashflow_*` | `apps/finansist/workflows` | investigate first | Похоже на Финансиста; нужна проверка активного контура. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/workflows/system_health.py` | `shared/devops/health` или `infra/orchestrator/workflows/health` | investigate first | Может быть shared runtime health, но зависит от server state. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/devops` | `shared/devops` и `infra/verify` | migrate with cleanup | Разделить библиотечные проверки и operator workflows. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/infra/orchestrator` | `infra/orchestrator` | migrate as-is first | Канонический shell workflow слой. Сначала перенос без изменений. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/infra/orchestrator/workflows/larisa_*.sh` | `infra/deploy/larisa` или `infra/orchestrator/workflows/larisa` | migrate with cleanup | Agent-specific ops workflows; не смешивать с generic infra. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/infra/orchestrator/workflows/sales_*.sh` | `infra/deploy/lev_petrovich` или `infra/orchestrator/workflows/lev_petrovich` | migrate with cleanup | Sales/Lev ops workflows. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/infra/orchestrator/workflows/openclaw_*.sh` | `infra/orchestrator/workflows/openclaw` | migrate with cleanup | Platform ops, не agent-specific app code. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/configs/schedule_contract.env` | `config/schedules/schedule_contract.env` | migrate as-is | Source of truth для расписаний. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/configs/schedules.cron` | `config/schedules/local.cron` | migrate with cleanup | Сейчас описывает локальный cron dev-machine; отделить от server cron. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/configs/*.env.example` | `config/env/examples/*.env.example` | migrate with cleanup | Развести shared и per-agent env examples. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.integrations.example` | `config/env/examples/shared.env.example` + per-agent examples | migrate with cleanup | Сейчас смешивает Telegram/OpenAI/Bitrix/Sales/WHOOP/Wazzup. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.integrations` | не в target repo; private local runtime path | keep external | Symlink на `/Users/pro2kuror/.config/openclo/assistant/.env.integrations`; секреты не переносить. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs` | `docs/architecture`, `docs/roles`, `docs/runbooks`, `docs/migration` | migrate with cleanup | Часть docs уже runtime-aware, но нужно дедуплицировать с `/Users/pro2kuror/Desktop/architect`. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/roles/lev_petrovich` | `docs/roles/lev_petrovich` и `apps/lev_petrovich/prompts/templates` | migrate with cleanup | Разделить documentation и runtime prompts/templates. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/server_snapshots` | `infra/server_snapshots` | migrate as-is | Исторический evidence layer; не runtime. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` | `archive/commercial-director-pre-lev` | archive | Старый sales/knowledge contour, не source of truth после `agents/lev_petrovich`. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` | `archive/whoop-standalone` или `apps/whoop_report` | investigate first | Есть standalone `.env` и token files; live WHOOP сейчас server-only cron через `/usr/local/bin/send_whoop_report.py`. |
| `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` | `archive/incubator-openclaw-extensions` или `experiments/openclaw-extensions` | archive by default | JS-прототип с `orchestrator.js`, `router.js`, `workflow.*.js`, `provider.*.js`; не канонический runtime. |
| `/Users/pro2kuror/Desktop/OpenClo/archive/restored-workspace` | `archive/restored-workspace` | archive | Исторический восстановленный workspace. |
| `/Users/pro2kuror/Desktop/tools` / `/Users/pro2kuror/Desktop/Tools` | не переносить; external project | keep external | Paperclip — внешний orchestration product, не часть OpenCloud runtime. |
| `/Users/pro2kuror/Desktop/tools/paperclip` | не переносить; documented external tool | keep external | Может использоваться как инструмент, но не source of truth Cloudbot. |
| `/opt/cloudbot-runtime/larisa/current` | server runtime pointer Larisa | keep external runtime | Не переносить локально; target contract должен ссылаться на него как на production runtime Ларисы. |
| `/opt/cloudbot-runtime/current` | временный server runtime pointer Sales/Lev | keep as legacy temporarily | Нужно заменить target state на scoped sales/lev pointer, но не сейчас. |
| `/opt/openclaw` | OpenClaw platform runtime | keep external | Platform/env/state contour; не source of truth agent code. |
| `/root/.openclaw/workspace/todo-integration` | `archive/server-only/todo-integration` после отдельной миграции | keep as legacy temporarily | Server-only active scheduler для sync/reminders/execution. Нельзя трогать без dependency map. |
| `/etc/openclaw/*.env` | runtime-only server env | keep external | Реальные секреты и runtime env не должны попадать в git. |
| `/etc/cron.d/cloudbot-larisa-daily-brief` | `infra/cron/active/larisa-daily-brief.cron` template only | investigate first | Активный server cron. Нельзя менять, можно только документировать. |
| `/etc/cron.d/cloudbot-sales-reports` | `infra/cron/active/sales-reports.cron` template only | investigate first | Активный server cron. Нельзя менять, можно только документировать. |
| `/etc/cron.d/openclaw-todo-digest` | `infra/cron/legacy/openclaw-todo-digest.cron` template only | keep as legacy temporarily | Active sync/reminders/execution; digest slots disabled. |
| `/etc/cron.d/openclaw-whoop-report` | `infra/cron/active/whoop-report.cron` template only | investigate first | Active WHOOP report. Нужно решить: standalone app или server-only integration. |

## 5. Canonical source of truth map

| Zone | Canonical source of truth now | Target source of truth | Notes |
|---|---|---|---|
| Лариса Ивановна app code | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/larisa_ivanovna` + `cloudbot/workflows/larisa_*` | `apps/larisa_ivanovna` | Сначала migrate as-is, потом выделять shared dependencies. |
| Лариса runtime | `/opt/cloudbot-runtime/larisa/current` | `/opt/cloudbot-runtime/larisa/current` | Уже scoped; не переключать без smoke-check. |
| Лариса cron | `/etc/cron.d/cloudbot-larisa-daily-brief` | template in `infra/cron/active`, live remains `/etc/cron.d/...` | В target repo хранить template/contract, не секреты и не live mutation. |
| Лев Петрович app code | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/lev_petrovich` | `apps/lev_petrovich` | Canonical role code. |
| Sales compatibility | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/sales_agent` | `apps/lev_petrovich/legacy_sales_agent` | Compatibility layer до полной миграции. |
| Лев/Sales runtime | `/opt/cloudbot-runtime/current` | target: `/opt/cloudbot-runtime/lev_petrovich/current` или `/opt/cloudbot-runtime/sales/current` | Current live pointer оставить временно, но запретить новые generic deploy без scope. |
| Shared orchestrator | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/orchestrator` | `shared/orchestrator` | High blast radius. Нужны contract tests. |
| Shared providers | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/providers` | `shared/providers` | Разделить shared provider и agent-specific adapter. |
| Shared skills | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/skills` | `shared/skills` | Нужна ownership map по агентам. |
| Telegram ingress | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/bot/telegram` | `apps/bot_gateway/telegram_ingress` | Держать тонким. |
| Docs/control-plane | `/Users/pro2kuror/Desktop/architect` + `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs` | `docs/*` | Дедуплицировать и классифицировать. |
| Runtime schedules | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/configs/schedule_contract.env` | `config/schedules/schedule_contract.env` | Contract first, live cron apply отдельно. |
| Local private env | `/Users/pro2kuror/.config/openclo/assistant/.env.integrations` | external private env | Не git. |
| Server env | `/etc/openclaw/*.env`, `/opt/openclaw/.env`, `/root/.openclaw/workspace/todo-integration/.env.runtime` | runtime-only server env | Не git. Только schemas/examples в repo. |
| OpenClaw platform | `/opt/openclaw` | external platform runtime | Не часть app source. |
| Todo legacy integration | `/root/.openclaw/workspace/todo-integration` | keep legacy until migration | Active sync/reminders/execution. |
| Paperclip | `/Users/pro2kuror/Desktop/tools/paperclip` | external tool | Не OpenCloud runtime. |
| Commercial director old contour | `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` | `archive/commercial-director-pre-lev` | Legacy/archive. |
| WHOOP standalone | `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` | investigate first | Active live WHOOP сейчас server cron/script. |
| Incubator JS extensions | `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` | archive/experiments | Не source of truth. |

## 6. Env contract

### 6.1 Principles

- Реальные env не хранятся в git.
- В git хранятся только `.env.example`, schema docs и validation scripts.
- Общий `TELEGRAM_BOT_TOKEN` не должен быть fallback для agent-specific delivery.
- Каждый агент должен иметь свой explicit bot token или explicit token file.
- Agent-specific chat ids нельзя шарить через общий `TELEGRAM_CHAT_ID`.
- Shared env должен содержать только инфраструктурные общие настройки, которые не определяют identity агента.

### 6.2 `shared.env`

Назначение: общая инфраструктура, не identity конкретного Telegram-агента.

Допустимые ключи:

```text
TZ=Europe/Moscow
OPENAI_API_KEY=
OPENAI_MODEL=
BITRIX_BASE_URL=
BITRIX_WEBHOOK_URL=
BITRIX_CLIENT_ID=
BITRIX_CLIENT_SECRET=
BITRIX_APP_STATE_DIR=
SEARCH_PROVIDER=
SEARCH_BASE_URL=
SEARCH_TIMEOUT_SECONDS=
SENTRY_BASE_URL=
SENTRY_ORG=
SENTRY_PROJECT=
SENTRY_AUTH_TOKEN=
WAZZUP_API_BASE_URL=
WAZZUP_API_KEY=
WAZZUP_WEBHOOK_FORWARD_URL=
LOG_LEVEL=
REPORT_DIR=
```

Запрещено в `shared.env`:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
LARISA_TELEGRAM_CHAT_ID
SALES_TELEGRAM_CHAT_ID
SALES_TELEGRAM_OWNER_ID
SALES_TELEGRAM_BOT_TOKEN
WHOOP_REFRESH_TOKEN
TODO_TOKEN
```

### 6.3 `larisa.env`

Назначение: identity и runtime настройки Ларисы Ивановны.

Допустимые ключи:

```text
LARISA_AGENT_NAME=larisa_ivanovna
LARISA_TIMEZONE=Europe/Moscow
LARISA_TELEGRAM_BOT_TOKEN_FILE=
LARISA_TELEGRAM_CHAT_ID=
LARISA_TELEGRAM_OWNER_ID=
LARISA_BITRIX_USER_ID=
LARISA_TODO_TOKEN_FILE=
LARISA_TODO_PROVIDER=
LARISA_REPORT_DIR=
LARISA_DAILY_BRIEF_ENABLED=
LARISA_CONTENT_TOPICS_ENABLED=
LARISA_WEATHER_ENABLED=
```

Правило:

- Лариса не должна использовать fallback на `TELEGRAM_BOT_TOKEN`.
- Лариса не должна использовать `SALES_*`.
- Если нужен общий Telegram provider, он принимает explicit credentials от агента.

### 6.4 `lev_petrovich.env`

Назначение: identity и runtime настройки Льва Петровича / Sales Copilot.

Допустимые ключи:

```text
LEV_AGENT_NAME=lev_petrovich
LEV_TIMEZONE=Europe/Moscow
LEV_TELEGRAM_BOT_TOKEN_FILE=
LEV_TELEGRAM_CHAT_ID=
LEV_TELEGRAM_OWNER_ID=
LEV_TELEGRAM_DM_CHAT_ID=
LEV_WEEKLY_TELEGRAM_CHAT_ID=
LEV_ALERT_TELEGRAM_CHAT_ID=
LEV_REPORT_DIR=
LEV_DAILY_HISTORY_FILE=
LEV_SALES_DEPARTMENT_IDS=
LEV_SALES_DEPARTMENT_NAMES=
LEV_EXCLUDED_USER_IDS=
LEV_EXCLUDED_USER_NAMES=
LEV_EXCLUDED_USER_MARKERS=
LEV_DAILY_REPORT_ENABLED=
LEV_FOLLOWUP_ENABLED=
LEV_WEEKLY_REVIEW_ENABLED=
```

Compatibility aliases, временно:

```text
SALES_TELEGRAM_BOT_TOKEN_FILE -> LEV_TELEGRAM_BOT_TOKEN_FILE
SALES_TELEGRAM_CHAT_ID -> LEV_TELEGRAM_CHAT_ID
SALES_WEEKLY_TELEGRAM_CHAT_ID -> LEV_WEEKLY_TELEGRAM_CHAT_ID
SALES_TELEGRAM_OWNER_ID -> LEV_TELEGRAM_OWNER_ID
SALES_DAILY_HISTORY_FILE -> LEV_DAILY_HISTORY_FILE
```

Правило:

- Лев не должен использовать общий `TELEGRAM_BOT_TOKEN` по умолчанию.
- `agents/sales_agent` может читать `SALES_*` только в compatibility mode.
- Новые features должны читать `LEV_*`.

### 6.5 `runtime-only server env`

Остается только на сервере:

```text
/opt/openclaw/.env
/opt/openclaw/.env.security_profile
/etc/openclaw/larisa.env
/etc/openclaw/sales_agent.env
/etc/openclaw/todo.env
/etc/openclaw/whoop.env
/root/.openclaw/workspace/todo-integration/.env.runtime
```

Target:

```text
/etc/opencloud/shared.env
/etc/opencloud/larisa.env
/etc/opencloud/lev_petrovich.env
/etc/opencloud/whoop.env
/etc/opencloud/todo_legacy.env
```

Но это только target contract. Не применять без отдельной migration wave.

### 6.6 Что нельзя шарить между агентами

- Telegram bot token.
- Telegram chat id / owner id.
- Agent prompt/system instructions.
- Agent-specific report directory.
- Agent-specific schedule enable flags.
- Sales team filters.
- Larisa Bitrix user id.
- Todo token, если он задает identity/owner.
- WHOOP refresh token, если WHOOP остается персональным контуром.

## 7. Runtime contract

### 7.1 Current live runtime

Подтверждено live:

```text
Лариса:
/opt/cloudbot-runtime/larisa/current
-> /opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326

Лев / Sales:
/opt/cloudbot-runtime/current
-> /opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60

OpenClaw platform:
/opt/openclaw

Todo legacy:
/root/.openclaw/workspace/todo-integration
```

### 7.2 Target runtime

Желаемое состояние:

```text
/opt/opencloud-runtime/
  larisa/
    current -> releases/<release_id>
    releases/
    .deploy.lock
    reports/

  lev_petrovich/
    current -> releases/<release_id>
    releases/
    .deploy.lock
    reports/

  news_agent/
    current -> releases/<release_id>
    releases/
    .deploy.lock
    reports/

  shared/
    current -> releases/<release_id>
    releases/

  legacy/
    cloudbot-runtime-current -> /opt/cloudbot-runtime/current
```

### 7.3 Generic `current`

Рекомендация:

- новый generic `/opt/cloudbot-runtime/current` для agent runtime не использовать;
- если generic pointer нужен, то только как read-only legacy pointer для обратной совместимости;
- новые deploy должны требовать explicit scope:
  - `larisa`
  - `lev_petrovich`
  - `news_agent`
  - `shared`

### 7.4 Legacy runtime paths to keep temporarily

Оставить временно:

```text
/opt/cloudbot-runtime/larisa/current
/opt/cloudbot-runtime/current
/home/ops/cloudbot-larisa-agent/reports
/home/ops/cloudbot-sales-agent/reports
/root/.openclaw/workspace/todo-integration
/opt/openclaw
```

Не использовать для новых deploy:

```text
/opt/cloudbot-runtime/current
```

Исключение: только текущий sales/Lev compatibility до выделения `/opt/cloudbot-runtime/lev_petrovich/current`.

### 7.5 Deploy boundaries

Лариса deploy:

- может менять только `/opt/cloudbot-runtime/larisa/releases/*` и symlink `/opt/cloudbot-runtime/larisa/current`;
- не может менять `/opt/cloudbot-runtime/current`;
- не может менять `/etc/openclaw/sales_agent.env`;
- не может менять sales cron.

Лев deploy:

- target должен стать `/opt/cloudbot-runtime/lev_petrovich/current`;
- до этого временно использует `/opt/cloudbot-runtime/current`;
- не может менять `/opt/cloudbot-runtime/larisa/current`;
- не может менять `/etc/openclaw/larisa.env`;
- не может менять Larisa cron.

Shared deploy:

- запрещен без предварительных tests для Ларисы и Льва;
- должен иметь explicit blast radius и rollback.

## 8. Migration waves

### Wave 0 — freeze/snapshot

Цель:

- зафиксировать текущее состояние перед любыми изменениями.

Входит:

- read-only `git status` для `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`;
- read-only `git status` для `/Users/pro2kuror/Desktop/architect`;
- read-only server baseline:
  - `systemctl status/cat cloudbot-bitrix-app.service`;
  - `docker ps`;
  - `/etc/cron.d/*cloudbot*`, `/etc/cron.d/*openclaw*`;
  - symlink targets `/opt/cloudbot-runtime/larisa/current`, `/opt/cloudbot-runtime/current`;
  - env file names and keys only, no values;
  - recent report/log timestamps.

Не входит:

- перенос файлов;
- cleanup;
- изменение cron/systemd/env/runtime pointers.

Риски:

- dirty repo может содержать незавершенные изменения;
- server state может измениться между audit и migration.

Проверить перед переходом:

- baseline сохранен в docs/audits;
- список live paths утвержден;
- нет неучтенных active services.

### Wave 1 — docs + classification

Цель:

- классифицировать все зоны как `prod`, `dev`, `legacy`, `archive`, `external`.

Входит:

- docs inventory;
- mapping current -> target;
- README markers для будущих зон: `source of truth`, `legacy`, `archive`, `external`;
- decision records.

Не входит:

- перенос runtime code;
- изменение env;
- изменение cron.

Риски:

- ошибочно пометить active legacy как archive.

Проверить:

- Лариса и Лев имеют отдельные source-of-truth records;
- `Paperclip` явно external;
- `commercial-director` legacy/archive;
- `whoop` помечен `investigate first`.

### Wave 2 — apps layout

Цель:

- создать target app boundaries.

Входит:

- подготовить структуру `apps/larisa_ivanovna`;
- подготовить структуру `apps/lev_petrovich`;
- временно разместить `agents/sales_agent` как `legacy_sales_agent`;
- imports не менять до отдельного compatibility step, если это увеличивает риск.

Не входит:

- shared extraction;
- env separation;
- server deploy.

Риски:

- broken imports;
- tests смотрят старые пути.

Проверить:

- unit tests Ларисы;
- unit tests Льва/Sales;
- `tests/test_larisa_agent.py`;
- `tests/test_lev_petrovich_runtime.py`;
- `tests/test_sales_dispatch_contract.py`.

### Wave 3 — shared extraction

Цель:

- вынести общий код в `shared/` без изменения поведения.

Входит:

- `cloudbot/orchestrator -> shared/orchestrator`;
- `cloudbot/providers -> shared/providers`;
- `cloudbot/skills -> shared/skills`;
- compatibility imports.

Не входит:

- изменение бизнес-логики;
- переименование env keys;
- deploy.

Риски:

- shared provider change ломает обоих агентов;
- circular imports.

Проверить:

- Лариса smoke;
- Лев smoke;
- provider tests;
- orchestrator/router tests;
- manual dry-run commands.

### Wave 4 — env separation

Цель:

- развести shared и agent-specific env.

Входит:

- создать examples/schemas:
  - `shared.env.example`;
  - `larisa.env.example`;
  - `lev_petrovich.env.example`;
- добавить validation scripts;
- добавить compatibility aliases для `SALES_* -> LEV_*`.

Не входит:

- перенос реальных секретов;
- изменение `/etc/openclaw/*.env`;
- изменение `/Users/pro2kuror/.config/openclo/assistant/.env.integrations`.

Риски:

- Telegram delivery уйдет не в тот контур;
- fallback на общий token скроет ошибку конфигурации.

Проверить:

- без agent-specific Telegram token агент должен падать явно и безопасно;
- Лариса не читает `SALES_*`;
- Лев не читает `LARISA_*`;
- shared env не содержит agent identity.

### Wave 5 — runtime separation

Цель:

- закрепить scoped runtime для каждого агента.

Входит:

- target plan для `/opt/cloudbot-runtime/lev_petrovich/current`;
- deploy scripts with explicit scope;
- lock path per agent;
- rollback per agent.

Не входит:

- переключение live symlink;
- изменение active cron;
- удаление `/opt/cloudbot-runtime/current`.

Риски:

- sales reports перестанут приходить;
- wrapper укажет не на тот release;
- generic current будет использован случайно.

Проверить:

- dry-run deploy package;
- release metadata;
- wrapper target;
- rollback target;
- smoke for both agents.

### Wave 6 — staging checks

Цель:

- доказать, что target structure работает до production cutover.

Входит:

- staging release;
- dry-run Telegram;
- mock Bitrix/Todo/WHOOP/OpenAI where possible;
- live read-only API smoke only по разрешению.

Не входит:

- live cron switch;
- live systemd switch;
- real Telegram delivery без явного разрешения.

Риски:

- staging env не совпадает с prod;
- missing server-only dependencies.

Проверить:

- Лариса daily brief;
- Лариса tasks/meetings/search;
- Лев daily/check/followup/weekly;
- OpenClaw gateway health;
- Bitrix app service health;
- WHOOP report dry-run.

### Wave 7 — production cutover

Цель:

- переключить production по одному контуру.

Входит:

- сначала один агент, не оба;
- explicit approval;
- backup active wrappers/cron;
- switch runtime pointer;
- smoke;
- log check;
- rollback window.

Не входит:

- cleanup;
- archive;
- удаление compatibility.

Риски:

- Telegram delivery failure;
- cron запускает старый wrapper;
- rollback не возвращает env expectations.

Проверить:

- cron next run;
- manual controlled run;
- Telegram delivery;
- logs за 1-2 запуска;
- no errors in journal/docker logs.

### Wave 8 — archive/cleanup

Цель:

- убрать визуальный мусор из active workspace без удаления данных.

Входит:

- move-to-archive plan;
- README markers;
- old `.bak` cron documentation;
- archive index.

Не входит:

- physical deletion;
- history rewrite;
- secret cleanup без отдельного security process.

Риски:

- архивировать используемый legacy;
- потерять forensic evidence.

Проверить:

- 2 стабильных цикла daily reports;
- оба Telegram-контура работают;
- no references to archived paths in active cron/wrappers/tests.

## 9. Do-not-touch list

Нельзя:

- менять Ларису и Льва одновременно;
- переключать `/opt/cloudbot-runtime/larisa/current` без Larisa smoke-check;
- переключать `/opt/cloudbot-runtime/current` без Sales/Lev smoke-check;
- использовать `/opt/cloudbot-runtime/current` для новых agent deploy после выделения scoped runtime;
- переносить docs и runtime code в одном коммите;
- менять env schema и runtime pointer в одной волне;
- удалять `agents/sales_agent` до завершения compatibility migration;
- удалять или архивировать `/root/.openclaw/workspace/todo-integration` без отдельной dependency map;
- трогать `/etc/openclaw/*.env` без explicit secret handling plan;
- выводить значения токенов/env в отчет;
- менять `/etc/cron.d/cloudbot-larisa-daily-brief` без approved cutover;
- менять `/etc/cron.d/cloudbot-sales-reports` без approved cutover;
- менять `cloudbot-bitrix-app.service` без Bitrix/Wazzup dependency map;
- перезапускать `docker.service`, `openclaw-openclaw-gateway-1`, `cloudbot-bitrix-app.service` в рамках migration planning;
- считать `Paperclip` частью OpenCloud runtime;
- считать `/Users/pro2kuror/Desktop/Cloudbot` source of truth;
- физически переносить `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` до устранения absolute path dependencies;
- переносить реальные `.env`, `.whoop_tokens.json`, private keys, token files в git;
- выполнять cleanup старых `.bak` cron-файлов на сервере в этой задаче.

## 10. What to send back to ChatGPT

Короткий блок для следующего этапа:

```text
Готов проект безопасной реорганизации OpenCloud/Cloudbot.
Вердикт остается: частичный rebuild.
Source of truth сейчас:
- repo: /Users/pro2kuror/Desktop/OpenClo/projects/engineer
- docs/control-plane: /Users/pro2kuror/Desktop/architect
- Larisa runtime: /opt/cloudbot-runtime/larisa/current
- Lev/Sales runtime: /opt/cloudbot-runtime/current

Target:
- apps/larisa_ivanovna
- apps/lev_petrovich
- apps/lev_petrovich/legacy_sales_agent
- shared/orchestrator
- shared/providers
- shared/skills
- config/env/examples + schemas
- infra/orchestrator + infra/deploy + infra/cron
- docs/*
- archive/*

Главные правила:
- не менять Ларису и Льва одновременно;
- не использовать общий TELEGRAM_BOT_TOKEN как fallback;
- не удалять sales_agent до конца compatibility migration;
- не трогать server-only integrations без отдельной dependency map;
- runtime pointers переключать только после staging smoke и rollback plan.

Следующий этап: Wave 0/Wave 1 — freeze baseline и classification docs без изменения runtime.
```

