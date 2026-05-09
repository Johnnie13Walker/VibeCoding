# Аудит live-контура Ларисы Ивановны

Дата: `2026-03-25 MSK`
Хост: `ams-1-vm-76ds`

> Историческая заметка: выводы ниже относятся к состоянию на `2026-03-25`.
> После последующего cutover канонический live runtime Ларисы смещён в scoped-контур `/opt/cloudbot-runtime/larisa/current`.
> На `2026-03-29` live wrapper'ы Ларисы уже используют `/opt/cloudbot-runtime/larisa/current`, а общий `/opt/cloudbot-runtime/current` подтверждён как отдельный generic/sales runtime pointer.

## Краткий вывод

На момент аудита единый контур Ларисы не собран.

Есть три слоя:
- новый git-контур `cloudbot` + `agents/larisa_ivanovna`
- legacy JS compatibility-хвост внутри runtime-репозитория
- активный server-only слой OpenClaw (`todo-integration`, отдельные cron и shell-скрипты)

Дополнительно подтверждена отдельная проблема release delivery:
- active cron Ларисы на сервере указывает на `/opt/cloudbot-runtime/current`
- текущий `current` release не содержит `run_larisa_daily_brief_from_runtime_env.sh`
- из-за этого scheduled path нового контура Ларисы сейчас сломан

## Что реально активно

### Новый repo-контур

Активен как кодовая база и Telegram routing path:
- `cloudbot/bot/telegram/telegram_handler.py`
- `cloudbot/orchestrator/router.py`
- `cloudbot/workflows/*.py`
- `agents/larisa_ivanovna/*`

Активен как intended source of truth, но не полностью активен как live scheduler.

### Server-only слой

Реально активны:
- `/etc/cron.d/openclaw-todo-digest`
- `/etc/cron.d/openclaw-moscow-weather`
- `/etc/cron.d/openclaw-whoop-report`
- контейнер `openclaw-openclaw-gateway-1`
- workspace `/root/.openclaw/workspace/todo-integration`

Именно этот слой сейчас продолжает отправлять персональные сообщения по задачам и исполнять assistant-like scheduler jobs.

### Broken scheduled path нового контура

Реально активен cron:
- `/etc/cron.d/cloudbot-larisa-daily-brief`
- `/usr/local/bin/cloudbot-larisa-daily-brief.sh`

Но сам запуск broken, потому что в active release отсутствует `run_larisa_daily_brief_from_runtime_env.sh`.

## Причина расхождения

На момент аудита deploy-скрипты `larisa`, `news` и `sales` использовали общий `CURRENT_LINK=/opt/cloudbot-runtime/current`.

При этом:
- `larisa_agent_deploy.sh` создаёт `run_larisa_daily_brief_from_runtime_env.sh`
- `news_agent_deploy.sh` тоже создаёт larisa/news runner'ы
- `sales_agent_deploy.sh` переключает тот же `current`, но создаёт только `run_sales_*`

Это означает, что sales deploy может перетереть shared runtime release и сломать scheduled path Ларисы.

Состояние на `2026-03-29`:
- `larisa` использует scoped runtime `/opt/cloudbot-runtime/larisa/current`
- общий `/opt/cloudbot-runtime/current` остаётся отдельным generic runtime pointer для sales-wrapper'ов
- rollback/unlock/verify для Ларисы должны смотреть в scoped runtime по умолчанию

## Что сохранено этим коммитом

В `server_snapshots/live_ams_1_vm_76ds_20260325/` добавлены:
- live cron-конфиги
- live wrapper'ы
- server-only `todo-integration`
- `bitrix_app_server.py`

Это не финальная архитектура, а git-сохранение фактического состояния для последующей миграции.
