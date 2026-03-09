# Cloudbot / OpenClaw Architecture

## orchestrator
- Оркестратор управляет запуском операций и стандартными workflow через `infra/orchestrator/run_workflow.sh`.
- Общие функции и окружение централизованы в `infra/orchestrator/lib.sh`.

## workflows
- Workflow в `infra/orchestrator/workflows/` покрывают ежедневные проверки, обновления, деплой и восстановление.
- Каждый workflow реализует пошаговый сценарий с отчетом в `reports/`.

## skills
- Skills расширяют поведение агента и задают стандартизированные процедуры выполнения задач.
- Используются для repeatable-операций: деплой, безопасность, интеграции, документация.

## providers
- Провайдеры в `bot/src/providers/` абстрагируют источники данных и интеграции.
- Основные источники: Bitrix, Todo/Todoist, внутренние источники и вспомогательные адаптеры.

## integrations
- Ключевые интеграции: Telegram, OpenAI, Bitrix, Todoist, WHOOP, Sentry, Notion.
- Проверки доступности и конфигурации выполняются скриптами в `scripts/` и `checks/`.

## search
- Поисковая логика подключается как отдельный провайдер/интеграция.
- Внешние API и ключи хранятся только в локальных env-файлах, не в git.

## telegram bot
- Telegram-бот в `bot/` является основным интерфейсом взаимодействия.
- Команды, расписания и уведомления реализованы в `bot/src/commands`, `bot/src/scheduler`, `bot/src/workflows`.

## devops
- Деплой и обслуживание автоматизируются через workflow и скрипты `scripts/deploy.sh`, `scripts/agent_commit.sh`.
- Backup изменений выполняется cron-задачей в 03:00 MSK.
- Отчеты и операционные логи сохраняются в `reports/`.
