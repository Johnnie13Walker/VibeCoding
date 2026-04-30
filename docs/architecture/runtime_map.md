# Карта runtime-контуров

Документ фиксирует стартовую карту путей исполнения в текущем runtime-репозитории и нужен для контроля расхождений между Telegram, cron, manual run и deploy.

## Telegram path

Текущий путь:

`cloudbot/bot/telegram/telegram_handler.py`
-> `normalize_update`
-> `cloudbot/bot/telegram/commands.py`
-> `cloudbot/orchestrator/orchestrator.py`
-> `cloudbot/orchestrator/router.py`
-> `cloudbot/workflows/<workflow>.py`
-> `agents/*` или `cloudbot/providers/*`
-> `send_reply`

Что важно:

- Telegram-слой должен оставаться тонким.
- Бизнес-маршрутизация должна жить в orchestrator и workflow.
- Нельзя заводить отдельный боевой путь в обход orchestrator для тех же команд.

## Cron path

Текущий путь:

`configs/schedules.cron`
-> `infra/orchestrator/run_workflow.sh`
-> `infra/orchestrator/workflows/*.sh`
-> агентный CLI или bridge-скрипт
-> лог или отчет в `reports/*`

Текущие подтвержденные cron-сценарии:

- `larisa_daily_brief`
- `sales_brief`
- `news_digest`
- `sales_followup`
- `sales_weekly_review`

Канонический контракт расписаний:

- `configs/schedule_contract.env`
- описание и правила изменения: `docs/architecture/schedule_contract.md`

Что важно:

- Для локальных cron-конфигов используется `CRON_TZ=Europe/Moscow`, но server sales-cron в `/etc/cron.d` фиксируется явными UTC-выражениями, потому что production Debian cron не выдержал SLA `09:30/17:00/18:30` через `CRON_TZ`.
- Каждый cron-путь должен иметь один канонический shell wrapper.
- Нельзя держать параллельно старую и новую cron-реализацию без явной миграции.

## Manual run path

Текущие поддерживаемые входы:

- `make verify`, `make preflight`, `make openclaw.*`
- `infra/orchestrator/run_workflow.sh <workflow>`
- `python3 -m agents.larisa_ivanovna ...`
- `python3 -m agents.news_agent.news_agent ...`
- `python3 -m agents.lev_petrovich ...`
- `python3 -m agents.sales_agent.sales_agent ...` только как compatibility-path до завершения миграции

Что важно:

- Ручной запуск нужен для диагностики, smoke и controlled execution.
- Если для боевого сценария уже существует workflow, production-операция должна идти через workflow, а не через произвольный прямой CLI.

## Deploy path

В текущем репозитории явно присутствует operational deploy path:

- `infra/orchestrator/workflows/larisa_agent_deploy.sh`
- `infra/orchestrator/workflows/news_agent_deploy.sh`

Архитектурное замечание:

- В операционных инструкциях может встречаться ссылка на `scripts/deploy.sh`, но в текущем runtime-репозитории такой канонический deploy entrypoint не подтвержден.
- До отдельной верификации каноническим deploy path следует считать путь через `infra/orchestrator/run_workflow.sh`.

Целевой server delivery contour для agent runtime:

- staging release: `/opt/cloudbot-runtime/larisa/releases/.<release_id>.staging`
- immutable release: `/opt/cloudbot-runtime/larisa/releases/<release_id>`
- live symlink: `/opt/cloudbot-runtime/larisa/current`
- deploy lock: `/opt/cloudbot-runtime/larisa/.deploy.lock`
- explicit news env: `/etc/openclaw/news_agent.env`
- system runner должен делать `cd /opt/cloudbot-runtime/larisa/current`
- cron может временно продолжать писать stdout/stderr в legacy `reports` до завершения cutover

Статус:

- локальные deploy-скрипты и server wrappers Ларисы переведены на release-based runtime в scoped-контуре `/opt/cloudbot-runtime/larisa`
- release deploy теперь должен идти строго через shared remote lock
- server cutover для `larisa` и `news` уже выполнен
- старые `/home/ops/cloudbot-larisa-agent` и `/home/ops/cloudbot-news-agent` остаются только legacy/report path
- для stale lock добавлен operational workflow: `infra/orchestrator/workflows/cloudbot_runtime_unlock.sh`
- для `news` зафиксирован явный server env path: `/etc/openclaw/news_agent.env`
- rollback/unlock/verify Ларисы должны по умолчанию смотреть в `/opt/cloudbot-runtime/larisa/*`
- общий `/opt/cloudbot-runtime/current` остаётся отдельным generic release pointer и на live-хосте сейчас используется server wrapper'ами sales; его нельзя считать каноническим runtime Ларисы без отдельного подтверждения

