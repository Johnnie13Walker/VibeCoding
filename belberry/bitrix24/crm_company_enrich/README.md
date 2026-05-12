# crm_company_enrich

Обогащение компаний Bitrix24 ИНН и реквизитами. Цель — закрыть техдолг ~1000
компаний без записи `RQ_INN`: обогатить их ИНН через web/UF/rusprofile и либо
создать реквизит, либо смержить с компанией-дубликатом, у которой реквизит
уже есть.

Форк по структуре `crm_deal_merge` — общий Bitrix-OAuth state, общая таблица
Google Sheets (отдельная вкладка `company_enrich_queue`), общий sync-script.

## Статус стадий

| Стадия | Тип | Реализация |
|---|---|---|
| `discover` | READ-only Bitrix + Sheets write | готова |
| `enrich-web` | HTTP fetch + Sheets write | готова |
| `classify` | READ-only Bitrix + Sheets write | готова |
| `mark-approved` | Sheets write | готова |
| `status` | Sheets read | готова |
| `apply` | WRITE Bitrix | **stub** (exit 2) |
| `merge-dupes` | WRITE Bitrix | **stub** (exit 2) |
| `verify` | READ-only Bitrix | **stub** (exit 2) |
| `rollback` | WRITE Bitrix | **stub** (exit 2) |

Write-стадии заморожены до завершения prod-run `crm_deal_merge transfer`
(PID 20750). Контракты каждой stub задокументированы в docstring файла
`stages/*.py`.

## Порядок запуска

```bash
cd belberry/bitrix24/crm_company_enrich
pip install -e .

bash ../../../shared/scripts/bitrix-sync-state.sh

python3 -m crm_company_enrich.cli discover
python3 -m crm_company_enrich.cli enrich-web --sample
python3 -m crm_company_enrich.cli enrich-web                   # без лимита
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
