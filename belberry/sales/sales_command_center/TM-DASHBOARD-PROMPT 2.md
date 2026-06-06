# Промт для новой ветки: дашборд по ТЕЛЕМАРКЕТИНГУ (Командный центр продаж, Belberry)

Ты строишь **отдельный дашборд по телемаркетингу (ТМ)** в веб-приложении «Командный центр продаж» Belberry.
Живой адрес приложения: https://static.163.222.104.178.clients.your-server.de/

## Что за проект
Веб-приложение для отдела продаж Belberry. Python-раннер каждое утро собирает данные из Bitrix24
(сделки, телефония Voximplant, встречи с LLM-разбором, брифы, КП) → пишет в **PostgreSQL** →
**Next.js** читает и показывает. Страницы: `/dashboard` (дашборд отдела), `/today` (live «Сегодня»),
`/daily` (отчёт дня), `/meetings` (анализ встреч), `/alerts`. Пользователи — руководитель (Щемелёв),
РОП, менеджеры. Время везде — **Europe/Moscow**.

Твоя задача — **новая страница `/telemarketing`** (или как договоришься): дашборд работы ТМ-отдела
(звонари/обзвон), по образцу существующих дашбордов.

## Расположение кода
- Worktree (mac): `/Users/pro2kuror/Desktop/VibeCoding`, модуль `belberry/sales/sales_command_center/`.
  - `runner/` — Python-ядро (сбор/анализ/запись в Postgres). venv: `runner/.venv/bin/python` (py3.12).
  - `web/` — Next.js 15 (App Router) + Drizzle ORM + postgres.js + iron-session.
  - `db/migrations/` — SQL-миграции (psql-канон, см. ниже).
- Стек web: Next.js 15 + React 19 + Drizzle 0.45 + postgres.js + iron-session + Tailwind v3.
  Компоненты дашборда — серверный page + клиентские компоненты с inline-стилями (классы `bb-*`).

## ПРОД-ДОСТУПЫ (Hetzner — единственный прод)
- SSH: `ssh -i ~/.ssh/temp_migration_key root@178.104.222.163`
- Репозиторий на проде: `/opt/scc/VibeCoding` (тот же git).
- Секреты/env: `/etc/scc/scc.env` (DATABASE_URL, LLM-ключ, BITRIX_STATE_PATH, Telegram). **Не печатать в чат.**
- БД: `set -a; . /etc/scc/scc.env; set +a; psql "$DATABASE_URL"`
- Web: PM2-процесс **`scc-web`**, порт **3010**, за nginx+TLS. Деплой: `git pull → npm run build → pm2 reload scc-web`.
- Runner venv на проде: `/opt/scc/VibeCoding/belberry/sales/sales_command_center/runner/.venv/bin/python`.
- Bitrix: read-only токен синкается с TimeWeb (на маке обновить: `bash /Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh`).
  Вызовы — через `runner/src/bx_client.py` → `bx.call(method, params)` (возвращает dict с `result`/`next`).
- Авторизация web: passwordless (email активного сотрудника Bitrix → код от Ларисы). **За auth страницу не видно**
  (curl даёт 307 → /login). Ревью: `curl -sk -o /dev/null -w "%{http_code}"`, дамп через `psql`, либо скрин от пользователя.

## ВЕТКА И ДЕПЛОЙ (важно!)
- **Каноническая ветка проекта сейчас — `feat/dashboard-v2`** (на ней живут все дашборды, страница встреч,
  раннер; прод выкачен именно на неё, HEAD ~`5a3b32c`). НЕ `main`, НЕ `feat/global-sales-dashboard`.
- Заводи свою ветку **от `feat/dashboard-v2`** (напр. `feat/tm-dashboard`) и **в ОТДЕЛЬНОМ git worktree**
  (урок проекта: не работай в общей рабочей папке — параллельные агенты ловят коллизии коммитов).
  Пример: `git worktree add /Users/pro2kuror/Desktop/VibeCoding-tm feat/tm-dashboard` (от dashboard-v2).
  В новом worktree симлинкни зависимости: `web/node_modules` и `runner/.venv` из основной папки (они в .gitignore).
- Коммиты: Conventional Commits, по-русски, trailer `Co-Authored-By: Claude ...`.
- **Деплой (web катит Claude по SSH сам):** на проде `git fetch && git reset --hard origin/<ветка> && npm run build && pm2 reload scc-web`.
  На проде одновременно ОДНА ветка — координируйся: сейчас там `feat/dashboard-v2`. Чтобы выкатить свою —
  либо смержи в dashboard-v2, либо переключи прод на свою ветку (тогда учти: на ней же раннер — не сломай).
- **Миграции БД**: новый файл `db/migrations/000N_*.sql`, применяется вручную `psql "$DATABASE_URL" -f ...`.
  Это прод-запись — спрашивай разрешение пользователя. (NB: уникальный индекс по NULL не работает в Postgres —
  у `plans` общие планы с `manager_id IS NULL` могут дублироваться, чисти явным DELETE.)
