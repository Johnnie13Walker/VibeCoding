# crm_company_enrich

Обогащение компаний Bitrix24 ИНН и реквизитами. Текущая цель — закрыть остаток
deal-merge групп, которые не прошли smart-фильтр из-за отсутствующего `RQ_INN`:
обогатить ИНН через domain/WEB/UF/rusprofile и либо создать реквизит, либо
зафиксировать, что ИНН уже есть у текущей/другой компании.

Форк по структуре `crm_deal_merge` — общий Bitrix-OAuth state, общая таблица
Google Sheets (отдельная вкладка `company_enrich_queue`), общий sync-script.

## Статус стадий

| Стадия | Тип | Реализация |
|---|---|---|
| `discover` | READ-only Bitrix + Sheets write | готова; источник — `merge_groups` (`PLAN_READY`, `ИНН=—`, domain непустой) |
| `enrich-web` | HTTP fetch + Sheets write | готова |
| `classify` | READ-only Bitrix + Sheets write | готова |
| `mark-approved` | Sheets write | готова |
| `status` | Sheets read | готова |
| `apply` | WRITE Bitrix | готова; запускать только после явного go и сначала с `--dry-run` |
| `merge-dupes` | WRITE Bitrix | stub |
| `verify` | READ-only Bitrix | готова для `APPLIED_PENDING_BP` |
| `rollback` | WRITE Bitrix | **stub** (exit 2) |

До явного подтверждения пользователя выполняются только `discover`,
`enrich-web`, `classify` и `status`. `apply` не запускать.

## Порядок запуска

```bash
cd belberry/bitrix24/crm_company_enrich
pip install -e .

bash ../../../shared/scripts/bitrix-sync-state.sh

python3 -m crm_company_enrich.cli discover
CCE_ENRICH_HTTP_TIMEOUT_S=4 CCE_ENRICH_HTTP_RETRIES=1 \
  CCE_ENRICH_HTTP_DELAY_S=0.1 \
  python3 -m crm_company_enrich.cli enrich-web --limit 30
python3 -m crm_company_enrich.cli classify
python3 -m crm_company_enrich.cli status --detailed

# После ручного ревью листа company_enrich_queue:
python3 -m crm_company_enrich.cli mark-approved --all --status CLASSIFIED
# Точечный approve с явным action:
python3 -m crm_company_enrich.cli mark-approved --company-id 42 --action MERGE_INTO --target 100
```

## Safety guards

1. **Bitrix-write только в стадиях со словом «WRITE».** Discover, enrich-web,
   classify, mark-approved Bitrix не модифицируют.
2. **in_active_deal_merge=1** — для компаний, которые сейчас являются
   `winner`/`loser` в активной строке `merge_groups` (статусы APPROVED /
   TRANSFERRED / MERGED / MANUAL), enrich-web и classify пропускаются без
   обращений к Bitrix.
3. **Валидация ИНН формата** (10/12 цифр) перед любой попыткой записи
   (`is_valid_inn_format`). Контрольная сумма доступна в
   `inn_checksum_ok`, но не блокирует pipeline.
4. **mark-approved для MERGE_INTO** требует валидного реквизита у target
   company (read-only проверка через `bx.list_company_requisites`).
5. **HTTP fetcher** изолирован за `HttpFetcher` — в тестах подменяется
   monkeypatch'ем, ни одного реального HTTP-вызова в pytest.

## Тесты

```bash
pytest tests/ -v
```

Все тесты гоняются без Bitrix и без Google Sheets: `BitrixClient` и
`SheetsClient` подменяются `FakeBitrix` / `FakeSheets`. HTTP заглушается
custom-callable.

## Конфигурация

Все пути конфигурируются через env (см. `config.py`):

- `CCE_STATE_PATH` — OAuth state Bitrix24 (общий с deal-merge)
- `CCE_SHEET_ID` — Google Sheet (общий с deal-merge, лист
  `company_enrich_queue` создаётся при первом запуске discover)
- `CCE_LOG_DIR` — куда писать CSV-лог API-вызовов
- `CCE_SERVICE_ACCOUNT_JSON` — путь к service-account ключу

## Полная ТЗ

Спецификация фиксируется в commit-message корневого коммита ветки
`feature/crm_company_enrich`. Stub-стадии содержат подробные docstring с
контрактом будущей реализации.
