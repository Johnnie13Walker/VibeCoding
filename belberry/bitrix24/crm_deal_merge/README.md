# crm_deal_merge

Merge-engine для сделок Bitrix24 в воронках `[38] Реанимация` и `[50] Телемаркетинг`.

Группировка выполняется по ключу `(company_id, нормализованный домен из TITLE)`. Если домен не извлечён или в группе меньше двух сделок, группа уходит в `MANUAL` и автоматически не переносится.

## Порядок запуска

```bash
cd /Users/pro2kuror/Desktop/VibeCoding/tmp/crm_deal_merge_worktree/belberry/bitrix24/crm_deal_merge

bash ../../../shared/scripts/bitrix-sync-state.sh

python3 -m crm_deal_merge.cli discover-v2
python3 -m crm_deal_merge.cli inventory
# Smart-process parentId2 поиск на этом портале медленный, включать отдельно:
# python3 -m crm_deal_merge.cli inventory --include-sp
python3 -m crm_deal_merge.cli classify

# После ручного ревью листа merge_groups:
python3 -m crm_deal_merge.cli mark-approved --all --status PLAN_READY

# Пилот. Сначала только план, потом перенос.
python3 -m crm_deal_merge.cli transfer --dry-run --limit 3
python3 -m crm_deal_merge.cli transfer --limit 3
python3 -m crm_deal_merge.cli close-loser --dry-run --limit 3
python3 -m crm_deal_merge.cli close-loser --limit 3
python3 -m crm_deal_merge.cli verify

python3 -m crm_deal_merge.cli status
```

`transfer` и `close-loser` являются write-стадиями. Перед ними CLI запускает `bitrix-sync-state.sh`. Без `approved=1` и `status=APPROVED` перенос не стартует.

## Команды

- `discover-v2` — загружает сделки `[38]+[50]`, нормализует домен, выбирает WINNER и пишет `merge_groups`.
- `inventory [--limit N]` — собирает активности, timeline-комментарии, контакты и смарт-процессы LOSER в `merge_inventory`.
- `classify` — переводит `INVENTORIED` в `PLAN_READY`, спорные группы в `MANUAL`.
- `mark-approved --all --status PLAN_READY` — массовый approval после ручного ревью.
- `mark-approved --company-id ID --domain DOMAIN` — approval одной группы.
- `transfer [--dry-run] [--limit N] [--group COMPANY_ID:DOMAIN]` — переносит связи LOSER на WINNER, создаёт backup-лист.
- `close-loser [--dry-run] [--limit N]` — закрывает LOSER в `C38:3` или `C50:APOLOGY`.
- `verify` — read-only проверка инвариантов после закрытия.
- `rollback --company-id ID --domain DOMAIN --confirm-rollback` — аварийный rollback по backup-листу.
- `status` — счётчики статусов и LOSER.

## Safety

- Ничего не удаляется из Bitrix.
- Сделки без `COMPANY_ID` не трогаются.
- `VOXIMPLANT_CALL` не переносится и помечается как `not_transferable`.
- Перед `crm.deal.update` выполняется TITLE safety check: домен в живой сделке должен совпасть с доменом группы.
- Статус группы flush-ится после каждой обработанной группы.

## Known limitations

- `rollback` не отвязывает контакты, добавленные на WINNER при `transfer`; при откате их нужно удалить вручную через UI.
- `rollback` использует `reassign_activity` для всех типов активностей. Для `TASKS` это не зеркально переносит `UF_CRM_TASK` обратно; нужен ручной откат задачи или отдельная симметричная доработка.
- Эти ограничения не влияют на основной flow `transfer -> close-loser -> verify`, но критичны, если `rollback` используется как escape hatch.
