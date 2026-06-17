# sales_dashboard

ETL Bitrix24 → Google Sheets → **Looker Studio**. Дашборд по продажам и
телемаркетингу. Доступ — по личным gmail-аккаунтам, **управляется
автоматически** на основе ACTIVE-статуса пользователя в Bitrix24.

## Архитектура

```
Bitrix24 REST API
   │  (crm.deal.list, voximplant.statistic.get, user.get, crm.dealcategory.*)
   ▼
sales_dashboard.cli etl           ← cron */15 мин
   │   raw extractors → upsert по ключу
   ▼
Google Sheet (вкладки)
   • deals, calls, users, stages, categories
   • daily_metrics, manager_kpi  (опц., считаем формулами в Sheet)
   • sync_log
   ▼
Looker Studio (онлайн-дашборд)
   ▲
   │  permissions = Bitrix active users
sales_dashboard.cli user-sync     ← cron каждые 15 мин со сдвигом
```

## Что показывается в дашборде (план визуала)

**Страница 1 — Продажи (воронка)**
- Funnel: количество и сумма сделок по стадиям × воронка
- Conversion rate стадия → стадия
- Avg deal size, win rate, средний цикл сделки
- Pipeline coverage (открытые сделки)
- Срез по менеджеру, источнику, городу

**Страница 2 — Телемаркетинг**
- Звонков всего / дозвон / разговоров >30с (по дням)
- Талк-тайм на менеджера
- Heatmap по часам и дням недели
- Конверсия звонок → активность → сделка
- Топ-10 «горячих» номеров (несколько попыток)

**Страница 3 — KPI менеджеров**
- Карточка на каждого: звонки/часы/сделки/выручка
- Сравнение план vs факт (план в отдельном tab Sheet)
- Лидерборд

## Структура проекта

```
sales_dashboard/
  pyproject.toml
  README.md                                  ← вы здесь
  sales_dashboard/
    config.py                                ← все настройки
    bitrix_client.py                         ← read-only REST клиент
    sheets_client.py                         ← Sheets + Drive permissions
    extractors/
      deals.py                               ← crm.deal.list по DATE_MODIFY
      calls.py                               ← voximplant.statistic.get
      users.py                               ← user.get + dealcategory.* + stage.list
    etl.py                                   ← оркестратор
    user_sync.py                             ← Bitrix active → Drive share
    cli.py                                   ← entry point
  scripts/
    cron_etl.sh                              ← */15 cron wrapper
    cron_user_sync.sh                        ← user-sync cron
  tests/
    test_bitrix_helpers.py                   ← smoke-тесты helpers
  state/                                     ← .json со штампами last_run
  logs/                                      ← csv-лог API-вызовов
```

## Установка

### 1. Создать Google Sheet и расшарить на сервис-аккаунт

1. Создать новый Sheet, скопировать `SHEET_ID` из URL.
2. Расшарить на сервисник
   `finance-director-sheets@<project>.iam.gserviceaccount.com` (берётся
   из `.config/vibecoding/assistant/secrets/finance-director-sheets-*.json`,
   поле `client_email`) с правами **Editor**.
3. Прописать ID в `sales_dashboard/config.py` → `SHEET_ID = "..."`.

### 2. Установить зависимости

Локально для разработки:

```bash
cd belberry/bitrix24/sales_dashboard
pip install -e .
```

На VPS (где будет крутиться cron) — то же самое в venv:

```bash
cd /home/cloudbot/VibeCoding/belberry/bitrix24/sales_dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Проверить доступ

```bash
python -m sales_dashboard.cli check
```

Ожидаемый вывод:
```
== Bitrix ==
  OK: ID=2812 Лариса Помогатор
== Sheets ==
  OK: tabs = [...]
```

### 4. Первичная заливка

```bash
python -m sales_dashboard.cli etl --full
```

Создаст все вкладки и зальёт историю за `INITIAL_BACKFILL_DAYS` (90 дней для
сделок, 30 для звонков — звонки много, не имеет смысла грузить год).

### 5. Cron на VPS

```cron
# каждые 15 мин — ETL
*/15 * * * * /home/cloudbot/VibeCoding/belberry/bitrix24/sales_dashboard/scripts/cron_etl.sh >> /var/log/sales_dashboard.cron.log 2>&1

# каждые 15 мин со сдвигом 5 мин — синк прав
5,20,35,50 * * * * /home/cloudbot/VibeCoding/belberry/bitrix24/sales_dashboard/scripts/cron_user_sync.sh >> /var/log/sales_dashboard.user_sync.log 2>&1
```

В скрипте используется `flock` чтобы не запустить две копии одновременно.

### 6. Создать дашборд в Looker Studio

1. Зайти на https://lookerstudio.google.com под admin-аккаунтом.
2. New → Report → коннектор **Google Sheets** → выбрать ваш Sheet.
3. Добавить каждую вкладку как отдельный data source: `deals`, `calls`,
   `users`, `stages`, `categories`.
4. Построить страницы (см. план визуала выше). По мере роста — можно
   добавлять формульные поля в Looker Studio или формулы в самом Sheet
   (tab `daily_metrics`).
5. Скопировать `REPORT_ID` из URL отчёта Looker Studio
   (`https://lookerstudio.google.com/reporting/<REPORT_ID>/page/...`).
6. Прописать его в `state/user_sync_state.json` (создастся после первого
   `user-sync --dry-run`):

