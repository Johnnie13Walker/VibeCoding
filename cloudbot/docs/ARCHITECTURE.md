# Архитектура Cloudbot

Cloudbot организован как модульная система персонального AI-ассистента с центральным `orchestrator`.

## Слои
- `cloudbot/bot/telegram` — тонкий Telegram-слой (прием update, нормализация, передача в orchestrator, отправка ответа).
- `cloudbot/orchestrator` — маршрутизация входящего сообщения в workflow.
- `cloudbot/workflows` — бизнес-сценарии (`day_briefing`, `meetings_summary`, `tasks_summary`, `whoop_report`).
- `cloudbot/skills` — атомарные действия, независимые от Telegram.
- `cloudbot/providers` — интеграции с внешними API.
- `cloudbot/devops` — системные проверки, диагностика, мониторинг, backup.

## Принцип совместимости
Существующие рабочие JS-модули сохранены. Новые Python-файлы выступают адаптерами и вызывают legacy-код через `cloudbot/compat/node_bridge.py`.
