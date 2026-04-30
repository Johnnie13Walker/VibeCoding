# Cloudbot Personal AI Assistant

Cloudbot — персональный AI-ассистент на базе OpenClaw с интерфейсом в Telegram.

## Ключевые компоненты
- `cloudbot/bot/telegram` — Telegram interface
- `cloudbot/orchestrator` — центральная маршрутизация сценариев
- `cloudbot/workflows` — пользовательские сценарии ассистента
- `cloudbot/skills` — атомарные навыки
- `cloudbot/providers` — интеграции с внешними API
- `cloudbot/devops` — health-check, диагностика, мониторинг, backup

## Интеграции
- Telegram
- OpenAI
- Bitrix
- Google Calendar OAuth
- Todo
- WHOOP
- Web Search

## Быстрый запуск
```bash
python3 checks/smoke_test.py
```

## Контур Ларисы Ивановны
- Основной агент: `agents/larisa_ivanovna/`
- Публичные команды: `/today`, `/brief`, `/day`, `/meetings`, `/tasks`, `/weather`, `/plan-day`, `/plan`
- Плановый запуск: cron `09:00` МСК через workflow `larisa_daily_brief`
- Отдельный News-контур и команда `/news` удалены из активной архитектуры