- **Не пушить с красными тестами.** Перед деплоем гонять (см. ниже).

## КОМАНДЫ (тесты/сборка)
- Runner (из `runner/`): `​.venv/bin/python -m pytest -q` (есть фикстуры, локального Postgres нет).
- Web (из `web/`): `npx tsc --noEmit` · `npx vitest run src/lib/__tests__/<...>.test.ts` · `npx next lint` · `npm run build`.
  ⚠️ vitest в изолированном worktree через симлинк node_modules цепляет лишние тесты — гоняй `--root src` или конкретный файл.

## МОДЕЛЬ ДАННЫХ (Postgres, что уже есть)
Схема Drizzle: `web/src/db/schema.ts`. Раннер пишет, web читает. Ключевые таблицы:
- **`manager_activity`** (per manager per day) — ГЛАВНОЕ для ТМ: `calls_total`, `calls_answered`,
  `calls_60s_plus`, `calls_120s_plus`, `dials_total` (наборы), `talk_seconds`, `meetings_set` (встреч НАЗНАЧЕНО,
  атрибутируется СОЗДАТЕЛЮ=ТМ), `meetings_held`, `briefs_created`, `kp_sent`, `emails_sent`,
  `messenger_dialogs`, `deals_created_count`/`deals_cold_count`/`deals_incoming_count`/`deals_won_count`/`deals_won_amount`.
- **`deals_snapshot`** (per deal per day) — снимок открытых сделок: `stage`, `opportunity`, `manager_id`,
  `category_id` (10=Продажи, 50=ТМ), `stuck_days`, `stage_entered`, `title`, `company_id`.
- **`meetings`**, **`kp_briefs`**, **`plans`** (period/manager_id/metric/target), **`reports`** (html+summary дня),
  `live_snapshot`/`live_chats` (для /today).
- **`users`** (bitrix_id, name, dept, role) — справочник; `dept` = должность из Bitrix.

## ТЕЛЕМАРКЕТИНГ — доменные знания (главное!)
- **ТМ-воронка = `CATEGORY_ID=50`** в Bitrix. Стадии (`crm.dealcategory.stage.list` id=50):
  - `C50:UC_1S1KIU` База · `C50:NEW` К обзвону · `C50:PREPARATION` Взято в работу ·
    `C50:UC_WZ4KQE` Встреча назначена · `C50:WON` УСПЕХ · `C50:LOSE` ОТЛОЖЕНО · `C50:APOLOGY` ОТВАЛ.
  - Воронка Продажи — `CATEGORY_ID=10` (отдельный дашборд `/dashboard`).
- **ТМ-сотрудники (звонари)** определяются по должности: `isTelemarketing(dept)` = dept содержит «телемаркет».
  Уже в БД: Вострецов Аркадий (id 2832), Исаева Дарья (id 2772), dept «Телемаркетолог». Справочник может быть
  неполным — бери scope по `isTelemarketing`, не хардкодь имена.
- **Дозвон = разговор ≥60 секунд** (`calls_60s_plus`), а не «снял трубку». Это канон проекта. Есть и `calls_120s_plus`.
- **Встреча «назначено» засчитывается СОЗДАТЕЛЮ** (телемаркетологу) — поле `meetings_set` уже по создателю.
  Проведённая встреча — ответственному (продавцу). ТМ метрика = назначенные.
- **Связь ТМ → Продажи**: ТМ обзванивает (cat50), при успехе сделка ПЕРЕВОДИТСЯ в воронку Продажи (cat10).
  В дашборде `/dashboard` есть метрика «сделки из холода» = переведённые из ТМ (определяется по входу в `C10:NEW`
  истории стадий, где сделка создана раньше — см. `transform.build_db_rows` `deals_cold_count`).
- **Телефония** собирается из **Voximplant** (`collect_voximplant` в `runner/src/collect.py`): per звонок
  `PORTAL_USER_ID`, `CALL_DURATION`. Агрегация в `transform.aggregate_calls` (наборы/дозвоны 60с/120с/talk_seconds).
- **План ТМ** (в таблице `plans`, period `YYYY-MM`): `meetings`=20 (назначенных встреч на 1 ТМ). Из старой
  «декомпозиции» ОП также: ~100–120 наборов/день, ~25 звонков 120с+/день, конверсия наборов во встречу ~3.5–4.2%.
- **SOURCE_ID=12** = Телемаркетинг (источник сделок ТМ). СПАМ-сделки `UF_CRM_1771495464=8588` исключать.