## Пост-измененческий verify path

Текущий путь:

- `make verify`
- `make openclaw.post-change-verify`
- `checks/smoke_test.py`
- дополнительные `bot` smoke и `checks/*`

Что важно:

- Smoke должен быть детерминированным.
- Mock и live-проверки должны различаться явно.
- Принятие изменения без post-change verify недопустимо.

## Канонический entrypoint: место для фиксации

Текущее подтвержденное состояние:

- Telegram ingress: `TBD`
- Scheduled ingress: `TBD`
- Manual operator ingress: `TBD`
- Deploy ingress:
  - `infra/orchestrator/workflows/larisa_agent_deploy.sh`
  - `infra/orchestrator/workflows/news_agent_deploy.sh`
  - live runtime target: `/opt/cloudbot-runtime/larisa/current`
- Rollback ingress:
  - `infra/orchestrator/workflows/cloudbot_runtime_rollback.sh`
  - default runtime target: `/opt/cloudbot-runtime/larisa/current`
- Verify ingress:
  - `infra/orchestrator/workflows/cloudbot_runtime_verify.sh`
  - default runtime target: `/opt/cloudbot-runtime/larisa/current`
- Статус подтверждения: `подтвержден для larisa/news`

## Риски расхождения между путями

- Telegram path идет через Python orchestrator, а часть legacy-контуров сохранена в JS.
- Cron path идет через shell wrappers и может расходиться с тем, что запускается вручную.
- Sales Copilot зависит от live env/state на сервере, поэтому локальный код и серверный runtime могут расходиться даже при одинаковом git commit.
- Deploy path и operational инструкции нужно сверять отдельно, иначе команда будет чинить один контур, а выкатывать другой.
- Cron всё ещё пишет в legacy `reports`, хотя live runtime Ларисы уже перенесён в `/opt/cloudbot-runtime/larisa/current`.
- News runtime больше не зависит от скрытого env node-процесса, но остаётся зависимым от явного server env.
- `news_agent.env` живёт вне git; его состояние нужно учитывать при change-control и server audit.
- Параллельный deploy в shared runtime path запрещен; для Ларисы и generic runtime нужны разные lock-path и явная область действия команды.
- Stale remote lock после аварийного обрыва deploy надо уметь локализовать и снимать осознанно.
- Архивные и инкубационные папки рядом с runtime-репозиторием создают риск взять не тот source of truth.

## Recovery path для deploy lock

Допустимые режимы:

- inspect: `infra/orchestrator/run_workflow.sh cloudbot_runtime_unlock inspect`
- release: `ALLOW_LOCK_RELEASE=1 infra/orchestrator/run_workflow.sh cloudbot_runtime_unlock release`

Что важно:

- `release` нельзя вызывать без явного подтверждения.
- Перед release нужно проверить `owner` и `acquired_at`.
- Если lock живой и deploy ещё идёт, release запрещён.

## Runtime rollback ingress

Доступные режимы:

- inspect: `infra/orchestrator/run_workflow.sh cloudbot_runtime_rollback inspect`
- apply: `infra/orchestrator/run_workflow.sh cloudbot_runtime_rollback apply <release_id>`

Что важно:

- rollback не трогает env/state и не переписывает wrappers/cron;
- target release нужно указывать явно;
- перед переключением проверяется наличие `RELEASE_COMMIT`;
- rollback по умолчанию использует lock scoped runtime Ларисы; generic runtime нужно указывать явным override.

## Runtime verify ingress

Канонический путь:

- `infra/orchestrator/run_workflow.sh cloudbot_runtime_verify`

Что важно:

- verify не отправляет боевые сообщения;
- manual проверки `larisa` и `news` идут только в `TELEGRAM_DRY_RUN=1`;
- verify проверяет `current`, release metadata, wrappers, cron, `news_agent.env` и свежие отчеты в `current/reports`.

## Что Архитектор обязан проверять в первую очередь

- Совпадает ли workflow в Telegram path и cron path для одного сценария.
- Есть ли у каждого cron-сценария единственный shell wrapper.
- Не обходит ли manual run канонический runtime без необходимости.
- Не держит ли deploy отдельный, недокументированный путь.
- Не зависит ли боевой сценарий от скрытого server state.
