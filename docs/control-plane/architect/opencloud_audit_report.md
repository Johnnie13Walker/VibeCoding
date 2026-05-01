# Аудит структуры OpenCloud / Cloudbot

Дата аудита: 2026-04-23, МСК  
Режим: только чтение, без удаления, перемещения, переименования, перезапуска сервисов и изменения конфигов.

## 1. Executive summary

Найдено не одно физическое дерево OpenCloud, а несколько связанных контуров:

- `/Users/pro2kuror/Desktop/OpenClo` — фактический старый/расширенный локальный workspace OpenClo; внутри находится основной инженерный git-контур `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`.
- `/Users/pro2kuror/Desktop/Cloudbot` / `/Users/pro2kuror/Desktop/CloudBot` — не отдельный проект, а удобная обертка с symlink'ами:
  - `architect -> /Users/pro2kuror/Desktop/architect`
  - `engineer -> /Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- `/Users/pro2kuror/Desktop/architect` — отдельный git-контур документации/control-plane.
- `/Users/pro2kuror/Desktop/tools` / `/Users/pro2kuror/Desktop/Tools` — отдельный проект Paperclip, не source of truth для Cloudbot.

Точные папки из запроса:

- `~/Desktop/OpenCloud` — не найдена.
- `~/Desktop/Tools` — найдена; на текущей файловой системе это тот же каталог, что `~/Desktop/tools`.
- `~/Desktop/Архитект` — не найдена.
- `~/Desktop/CloudBot` — найдена; на текущей файловой системе это тот же каталог, что `~/Desktop/Cloudbot`.

Основной риск: структура уже лечилась symlink-оберткой, но реальные runtime-пути и часть документации/cron всё еще завязаны на абсолютные пути `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` и `/Users/pro2kuror/Desktop/architect`. На сервере live-проверкой подтверждены несколько runtime-контуров: scoped runtime Ларисы, generic runtime sales, `/opt/openclaw`, server-only todo-integration, WHOOP cron и Bitrix service.

Вердикт: **Вариант B — нужен частичный rebuild**.

Почему не A: дублей и исторических хвостов слишком много, есть несколько entrypoint'ов и несколько runtime-контуров.  
Почему не C: канонический инженерный repo, роли агентов, target runtime Ларисы и основные контракты уже описаны; полностью строить заново не требуется.

## 2. Карта текущей структуры

| Путь | Назначение | Статус | Используется сейчас | Комментарий |
|---|---|---:|---:|---|
| `/Users/pro2kuror/Desktop/OpenCloud` | Заявленная папка OpenCloud | missing | нет | Такой папки нет. Есть похожая `/Users/pro2kuror/Desktop/OpenClo`. |
| `/Users/pro2kuror/Desktop/OpenClo` | Старый/расширенный workspace OpenClo | mixed | да, косвенно | Содержит `projects/engineer`, `projects/whoop`, `projects/commercial-director`, `incubator`, `archive`. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | Основной инженерный git-контур Cloudbot/OpenClo | prod/dev | да | Git remote `https://github.com/Johnnie13Walker/codex-base.git`, ветка `codex/feature/self-healing`, много незакоммиченных изменений. |
| `/Users/pro2kuror/Desktop/Cloudbot` | Удобная локальная точка входа | dev/control | да | Не самостоятельная копия. Содержит symlink'и на `architect` и `engineer`. |
| `/Users/pro2kuror/Desktop/Cloudbot/engineer` | Symlink на инженерный контур | prod/dev | да | Указывает на `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`. |
| `/Users/pro2kuror/Desktop/Cloudbot/architect` | Symlink на документационный контур | docs | да | Указывает на `/Users/pro2kuror/Desktop/architect`. |
| `/Users/pro2kuror/Desktop/architect` | Control-plane, документы, статусы, чеклисты | docs/dev | да | Отдельный git-контур, ветка `codex/docs-bootstrap`, много незакоммиченных документов/артефактов. |
| `/Users/pro2kuror/Desktop/tools` / `/Users/pro2kuror/Desktop/Tools` | Paperclip | external/dev | [не подтверждено] | Отдельный Node/React/TS проект, есть docker-compose и `.env.example`; не source of truth для Cloudbot. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` | Standalone WHOOP sandbox | dev/sandbox | [не подтверждено] | Есть `.env`, `.whoop_tokens.json`, `requirements.txt`, `package.json`; локальный модуль, live WHOOP по документам идет через серверный cron. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` | Старый sales/knowledge contour | archive/unclear | нет как source of truth | По `system_map.md` больше не должен считаться source of truth после переноса роли в `agents/lev_petrovich`. |
| `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` | Инкубационные JS-модули OpenClaw | experiment | [не подтверждено] | Есть `orchestrator.js`, `router.js`, `workflow.*.js`, `provider.*.js`, `.env.example`; похоже на старый JS-прототип. |
| `/Users/pro2kuror/Desktop/OpenClo/archive/restored-workspace` | Восстановленный архивный workspace | archive | нет | Содержит agent_sys, watchdog, старые файлы; расположен в `archive`. |