```json
{
  "looker_report_ids": ["YOUR_REPORT_ID"],
  "whitelist_emails": ["eshchemelev@gmail.com"]
}
```

`whitelist_emails` — те, кого скрипт **никогда не удалит**, даже если
этих людей нет в Bitrix. Положите туда свой админский gmail.

### 7. Запустить user-sync вручную (dry-run сначала)

```bash
python -m sales_dashboard.cli user-sync --dry-run
# проверить вывод, что разумные люди добавляются / удаляются
python -m sales_dashboard.cli user-sync
```

## Как это работает: контроль доступа (REVOKE-only)

**Важно:** скрипт НИКОГДА не выдаёт доступ автоматически. Доступ
выдаёте вы вручную через Share-кнопку в Sheet или Looker Studio.

- Источник правды о существующих доступах — текущие permissions на Sheet
  (и на Looker Studio отчёте, если ID указан в `looker_report_ids`).
- Скрипт периодически проверяет: для каждого reader, у кого нет owner-роли
  и кого нет в whitelist, ищет email в Bitrix `user.get`.
- Если email найден и `ACTIVE=N` (уволен) → **снимает доступ**.
- Если email найден и `ACTIVE=Y` → ничего не делает.
- Если email вообще не в Bitrix (партнёр / гость / ваш личный gmail) →
  ничего не делает. Внешних смотрящих не трогаем.
- Whitelist — emails, которые **никогда не трогаются**, даже если в
  Bitrix они деактивированы или отсутствуют (например, ваш админский
  gmail или сервисник).

### Когда вы хотите дать доступ новому сотруднику

1. Открыть Sheet (или Looker Studio отчёт) → кнопка Share
2. Добавить его email как Viewer
3. Готово. Скрипт его не тронет, пока он активен в Bitrix.

### Когда сотрудника увольняют

1. РОП деактивирует пользователя в Bitrix (`ACTIVE=N`).
2. В течение ≤15 минут `user-sync` снимает права на Sheet → данные не
   подгружаются → Looker Studio показывает «нет доступа».

### Партнёры и гости вне Bitrix

Если хотите дать доступ внешнему смотрящему (партнёр, аудитор), у
которого нет учётки в Bitrix — добавьте его в `whitelist_emails` в
`state/user_sync_state.json`, чтобы скрипт его точно не тронул, даже
случайно. Без whitelist скрипт его всё равно не тронет (Bitrix о нём не
знает = не трогаем), но whitelist это страховка от будущих изменений
логики.

## Поля и метрики

### Tab `deals`
Колонки см. в `extractors/deals.py:HEADER`. Главное:
- `stage_semantic`: `P` (в работе), `S` (выиграна), `F` (проиграна) — даёт
  чистый фильтр в Looker Studio без хардкода stage_id.
- `is_won`, `is_lost`: `Y/N` precomputed → удобно для счётчиков.

### Tab `calls`
- `call_type_label`: `outgoing` / `incoming` / `missed` / `incoming_redirect`.
- `date` и `hour` (MSK) предвычислены → heatmap «дни × часы» строится
  без формул в Looker Studio.
- `talk_duration` пока равно `call_duration` (Bitrix через
  `voximplant.statistic.get` не отдаёт отдельно talk-time; для точного —
  нужен `telephony.externalcall.*` или парсинг через `crm.activity`).

### Tab `users`
- `email` — нижний регистр, единственный — используется как identity.
- `active=N` означает уволенного.
- `department_ids` — для будущего разделения дашборда по отделам.

### Tab `stages`
`stage_id` = то же, что `STAGE_ID` в `crm.deal.list`. Join по
`deals.stage_id = stages.stage_id` даёт человеческое название стадии и
её семантику.

## Что не сделано (намеренно)

- **Daily aggregations** (`daily_metrics`, `manager_kpi`) — оставлены под
  формулы в самом Sheet (так быстрее итерируется, не надо передеплоивать
  Python). Если данные перерастут Sheets — заменяем на pre-aggregation
  в ETL.
- **Webhook ONUSERUPDATE** для моментальной деактивации — не делал, лаг
  15 минут приемлем для MVP.
- **RLS (менеджер видит только своё)** — отключено по решению с самого
  начала. Все видят всё.
- **Алерты** («менеджер не звонит 2 часа») — нет, Looker Studio это не
  умеет. Если нужно — добавим отдельный мелкий Python-сервис, шлющий в
  Telegram.

## Тесты

```bash
cd belberry/bitrix24/sales_dashboard
python -m pytest tests/ -q
```

## Логи и отладка

- API-вызовы Bitrix: `logs/sales_dashboard.csv`
- Cron stdout: `/var/log/sales_dashboard.cron.log`, `*.user_sync.log`
- Sheet `sync_log`: история запусков ETL с rows/inserted/updated/errors
- `state/etl_state.json`: timestamps last_run для инкремента
- `state/user_sync_state.json`: managed emails + whitelist + Looker IDs

## Roadmap

- [ ] Поднять на VPS, повесить cron, дождаться первого `--full`
- [ ] Собрать первый Looker Studio отчёт по 3 страницам
- [ ] Прописать `looker_report_ids` в user_sync_state
- [ ] Добавить test-suite на user_sync mock
- [ ] (Опционально) Smart-process данные тоже тащить — если в [28] Проекты
      есть SP-привязанные сущности
