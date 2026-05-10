# API-интеграции Cloudbot

## Telegram
- Интерфейс общения с пользователем.
- Входящий `update` обрабатывается в `cloudbot/bot/telegram/telegram_handler.py`.

## OpenAI
- Используется как интеллект ассистента в orchestrator/workflows (через существующие интеграции проекта).

## Bitrix
- Провайдер app-state: `cloudbot/providers/bitrix/bitrix_app_auth.py`.
- Sales adapter: `cloudbot/providers/bitrix/bitrix_sales_adapter.py`.
- Общий provider/health-check: `cloudbot/providers/bitrix_provider.py`.
- Sales data skill: `cloudbot/skills/bitrix_sales_data.py`.
- Skills: `cloudbot/skills/create_bitrix_event.py`, `cloudbot/skills/get_bitrix_calendar.py`.
- Источник авторизации: локальное приложение Bitrix24 через `BITRIX_APP_STATE_DIR`.

## Google Calendar OAuth
- В текущем инженерном контуре подтверждён как auxiliary/server-side path, а не как отдельный основной provider-модуль.
- Следы runtime-пути есть в `infra/orchestrator/workflows/todo-digest-remediate.apply.remote.sh` через команды `connect_google` и `oauth_google`.
- Если этот контур участвует в боевом сценарии, он должен описываться в operational registry отдельно от `Bitrix calendar`, а не жить только в текстах отчётов.

## Todo
- Провайдер: `cloudbot/providers/todo_provider.py`.
- Skill: `cloudbot/skills/get_todo_tasks.py`.

## WAZZUP / WhatsApp
- Используется Sales Copilot bridge через `WAZZUP_API_KEY` и `WAZZUP_API_BASE_URL`.
- Для live-проверки интеграций используется endpoint `GET /v3/channels`.
- `WAZZUP_WEBHOOK_FORWARD_URL` и часть WAZZUP runtime-контура могут жить в server-side `/opt/openclaw/.env`; это не должно трактоваться как `Не настроено`, если локальный workspace не видит эти переменные напрямую.

## WHOOP
- Провайдер: `cloudbot/providers/whoop_provider.py`.
- Skill: `cloudbot/skills/get_whoop_data.py`.
- Боевой OAuth/env-контур может жить server-side в `whoop.env` и связанных cron/report scripts; локальный `/health` не должен объявлять WHOOP `Не настроено`, если server runtime подтверждён.

## Web Search
- Провайдер: `cloudbot/providers/search_provider.py`.
- Skill: `cloudbot/skills/web_search.py`.

## Obsidian
- Тип интеграции: файловый Markdown vault с синхронизацией через private GitHub repository.
- Боевой путь vault: `OBSIDIAN_VAULT_PATH`, по умолчанию `/srv/cloudbot/obsidian-vault`.
- Git remote: `OBSIDIAN_GIT_REMOTE`.
- Timezone для daily notes и пользовательских сообщений: `Europe/Moscow`.
- Целевые provider/skills описаны в `shared/docs/integrations/obsidian_vault.md`.
- Vault не должен содержать `.env`, токены, private keys и другие секреты.

## Контур Ларисы Ивановны
- Канонический агент: `apps/larisa_ivanovna/`.
- Compatibility shim: `agents/larisa_ivanovna/`.
- Workflow-адаптеры: `cloudbot/workflows/day_briefing.py`, `cloudbot/workflows/meetings_summary.py`, `cloudbot/workflows/tasks_summary.py`, `cloudbot/workflows/larisa_weather.py`, `cloudbot/workflows/larisa_plan_day.py`.
- Telegram-команды: `/today`, `/brief`, `/day`, `/meetings`, `/tasks`, `/weather`, `/plan-day`, `/plan`.