## ЧТО МОЖЕТ ПОКАЗЫВАТЬ ТМ-ДАШБОРД (scope — уточни у пользователя квизом)
На имеющихся данных (`manager_activity` + `deals_snapshot` cat50 + Voximplant):
- **Звонки/обзвон**: наборы всего, дозвоны 60с+/120с+, часы разговоров; всего, **на 1 звонаря**, **в день**, **в час**.
- **По звонарям** (таблица): наборы, дозвоны, встреч назначено, **конверсия наборов→встречу** (meetings_set/dials).
- **ТМ-воронка (cat50 snapshot)**: База / К обзвону / Взято в работу / Встреча назначена / Успех / Отвал + Δ за месяц.
- **Назначенные встречи**: сколько назначено, конверсия в проведённые, переданные сделки в Продажи (холод).
- **План/факт ТМ**: встречи 20/ТМ, наборы/день, звонки 120с+/день — факт vs план.
- **Помесячная динамика + Day2Day** по ТМ.
- **Outreach** (email-касания) — отдельный канал, частично `emails_sent`.
- (опц., нужны ручные константы) **Юнит-экономика ТМ**: ФОТ ТМ, себестоимость встречи/сделки из холода, % от чека.

## КОД ДЛЯ ПЕРЕИСПОЛЬЗОВАНИЯ
- `web/src/lib/dashboard.ts`: уже есть `buildTmActivity(members, workingDays)` (звонки на звонаря/в день),
  `isSalesDept`/`isTelemarketing`, `STAGE_META` (cat10). Паттерн: чистая функция под vitest + серверная загрузка
  + клиентский компонент с inline-стилями. Блок «Активность ТМ · звонки» на `/dashboard` — образец.
- `web/src/lib/meetings.ts` + `meetings-shared.ts` — образец «server-only загрузка / shared чистые функции для клиента»
  (важно: клиентский компонент НЕ должен импортировать `server-only` модуль — выноси типы/функции в `*-shared.ts`).
- `web/src/components/Sidebar.tsx` — добавить пункт меню (NAV).
- Runner: `collect.py` (Voximplant, сделки cat50), `transform.py` (aggregate_calls, deal_origin/cold).
- Деплой/наблюдение: образцы SSH-команд в `DASHBOARD-REWORK-PROMPT.md` (там же история фиксов).

## ПРАВИЛА ПРОЕКТА (соблюдать везде)
- Язык: **русский**, **без англицизмов** в UI (дозвон не «коннект», воронка не «пайплайн», сделка не «дил»).
- Время — **Europe/Moscow**. Даты — через datetime/Intl с timeZone, не угадывать день недели.
- **Дозвон = ≥60с**. **Встреча назначено = создателю (ТМ)**. **Scope ТМ** = `isTelemarketing(dept)`.
- СПАМ `UF_CRM_1771495464=8588` исключать. Имена сотрудников «Фамилия Имя», не id.
- Drizzle: `timestamptz` без `mode:'date'` может прийти строкой — нормализуй к Date.

## ЧЕГО НЕ ТРОГАТЬ (идёт параллельно)
- Страница **`/meetings`** (анализ встреч) и LLM-разбор: `runner/src/analyze_llm.py`, `reanalyze.py`,
  `web/src/lib/meetings*.ts`, `components/meetings/`. Не редактируй.
- Блоки дашборда `/dashboard` (воронка вход→оплата, прогноз, качество встреч, по менеджерам, динамика, план/факт)
  и их код в `lib/dashboard.ts` — кроме общих хелперов (`isTelemarketing`, `buildTmActivity`), которые можешь переиспользовать.
- Фича «задачи из встреч» (`runner/src/tasks.py`, `meeting_tasks`, блок в `/alerts`) — чужая.

## ВАЖНЫЕ ГРАБЛИ (из истории проекта)
- **Backfill истории**: раннер обрабатывает только рабочие дни; снимок воронки за прошлое НЕ восстановим
  (Bitrix хранит только текущие открытые) — backfill пишет только потоковые таблицы. Транскрибация встреч
  появилась с апреля 2026 (первая 13.03) — раньше LLM-разбор невозможен.
- **Отменённые встречи** (`DT1048_24:FAIL` в SP 1048) не считаются проведёнными — фильтр по `stageId=DT1048_24:SUCCESS`.
- **Метрика «Сделки» (Продажи)** = вошедшие в `C10:NEW` по истории стадий (дата-точно), НЕ по текущему CATEGORY_ID.
- При смене логики метрик нужен ре-backfill с delete-per-day (иначе остаются строки выпавших менеджеров).

## ЗАДАЧА
Начни с чтения `lib/dashboard.ts` (блок ТМ-активности как образец), `schema.ts`, `Sidebar.tsx`, и стадий cat50.
Затем уточни у пользователя scope ТМ-дашборда **квизом** (готовые опции, не текстом): какие блоки в первую очередь,
нужна ли ТМ-воронка cat50, юнит-экономика (ручные ФОТ-константы), план/факт по каким метрикам.

Память Claude (если доступна): `project-belberry-global-sales-dashboard`, `feedback-sales-dozvon-and-meeting-attribution`
(дозвон 60с + встреча по создателю), `feedback-sales-dashboard-employee-scope` (только ОП+ТМ), `reference-belberry-bp-company`,
`project-belberry-sales-plan-may-2026` (планы ТМ: 35 встреч, 100 наборов/день, 25 звонков 120с+).
