# Runbook duplicate merge

Дата: 2026-05-10 МСК.

## Запреты

- Не запускать merge автоматически.
- Не изменять CRM без explicit apply.
- Не использовать legacy runtime state.
- Не использовать remote tar, SSH bridge или старые абсолютные пути.
- Не удалять сделки вручную.

## Минимальный безопасный процесс

1. Проверить `.env` и доступы.
2. Запустить config preflight.
3. Получить snapshot Google Sheet.
4. Выполнить dry-run по одной группе.
5. Проверить risk score, CRM snapshot и expected merge target.
6. Запросить явное apply-подтверждение.
7. Перед apply повторить live CRM verification.
8. Выполнить штатный `crm.entity.mergeBatch`.
9. Проверить CRM, ledger и Google Sheet.
10. Зафиксировать run summary в `outputs/runs/<run_id>/`.

## Recovery

Если CRM apply успешен, а Sheet sync упал, не повторять merge. Нужно восстановиться из ledger и повторить только sheet sync.

Если результат CRM неизвестен, не делать повторный apply. Нужно выполнить live reconcile по всем deal IDs и вручную классифицировать состояние.
