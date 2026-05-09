# Handoff Для Нового Агента (MSK)

Обновлено: 2026-03-05

## Что почти наверняка поймут неправильно
1. Что `health-check` и `daily status` можно отправлять в любое утреннее время.
   Правильно: ежедневный статус должен приходить до 09:30 МСК.
2. Что проверка интеграций = наличие переменных.
   Правильно: нужен фактический smoke/read вызов.
3. Что `DRY_RUN`-успех равен боевой готовности.
   Правильно: боевая готовность подтверждается только прогоном `DRY_RUN=0`.

## Стартовые команды
1. `DRY_RUN=1 make openclaw.post-change-verify`
2. `DRY_RUN=1 make openclaw.daily-ops`
3. `make openclaw.next-week-prep`

## Главные артефакты
1. `reports/daily_ops_*_MSK.txt`
2. `reports/incidents/daily_ops_incident_*_MSK.md`
3. `reports/next_week_prep_*_MSK.md`
4. `reports/context/context_snapshot_*_MSK.md`

## Приоритеты
1. Доставка обязательного статуса владельцу.
2. Устранение инцидентов до закрытия задачи.
3. Минимизация ручных действий через orchestrator workflow.
