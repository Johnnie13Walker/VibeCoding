# Runbook: Rollback

## Цель
Быстро вернуть стабильную версию сервиса при неудачном деплое.

## Preconditions
- Известен предыдущий стабильный релиз.
- Есть доступ к серверу и CI/CD.
- Подготовлены миграции с обратной совместимостью.

## Процедура
1. Остановить rollout новой версии.
2. Откатить приложение на `last-known-good`.
3. Проверить health endpoint и ключевые user-flows.
4. Проверить ошибки и latency в мониторинге.
5. Сообщить команде о состоянии после rollback.

## Команды (пример)
- Docker:
  - `docker compose pull app:<stable_tag>`
  - `docker compose up -d app`
- Systemd:
  - `sudo systemctl restart <service>`
  - `systemctl status <service>`

## После отката
- Временно заблокировать повторный деплой проблемной версии.
- Создать задачу на root cause analysis.
- Добавить тест/чек, который предотвратит повторение.

