# План миграции Bitrix duplicate merge

Дата: 2026-05-10 МСК.

## Вывод

Полный перенос возможен только как selective migration, не как копирование legacy workspace.

Переносить нужно бизнес-логику и тестовые контракты. Не переносить runtime-state, outputs, remote bridge, абсолютные пути, старые batch-результаты и любые секреты.

## Что найдено в legacy

Критичные компоненты:

- `bitrix_policy_merge_deals.py` - policy workflow: backup, нормализация конфликтов, preflight, штатный `crm.entity.mergeBatch`, rollback полей при неуспешном merge.
- `bitrix_safe_merge_deals.py` - низкоуровневый safe merge: backup сделок, product rows, контакты, activities, timeline comments, dry-run/apply.
- `bitrix_reanimation_merge_ledger.py` - JSONL ledger и idempotency по `operation_key`.
- `bitrix_reanimation_merge_sheet_sync.mjs` - синхронизация Google Sheet: перенос строк в `Объединено` или отметка ручного merge.
- `bitrix_app_auth.py` - OAuth client, refresh token, retry по rate limit, маскирование секретов.
- Unit-тесты по policy, ledger, OAuth и смежным функциям.

Актуальные workflow:

- Dry-run по группе сделок.
- Backup перед любыми изменениями CRM.
- Preflight risk scoring до apply.
- Нормализация части полей перед merge.
- Штатный Bitrix merge только через `crm.entity.mergeBatch`.
- Post-check целевой сделки и источников.
- Ledger для восстановления и защиты от повторного исполнения.
- Sheet sync после результата CRM.

Не переносить:

- Legacy `outputs/*` и batch state.
- `remote-bridge`, SSH, remote tar/state dump.
- Старые абсолютные пути к secrets и `/opt/openclaw`.
- Скрипты unrelated к duplicate merge: task reports, spam delete, workgroups, enrichment, calendar cleanup.
- `__pycache__`, сгенерированные XLSX/DOCX/CSV/JSON с CRM-данными.

## Dependency map

```text
batch engine
  -> config loader
  -> process lock
  -> google sheet provider
  -> group validator
  -> bitrix provider
  -> duplicate policy
  -> merge executor
  -> ledger
  -> sheet sync
  -> verifier
  -> structured logger
```

Scripts:

- Legacy `bitrix_policy_merge_deals.py` объединяет слишком много обязанностей. В новом контуре разделить на CLI entrypoint и сервисы.
- Legacy `bitrix_reanimation_merge_sheet_sync.mjs` полезен как reference, но Google client лучше переписать как provider с явным dry-run/apply и transaction log.

Providers:

- Bitrix provider: OAuth state, refresh, API call, pagination, retry, secret masking.
- Google provider: service account auth, Sheets read/update/batchUpdate, sheet metadata, guarded writes.

Policy:

- Canonical target должен быть явно выбран или вычислен по deterministic rule.
- Запрещены группы с разными компаниями, конфликтующими product signatures, большим числом активностей, добавлением контактов и группой больше 2 без manual review.

Outputs:

- Только локальные run artifacts в `outputs/runs/<run_id>/`.
- Формат: `input_snapshot.json`, `dry_run_plan.json`, `preflight.json`, `crm_backup.json`, `apply_result.json`, `postcheck.json`, `sheet_sync.json`.

State:

- Только новый isolated state в `state/`.
- Ledger: append-only JSONL.
- Lock: отдельный lock-файл.
- OAuth state: `state/bitrix-oauth/`, не переносить из legacy.

Tests:

- Перенести контрактные тесты policy и ledger.
- Добавить fake Bitrix/Google providers.
- Добавить тесты idempotency, lock, duplicate execution protection и post-run verification.

Google integration:

- Service account JSON через env.
- Таблица и листы через env/config.
- Права service account ограничить только нужной таблицей.

Bitrix OAuth:

- Новый локальный app state, новый install/handler flow или ручное безопасное заполнение state.
- Refresh token хранить только в gitignored `state/bitrix-oauth/`.

Merge policy:

- До merge обязательны dry-run, live CRM verification, duplicate validation, risk scoring.
- Apply требует явного флага и confirmation token.

Ledger:

- Operation key: `sheet_id|domain|target=<id>|ids=<ordered_ids>|policy_version=<version>`.
- Перед apply проверять, что operation key не был успешно применен.

Sync logic:

- Sheet update только после CRM post-check.
- При конфликте не архивировать строки, а писать статус ручной проверки и ссылку на штатный Bitrix merge.

## Что переписать

- Batch engine.
- Google Sheets client.
- CLI orchestration.
- Config loader и preflight validator.
- Lock/idempotency слой.
- Structured logging.

## Что можно портировать

- Алгоритм `build_policy_plan`.
- Правила high-conflict risk.
- OAuth refresh модель с маскированием секретов.
- Ledger classification/idempotency.
- Тестовые сценарии policy и ledger.

## Технический долг legacy

- Смешаны provider, policy, orchestration и CLI.
- Есть hardcoded portal URL и sheet URL.
- Есть fallback на абсолютный путь Google service account.
- Есть remote bridge и SSH/tar state sync.
- Ledger живет в outputs, а не в isolated state.
- Sheet sync изменяет Google Sheet без общего transaction model.
- Rollback покрывает только нормализованные поля, не сам merge.
