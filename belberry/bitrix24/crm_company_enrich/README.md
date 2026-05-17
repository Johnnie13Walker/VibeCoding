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
| `sync-deals` | WRITE Bitrix | готова; дозаполняет поля активных сделок из обогащённой компании |
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

# После apply/verify можно дозаполнить связанные сделки из карточки компании:
python3 -m crm_company_enrich.cli sync-deals --company-id 42
python3 -m crm_company_enrich.cli sync-deals --company-id 42 --live
python3 -m crm_company_enrich.cli sync-deals --deal-id 100 --include-closed --telemarketing-workflow --live
# После точечного sync-deals можно сразу объединить дубли сделок только
# этой компании в воронке телемаркетинга:
python3 -m crm_company_enrich.cli sync-deals --company-id 20606 --live --dedupe-telemarketing
```

`sync-deals` по умолчанию работает в dry-run и требует явный `--company-id`
или `--deal-id`. Без `--overwrite` стадия заполняет только пустые поля сделки:
«Сайт клиента», «Город», «ИНН», «Оборот», «Сфера деятельности» и
«Бренд проекта» — только если соответствующее значение уже есть на компании.
Флаг `--dedupe-telemarketing` после синхронизации запускает scoped dedupe
только для этой компании: если у неё несколько открытых сделок в C50, loser-ы
закрываются как дубли, без глобального прохода по порталу.

## Apply: реквизиты и BP

При первичном внесении реквизитов `apply` выполняет двухступенчатое обогащение:

1. `crm.requisite.add` создаёт реквизит компании по ИНН.
2. `start_workflow(CCE_BIZPROC_FIRST_ENTRY_ID=5938)` запускает BP
   «Изменение компании и заполнение данных»; он отрабатывает быстро.
3. Короткая пауза до 3 секунд даёт первому BP завершить мгновенные изменения.
4. `start_workflow(CCE_BIZPROC_UPDATE_ID=8612)` запускает BP
   «Обновление компании и заполнение данных»; он подтягивает ЕГРЮЛ/ДаДата
   около 4 минут.
5. `apply` ждёт `CCE_BIZPROC_WAIT_S` (по умолчанию 15 секунд).
6. `verify_with_retries` дочитывает реквизиты, статус, адрес и выручку; если
   основной BP ещё не успел завершиться, verify-цикл повторяет чтение.

## Ручной процесс для сайтов телемаркетинга

Если по компании уже есть сделка в воронке телемаркетинга, новую сделку не
создавать. Нужно брать существующую сделку, даже если она закрыта, дозаполнять
её через `sync-deals --deal-id <id> --include-closed --live`, переводить в
`C50:NEW` через `--telemarketing-workflow`.

Ответственные телемаркетинга:

- Дарья Исаева — `2772`;
- Аркадий Вострецов — `2832`.

Если сделки нет, новую сделку назначать по очереди: `2772`, затем `2832`, затем
снова `2772`. Для автоматизированных/пакетных прогонов индекс очереди передаётся
как `--rotation-index`: `0` означает Дарью, `1` — Аркадия.

Если сделка уже есть в отказе (`C50:APOLOGY`, `C50:LOSE`, `C50:UC_1S1KIU`), новую
не создавать: вернуть существующую сделку в `C50:NEW`, поставить `CLOSED=N`,
`SOURCE_ID=12` и переназначить. Если отказная сделка была на Дарье, вернуть её
Аркадию; если была на Аркадии, вернуть Дарье. Если отказная сделка была на другом
ответственном, назначить по ротации.

Если существующая сделка не в отказе, `--telemarketing-workflow` не меняет
ответственного, но всё равно фиксирует целевую воронку, стадию, источник и
`CLOSED=N`.

Новая сделка допустима только если у компании вообще нет сделки в нужной
воронке. Перед созданием обязательно проверить дубли по ИНН, реквизитам,
домену/title и списку сделок компании.

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