## 3. Что реально является боевым контуром

### 3.1 Локальный source of truth

Подтверждено локально:

- Основной repo: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- Удобный alias: `/Users/pro2kuror/Desktop/Cloudbot/engineer`
- Git remote: `origin -> https://github.com/Johnnie13Walker/codex-base.git`
- Текущая ветка: `codex/feature/self-healing`
- В repo есть реальные production-critical зоны:
  - `agents/larisa_ivanovna/`
  - `agents/lev_petrovich/`
  - `agents/sales_agent/` как compatibility-слой
  - `cloudbot/bot/telegram/`
  - `cloudbot/orchestrator/`
  - `cloudbot/workflows/`
  - `cloudbot/providers/`
  - `infra/orchestrator/`
  - `configs/schedules.cron`
  - `configs/schedule_contract.env`

Важный факт: `.env.integrations` в инженерном repo — symlink:

```text
/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.integrations
-> /Users/pro2kuror/.config/openclo/assistant/.env.integrations
```

Это хорошо для git-безопасности, но архитектурно это shared env, который может влиять сразу на несколько контуров.

### 3.2 Лариса Ивановна

Подтверждено локально:

- Код агента: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/larisa_ivanovna`
- Runtime workflows:
  - `agents/larisa_ivanovna/workflows/daily_brief.py`
  - `agents/larisa_ivanovna/workflows/evening_review.py`
  - `agents/larisa_ivanovna/workflows/meetings.py`
  - `agents/larisa_ivanovna/workflows/tasks.py`
  - `agents/larisa_ivanovna/workflows/weather.py`
  - `agents/larisa_ivanovna/workflows/plan_day.py`
  - `agents/larisa_ivanovna/workflows/search.py`
  - `agents/larisa_ivanovna/workflows/content_topics.py`
- Telegram/provider слой:
  - `agents/larisa_ivanovna/providers/telegram_provider.py`
  - `cloudbot/bot/telegram/telegram_handler.py`
  - `cloudbot/bot/telegram/commands.py`
  - `cloudbot/orchestrator/router.py`
- Workflow wrappers:
  - `infra/orchestrator/workflows/larisa_daily_brief.sh`
  - `infra/orchestrator/workflows/larisa_evening_review.sh`
  - `infra/orchestrator/workflows/larisa_midday_replan.sh`
  - `infra/orchestrator/workflows/larisa_content_topics.sh`
  - `infra/orchestrator/workflows/larisa_agent_deploy.sh`
- Локальный cron contract:
  - `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/configs/schedules.cron`
  - `09:00 МСК`: `./infra/orchestrator/run_workflow.sh larisa_daily_brief`
  - `19:30 МСК`: `PERIOD=day ./infra/orchestrator/run_workflow.sh larisa_content_topics`

По документации/runbook:

- Канонический live runtime Ларисы после cutover: `/opt/cloudbot-runtime/larisa/current`
- Deploy lock: `/opt/cloudbot-runtime/larisa/.deploy.lock`
- Старые `/home/ops/cloudbot-larisa-agent` и `/home/ops/cloudbot-news-agent` оставлены как legacy/report path.

Live-подтверждение сервера: **выполнено прямым read-only SSH**. Хост `ams-1-vm-76ds`, время проверки `2026-04-23 10:49 МСК`.

### 3.3 Лев Петрович

Подтверждено локально:

- Канонический агент роли: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/lev_petrovich`
- Compatibility runtime: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/sales_agent`
- Основной bridge/entrypoint для sales copilot:
  - `scripts/run_sales_copilot.py`
  - запускает `python3 -m agents.lev_petrovich --report <type>`
- Workflow wrappers:
  - `infra/orchestrator/workflows/sales_brief.sh`
  - `infra/orchestrator/workflows/sales_followup.sh`
  - `infra/orchestrator/workflows/sales_weekly_review.sh`
  - `infra/orchestrator/workflows/sales_morning_report.sh`
  - `infra/orchestrator/workflows/sales_agent_deploy.sh`
  - `infra/orchestrator/workflows/sales_agent_verify.sh`
- Документация роли:
  - `docs/roles/lev_petrovich/README.md`
  - `docs/roles/lev_petrovich/context.md`
  - `docs/roles/lev_petrovich/prompts/*`
  - `docs/roles/lev_petrovich/templates/*`

Env/config признаки:

- `SALES_TELEGRAM_CHAT_ID`
- `SALES_TELEGRAM_OWNER_ID`
- `SALES_TELEGRAM_DM_CHAT_ID`
- `SALES_WEEKLY_TELEGRAM_CHAT_ID`
- `SALES_TELEGRAM_BOT_TOKEN`
- `SALES_TELEGRAM_BOT_TOKEN_FILE`
- fallback на общий `TELEGRAM_BOT_TOKEN` существует в части кода, но тесты явно проверяют, что token resolution Льва по умолчанию не должен бездумно падать в shared token.

По документации/runbook:

- `agents/lev_petrovich` — канонический runtime entrypoint роли.
- `agents/sales_agent` — временный compatibility-слой до завершения миграции legacy-имени.
- `/opt/cloudbot-runtime/current` — generic runtime pointer, по документам используется sales-wrapper'ами; его нельзя считать runtime Ларисы.

Live-подтверждение сервера: **выполнено прямым read-only SSH**. Sales/Лев использует generic runtime `/opt/cloudbot-runtime/current`.

### 3.4 Общие компоненты

Общие для Ларисы и Льва:

- `cloudbot/orchestrator/*`
- `cloudbot/providers/*`
- `cloudbot/devops/*`
- `cloudbot/workflows/system_health.py`
- `infra/orchestrator/run_workflow.sh`
- `infra/orchestrator/lib.sh`
- `.env.integrations` / `/Users/pro2kuror/.config/openclo/assistant/.env.integrations`
- `configs/schedule_contract.env`
- `configs/schedules.cron`
- часть Telegram delivery variables (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) как fallback.

Риск: изменение общих provider/orchestrator/env может одновременно сломать оба Telegram-контура.

### 3.5 Серверные контуры, подтвержденные live

Подтверждено прямым read-only SSH на `ams-1-vm-76ds`:

- `/opt/openclaw` — активный platform/env/state контур.
- `/opt/cloudbot-runtime` — release-based runtime для Cloudbot.
- `/opt/cloudbot-runtime/larisa/current -> /opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326`
- `/opt/cloudbot-runtime/current -> /opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60`
- `/root/.openclaw` — OpenClaw config/workspace root.
- `/root/.openclaw/workspace/todo-integration` — server-only todo integration workspace.
- `/etc/openclaw` — server env directory.
- `/home/ops` — legacy/report paths.

Активные процессы и сервисы:

- `cloudbot-bitrix-app.service` — `active running`, `enabled`.
  - `WorkingDirectory=/opt/openclaw`
  - `ExecStart=/usr/bin/python3 /opt/openclaw/local/bitrix_app_server.py`
  - `EnvironmentFile=/opt/openclaw/.env`
- `docker.service` — `active running`, `enabled`.
- Docker compose `openclaw` — `running`, config `/opt/openclaw/docker-compose.yml`.
- Docker compose `searxng` — `running`, config `/opt/searxng/docker-compose.yml`.
- Container `openclaw-openclaw-gateway-1` — `Up 26 hours (healthy)`, image `openclaw:ddg-searxng-20260412`, ports `127.0.0.1:18789-18790`.
- Container `searxng` — `Up 4 days`, port `8088`.
- Container `searxng-redis` — `Up 4 days`.
- PM2 не установлен / не используется.

Активные cron-файлы:

- `/etc/cron.d/cloudbot-larisa-daily-brief`
  - `05:00 UTC = 08:00 МСК`
  - `/usr/local/bin/cloudbot-larisa-daily-brief.sh`
  - лог: `/home/ops/cloudbot-larisa-agent/reports/larisa_daily_brief_cron.log`
- `/etc/cron.d/cloudbot-sales-reports`
  - `06:30 UTC = 09:30 МСК`: `/usr/local/bin/cloudbot-sales-daily-brief.sh`
  - `06:40 UTC = 09:40 МСК`: `/usr/local/bin/cloudbot-sales-morning-check.sh`
  - `14:00 UTC = 17:00 МСК`: `/usr/local/bin/cloudbot-sales-followup.sh`
  - `15:30 UTC = 18:30 МСК по пятницам`: `/usr/local/bin/cloudbot-sales-weekly-review.sh`
- `/etc/cron.d/openclaw-todo-digest`
  - активны `sync`, `reminders:tick`, `execution:tick`
  - morning/midday/evening digest отключены комментариями после cutover на Ларису
- `/etc/cron.d/openclaw-whoop-report`
  - `05:01 UTC = 08:01 МСК`
  - `WHOOP_ENV_FILE=/etc/openclaw/whoop.env /usr/local/bin/send_whoop_report.py send-report`

Wrapper entrypoint'ы:

- `/usr/local/bin/cloudbot-larisa-daily-brief.sh`
  - `cd /opt/cloudbot-runtime/larisa/current`
  - `exec ./run_larisa_daily_brief_from_runtime_env.sh`
- `/usr/local/bin/cloudbot-sales-daily-brief.sh`
  - `cd /opt/cloudbot-runtime/current`
  - `exec ./run_sales_morning_report_from_runtime_env.sh`
- `/usr/local/bin/cloudbot-sales-morning-check.sh`
  - `cd /opt/cloudbot-runtime/current`
  - `exec ./run_sales_morning_report_check_from_runtime_env.sh`
- `/usr/local/bin/cloudbot-sales-followup.sh`
  - `cd /opt/cloudbot-runtime/current`
  - `exec ./run_sales_followup_from_runtime_env.sh`
- `/usr/local/bin/cloudbot-sales-weekly-review.sh`
  - `cd /opt/cloudbot-runtime/current`
  - `exec ./run_sales_weekly_review_from_runtime_env.sh`
- `/usr/local/bin/send_whoop_report.py`
  - standalone server script, env через `/etc/openclaw/whoop.env`.

Release metadata:

- Лариса:
  - runtime: `/opt/cloudbot-runtime/larisa/current`
  - release id: `codex_feature_self-healing_067d326`
  - branch: `codex/feature/self-healing`
  - commit: `067d326c5c23e4486efbef87741012211af1adaf`
  - содержит `run_larisa_daily_brief_from_runtime_env.sh`
- Sales / Лев:
  - runtime: `/opt/cloudbot-runtime/current`
  - release id: `codex_feature_self-healing_c329f60`
  - branch: `codex/feature/self-healing`
  - commit: `c329f6077b87dc332703d043dc82a41b9f131edd`
  - содержит `run_sales_morning_report_from_runtime_env.sh`, `run_sales_morning_report_check_from_runtime_env.sh`, `run_sales_followup_from_runtime_env.sh`, `run_sales_weekly_review_from_runtime_env.sh`

Server env-файлы, только имена и ключи без значений:

- `/opt/openclaw/.env` — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`, `OPENAI_API_KEY`, `OPENCLAW_GATEWAY_TOKEN`, Bitrix/Wazzup/OpenClaw настройки.
- `/opt/openclaw/.env.security_profile` — security/backup/risk profile.
- `/etc/openclaw/larisa.env` — `LARISA_BITRIX_USER_ID`, `LARISA_TODO_TOKEN`.
- `/etc/openclaw/sales_agent.env` — `SALES_*` Telegram/chat/report/team settings, включая `SALES_TELEGRAM_BOT_TOKEN_FILE`.
- `/etc/openclaw/todo.env` — Todo/Telegram digest settings.
- `/etc/openclaw/whoop.env` — WHOOP OAuth/report/Telegram settings.
- `/root/.openclaw/workspace/todo-integration/.env.runtime` — Todo/Bitrix/Telegram/reminders/execution runtime settings.

Логи / признаки работы:

- `/opt/cloudbot-runtime/larisa/current/reports` содержит свежие отчеты Ларисы, включая `2026-04-23 09:11 МСК` и `2026-04-23 09:25 МСК`.
- `/var/log/openclaw-whoop-report.log` обновлен `2026-04-23 05:05 UTC`.
- `/var/log/openclaw-todo-sync.log`, `/var/log/openclaw-execution-tick.log`, `/var/log/openclaw-todo-reminders.log` обновлялись утром `2026-04-23`.
- `journalctl -u cloudbot-bitrix-app.service --since "24 hours ago"` показывает регулярные `bitrix_app_wazzup_forward status=ok`.

### 3.6 Серверные контуры по snapshot/runbook

Дополнительно ранее было зафиксировано в локальных документах и snapshot:

- `/opt/cloudbot-runtime/larisa/current` — scoped runtime Ларисы.
- `/opt/cloudbot-runtime/current` — generic runtime pointer для sales.
- `/opt/openclaw` — platform/env/state контур, не source of truth agent-кода.
- `/etc/openclaw/news_agent.env` — env news-agent.
- `/etc/openclaw/whoop.env` — env WHOOP report.
- `/etc/cron.d/openclaw-whoop-report` — WHOOP cron.
- `/etc/cron.d/openclaw-todo-digest` — legacy todo scheduler через docker exec.
- `/root/.openclaw/workspace/todo-integration` — server-only todo integration workspace.
- `cloudbot-bitrix-app.service` — по `system_map.md`, `WorkingDirectory=/opt/openclaw`, `ExecStart=/usr/bin/python3 /opt/openclaw/local/bitrix_app_server.py`.
- Исторический snapshot:
  - `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/server_snapshots/live_ams_1_vm_76ds_20260325`
  - содержит `/etc/cron.d/*`, `/usr/local/bin/*`, `/root/.openclaw/workspace/todo-integration`, `/opt/openclaw/local/bitrix_app_server.py`
  - не содержит env, tokens, logs, node_modules.

## 4. Основные архитектурные проблемы

### Критично

1. **Слишком много runtime-путей с похожей ролью.**  
   Лариса: `/opt/cloudbot-runtime/larisa/current`.  
   Sales/Лев: `/opt/cloudbot-runtime/current`.  
   Platform: `/opt/openclaw`.  
   Legacy todo: `/root/.openclaw/workspace/todo-integration`.  
   Legacy reports: `/home/ops/cloudbot-larisa-agent/reports`.  
   Ошибка в выборе `current` уже ранее ломала scheduled path Ларисы, это прямо описано в `larisa_live_contour_audit_20260325_MSK.md`.

2. **Shared env может ломать оба Telegram-контура.**  
   `.env.integrations` общий и вынесен в `/Users/pro2kuror/.config/openclo/assistant/.env.integrations`. В нем по шаблонам есть `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `LARISA_TELEGRAM_CHAT_ID`, `SALES_*`. Нужна жесткая agent-specific схема.

3. **Есть несколько entrypoint-слоев.**  
   Python path: `cloudbot/bot/telegram -> orchestrator -> workflows -> agents/providers`.  
   Shell path: `infra/orchestrator/run_workflow.sh -> workflows/*.sh`.  
   Legacy JS path: `OpenClo/incubator/openclaw-extensions/orchestrator.js`, `router.js`, `workflow.*.js`, `provider.*.js`.  
   Bot JS path: `bot/src/index.js`, `bot/scripts/scheduler_daemon.js`.

4. **Рабочий repo сильно dirty.**  
   В `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` много modified/deleted/untracked файлов, включая production-critical зоны и удаленные старые workflows. Перед любой миграцией нужен отдельный freeze/snapshot.

5. **На сервере рядом с активными cron лежит много `.bak` cron-файлов.**  
   Они не исполняются как cron-задачи, но визуально засоряют контур и повышают риск ручной ошибки при обслуживании.

### Средне

1. **`Cloudbot` решает проблему навигации symlink'ами, но не решает физическую структуру.**  
   Это безопасная обертка, но реальная миграция не завершена.

2. **Документы и runtime живут в разных git-контурах.**  
   `/Users/pro2kuror/Desktop/architect` и `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` оба активны и оба dirty.

3. **WHOOP есть в двух вариантах.**  
   Standalone: `/Users/pro2kuror/Desktop/OpenClo/projects/whoop`.  
   Runtime/provider: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/providers/whoop*` и серверный `/etc/cron.d/openclaw-whoop-report`.

4. **Лев Петрович и `sales_agent` сосуществуют.**  
   Это осознанный compatibility-слой, но пока миграция не завершена, есть риск править не тот слой.

5. **Paperclip рядом с Cloudbot может путать OpenClaw/OpenCloud naming.**  
   В `tools/paperclip` есть OpenClaw adapters, docker-compose и agent-runtime docs, но это внешний проект.

### Косметика

1. Названия `OpenClo`, `Cloudbot`, `CloudBot`, `OpenCloud` создают путаницу.
2. В `architect` лежат рабочие маркетинговые артефакты, pdf/png/docx/tmp рядом с Cloudbot docs.
3. В `OpenClo` рядом лежат `archive`, `incubator`, `projects` без жесткого визуального разделения “prod/dev/archive”.

## 5. Дубли и конфликты

### Похожие папки по роли

- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` и `/Users/pro2kuror/Desktop/Cloudbot/engineer`  
  Не дубль, а symlink. Риск низкий, если это явно известно.

- `/Users/pro2kuror/Desktop/architect` и `/Users/pro2kuror/Desktop/Cloudbot/architect`  
  Не дубль, а symlink. Риск низкий.

- `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` и `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/lev_petrovich`  
  Похожая роль sales/коммерческого директора. По документам `commercial-director` больше не source of truth.

- `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` и `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/*`  
  Оба содержат orchestrator/router/workflow/provider. Первый выглядит как экспериментальный JS-прототип, второй как канонический runtime.

- `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` и `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/providers/whoop*`  
  Standalone WHOOP sandbox против runtime/provider слоя.

- `/Users/pro2kuror/Desktop/tools/paperclip` и Cloudbot/OpenClo  
  Оба связаны с агентами/OpenClaw, но Paperclip — внешний orchestration product, не Cloudbot runtime.

### Дубли конфигов/env

- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.example`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.integrations.example`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/configs/app_config.env.example`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/configs/integrations.env.example`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.integrations -> /Users/pro2kuror/.config/openclo/assistant/.env.integrations`
- `/Users/pro2kuror/Desktop/OpenClo/projects/whoop/.env`
- `/Users/pro2kuror/Desktop/OpenClo/projects/whoop/.whoop_tokens.json`
- `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions/.env.example`
- `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions/.env.bitrix-oauth.example`
- Серверные env по документации: `/etc/openclaw/news_agent.env`, `/etc/openclaw/whoop.env`, `/opt/openclaw/.env`, `/opt/openclaw/.env.security_profile`, `/root/.openclaw/workspace/todo-integration/.env.runtime`

### Дубли scripts/workflows

- `scripts/deploy.sh`
- `devops/deploy.sh`
- `infra/orchestrator/workflows/larisa_agent_deploy.sh`
- `infra/orchestrator/workflows/sales_agent_deploy.sh`
- `infra/orchestrator/workflows/cloudbot_runtime_verify.sh`
- `infra/orchestrator/workflows/cloudbot_runtime_rollback.sh`
- `infra/orchestrator/workflows/cloudbot_runtime_unlock.sh`
- Старые server wrappers в snapshot: `/usr/local/bin/cloudbot-larisa-daily-brief.sh`, `/usr/local/bin/send_whoop_report.py`, `/usr/local/bin/send_moscow_weather.sh`

### Где настройка одного может ломать другое

- Общий `TELEGRAM_BOT_TOKEN` и fallback `TELEGRAM_CHAT_ID` могут затронуть Ларису и Льва.
- Общий `/opt/cloudbot-runtime/current` исторически мог ломать Ларису после sales deploy. Сейчас по документам Лариса вынесена в `/opt/cloudbot-runtime/larisa/current`, но live это в этом запуске не подтверждено.
- Общий `cloudbot/providers/*` и `cloudbot/orchestrator/*` используется несколькими агентами.
- `configs/schedule_contract.env` влияет на расписания нескольких контуров.
- `infra/orchestrator/lib.sh` содержит общую workflow-инфраструктуру.

## 6. Вердикт

**Лучше делать частичный rebuild.**

## 7. Почему именно такой вердикт

Текущая система не выглядит безнадежной: есть канонический repo, описанная карта runtime, выделенные агенты, тесты и workflow-обертки. Но она уже не лечится простой косметической реорганизацией, потому что:

- рядом существуют prod/dev/archive/incubator;
- есть несколько похожих runtime entrypoint'ов;
- Лариса и Лев частично разделены, но всё еще зависят от shared env/orchestrator/providers;
- server-only контуры пока не полностью сведены в repo;
- live server в текущем запуске не подтвержден, значит миграцию нельзя начинать “на доверии”.

Строить заново почти полностью не нужно: переносить следует живые компоненты в чистую схему, оставляя старую систему работающей до поэтапного cutover.

## 8. Предлагаемая целевая структура

Только проект решения. Ничего не применять без отдельной миграции.

```text
OpenCloud/
  apps/
    larisa_ivanovna/
      agent/
      workflows/
      prompts/
      config/
      telegram/
    lev_petrovich/
      agent/
      workflows/
      prompts/
      config/
      telegram/
    news_agent/
      agent/
      workflows/
      config/
    bot_gateway/
      telegram_ingress/
      command_router/

  shared/
    orchestrator/
    providers/
      bitrix/
      todo/
      whoop/
      search/
      telegram/
      openai/
    skills/
    formatting/
    time/
    logging/

  config/
    examples/
      larisa.env.example
      lev_petrovich.env.example
      shared.env.example
      schedules.env.example
    schemas/
    schedules/
      local.cron
      server.cron

  infra/
    orchestrator/
      run_workflow.sh
      workflows/
    deploy/
      larisa/
      lev_petrovich/
      rollback/
      verify/
    systemd/
    cron/
    docker/
    server_snapshots/

  runtime/
    README.md
    local_state_links.md

  data/
    README.md
    .gitkeep

  reports/
    README.md
    .gitkeep

  docs/
    architecture/
    runbooks/
    audits/
    roles/
    status/

  tests/
    unit/
    integration/
    smoke/

  archive/
    README.md
```

Что куда должно переехать в будущем:

- `OpenClo/projects/engineer/agents/larisa_ivanovna` -> `apps/larisa_ivanovna/agent`
- `OpenClo/projects/engineer/agents/lev_petrovich` -> `apps/lev_petrovich/agent`
- `OpenClo/projects/engineer/agents/sales_agent` -> временно `apps/lev_petrovich/legacy_sales_agent`, затем убрать после завершения compatibility migration
- `OpenClo/projects/engineer/cloudbot/orchestrator` -> `shared/orchestrator`
- `OpenClo/projects/engineer/cloudbot/providers` -> `shared/providers`
- `OpenClo/projects/engineer/cloudbot/skills` -> `shared/skills`
- `OpenClo/projects/engineer/infra/orchestrator` -> `infra/orchestrator`
- `OpenClo/projects/engineer/configs` -> `config`
- `OpenClo/projects/engineer/docs` + `/Users/pro2kuror/Desktop/architect/docs` -> `docs`, после дедупликации
- `OpenClo/incubator/openclaw-extensions` -> `archive/incubator/openclaw-extensions` или отдельный `experiments/`, если нужен
- `OpenClo/projects/commercial-director` -> `archive/commercial-director-pre-lev`
- `OpenClo/projects/whoop` -> либо `archive/whoop-standalone`, либо отдельный `apps/whoop_report`, если подтвердится live-роль
- `server_snapshots/*` -> `infra/server_snapshots`
- `tools/paperclip` -> не переносить в OpenCloud runtime; держать как внешний tool/project.

## 9. План безопасной миграции

1. **Freeze текущего состояния.**  
   Ничего не переносить. Зафиксировать git status обоих контуров: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` и `/Users/pro2kuror/Desktop/architect`.

2. **Восстановить read-only доступ к live server.**  
   Нужно поднять или предоставить активный SSH/proxy route для `cloudbot-ssh-proxy`. После этого выполнить только read-only audit: `ps`, `systemctl list/cat`, `docker ps`, `crontab -l`, `/etc/cron.d`, `find` по `/opt`, `/etc/openclaw`, `/root/.openclaw`, `/home/ops`, `/var/log`.

3. **Собрать live runtime map.**  
   Подтвердить:
   - что реально запущено;
   - какие cron/systemd/docker/service активны;
   - какие wrappers указывают на Ларису;
   - какие wrappers указывают на Льва/ sales;
   - где лежат env/log/state.

4. **Выделить “живое” без переноса.**  
   Составить allowlist живых путей:
   - Larisa live paths;
   - Lev/Sales live paths;
   - shared providers/orchestrator;
   - server-only integrations;
   - env paths без содержимого секретов.

5. **Создать target structure рядом, но не переключать prod.**  
   Например `/Users/pro2kuror/Desktop/OpenCloud-clean` или feature branch внутри repo. На этом этапе не менять cron/systemd/server.

6. **Перенести только кодовые слои в branch.**  
   Сначала `apps/larisa_ivanovna`, затем `apps/lev_petrovich`, затем `shared`. После каждого переноса запускать unit/smoke tests локально.

7. **Развести env-контракты.**  
   Создать отдельные example/schemas:
   - `larisa.env.example`
   - `lev_petrovich.env.example`
   - `shared.env.example`
   Реальные env не переносить в git.

8. **Развести runtime pointers.**  
   Зафиксировать правило:
   - Лариса использует только `/opt/cloudbot-runtime/larisa/current`.
   - Лев/ sales использует свой scoped runtime, а не generic shared pointer. Если generic нужен временно, пометить как legacy.

9. **Проверить оба Telegram-контура в staging/dry-run.**  
   Лариса: daily brief, tasks, meetings, search, Telegram delivery dry-run/live по разрешению.  
   Лев: daily, check, followup, weekly, Telegram delivery dry-run/live по разрешению.

10. **Cutover только после успешной проверки.**  
    Сначала один контур, потом второй. После каждого шага:
    - тесты;
    - smoke;
    - логи;
    - cron/systemd status;
    - ручная проверка Telegram delivery.

11. **Архивировать мусор только после стабильного периода.**  
    Не удалять. Перевести старые папки в `archive/` или оставить с README “не source of truth”.

## 10. Что мне отправить обратно в ChatGPT для следующего этапа

Отправить:

1. Полный executive summary из раздела 1.
2. Таблицу структуры из раздела 2.
3. Карту боевого контура из раздела 3.
4. Список дублей и конфликтов из раздела 5.
5. Итоговый вердикт: **Вариант B — частичный rebuild**.
6. Предложенную target structure из раздела 8.
7. Отдельно указать блокер: live-сервер не подтвержден, потому что в этом треде не работает локальный SSH proxy `127.0.0.1:2080` для alias `cloudbot-ssh-proxy`.

Минимальный текст для следующего этапа:

```text
Есть аудит OpenCloud/Cloudbot на 2026-04-23 МСК.
Вердикт: Вариант B — нужен частичный rebuild.
Локально подтвержден основной инженерный repo:
/Users/pro2kuror/Desktop/OpenClo/projects/engineer
alias:
/Users/pro2kuror/Desktop/Cloudbot/engineer
Документационный контур:
/Users/pro2kuror/Desktop/architect
alias:
/Users/pro2kuror/Desktop/Cloudbot/architect

Cloudbot — symlink-обертка, не физический перенос.
OpenClo содержит prod/dev/archive/incubator вперемешку.
Лариса: agents/larisa_ivanovna + cloudbot/orchestrator/providers + infra/orchestrator/workflows/larisa_*.sh.
Лев: agents/lev_petrovich + agents/sales_agent compatibility + scripts/run_sales_copilot.py + infra/orchestrator/workflows/sales_*.sh.
Главный риск: shared env, shared orchestrator/providers и несколько runtime pointers.
Сервер live в этом запуске не подтвержден: cloudbot-ssh-proxy зависит от локального SOCKS/proxy 127.0.0.1:2080, порт не слушал.

Нужен следующий этап: read-only live server audit, потом план target structure и безопасной миграции без остановки прода.
```
