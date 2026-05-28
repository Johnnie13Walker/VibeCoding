# Сборка дашборда в Looker Studio — пошагово

Цель: за ~25 минут собрать рабочий онлайн-дашборд из 3 страниц
(Продажи / Телемаркетинг / KPI менеджеров).

---

## Шаг 0. Открыть Looker Studio и подключить 5 таблиц

Linking API Looker Studio работает только с шаблонами, поэтому
"create-from-URL" не сработает. Подключаем источники вручную (1.5 минуты).

1. Открыть https://lookerstudio.google.com под `eshchemelev@gmail.com`
2. Большая кнопка **Blank Report** (Создать → Отчёт)
3. В диалоге "Add data to report":
   - Google Sheets → найти `Belberry Sales Dashboard — raw data`
     (или ввести ID `1W11eS3q4ft_iCMECqpQZ4x_81GAeoBKE1Fx9EtXf3f8`)
   - Worksheet: **deals** → "Use first row as headers" ON → Add
4. Сверху-справа `Add data` → повторить для каждой вкладки:
   - **calls**
   - **users**
   - **stages**
   - **categories**
5. Переименовать (опционально): Resource → Manage data sources → клик на имя:
   - `deals` → **Сделки**
   - `calls` → **Звонки**
   - `users` → **Менеджеры**
   - `stages` → **Стадии**
   - `categories` → **Воронки**

После этого должно быть 5 data sources в правой панели.

---

## Шаг 1. Сохранить и переименовать отчёт

1. В верхнем левом углу нажать на `Untitled Report` → ввести: **Belberry — Продажи и Телемаркетинг**
2. File → Make a copy *не нужно*, отчёт уже сохраняется автоматически
3. Заметьте URL вида `https://lookerstudio.google.com/reporting/<REPORT_ID>/page/...`
   — `<REPORT_ID>` нужен будет потом для user-sync

---

## Шаг 2. Проверить типы полей (1 минута)

В правой панели → раздел `Resource` → `Manage added data sources` → по каждому
источнику нажать `Edit` и убедиться:

**Сделки:**
- `opportunity` — Number (если строка — поменять)
- `date_create`, `date_modify`, `closedate` — Date Hour (или Date)
- `category_id`, `assigned_by_id` — Text (иначе будет суммироваться как число)

**Звонки:**
- `call_duration`, `talk_duration` — Number
- `date` — Date
- `hour` — Number
- `portal_user_id` — Text

Если Looker Studio неправильно определил тип — кликнуть на тип и выбрать
правильный. После любого изменения → **Done** в правом верхнем углу.

---

## Страница 1: «Продажи»

Переименуйте текущую страницу: в левом сайдбаре → правой клик на странице →
Rename → **Продажи**.

### Widget 1: Фильтр по периоду (Date range control)

- Toolbar: `Add a control` → `Date range control`
- Перетащить в верх страницы
- В настройках справа:
  - Default date range → Custom → Last 30 days

### Widget 2: Scorecard «Открытых сделок»

- `Add a chart` → `Scorecard`
- Data source: **Сделки**
- Metric: `Record Count` (или drag `deal_id` → Count)
- Filter (нажать `Add a filter` → Create a filter):
  - Name: `Открытые`
  - Include: `is_closed` Equals (=) `N`
- Style → Comparison → Previous period (необязательно)

### Widget 3: Scorecard «Выиграно сделок» (за период)

- Скопировать предыдущий scorecard
- Поменять фильтр: `is_won` Equals `Y`
- Заголовок: «Выиграно»

### Widget 4: Scorecard «Сумма выигранных, ₽»

- Scorecard
- Data: Сделки
- Metric: `opportunity` → Aggregation **Sum**
- Filter: `is_won` = `Y`
- Заголовок: «Сумма выигранных»

### Widget 5: Funnel-bar «Сделки по стадиям»

- Add chart → **Bar chart** (Horizontal)
- Data: Сделки
- Dimension: `stage_name`
- Metric: `Record Count`
- Sort: Record Count → DESC
- Filter: `is_closed` = `N` (показать только сделки в работе)
- Style → Bar — Show data labels → ON

### Widget 6: Таблица «По воронкам»

- Add chart → **Table with bars**
- Data: Сделки
- Dimension: `category_name`
- Metrics:
  - Record Count (rename: Кол-во)
  - `opportunity` Sum (rename: Сумма)
  - `opportunity` Average (rename: Средний чек)
- Sort: Кол-во → DESC

### Widget 7: Time-series «Создание сделок по дням»

- Add chart → **Time series**
- Data: Сделки
- Dimension (date): `date_create`
- Metric: `Record Count`
- Breakdown dimension (опционально): `category_name`

---

## Страница 2: «Телемаркетинг»

В сайдбаре → Add page → переименовать в **Телемаркетинг**.
Скопируйте Date range control с первой страницы (правый клик → Make report-level → доступен на всех).

### Widget 1: Scorecard «Звонков всего»

- Data: Звонки
- Metric: Record Count

### Widget 2: Scorecard «Дозвонов»

- Data: Звонки
- Metric: Record Count
- Filter: `is_answered` = `Y`

### Widget 3: Scorecard «Talk time, часов»

- Data: Звонки
- Metric: `call_duration` Sum
- Style → Comparison metric → дополнительно поделить на 3600
  (или просто переименовать единицу — Looker не умеет автоматом)
- *Альтернатива:* в data source `Звонки` → Add field:
  - Name: `talk_hours`
  - Formula: `call_duration / 3600`
  - Type: Number
  Потом использовать `talk_hours` как metric с Sum

### Widget 4: Time series «Звонки по дням»

- Time series
- Data: Звонки
- Dimension: `date`
- Metric: Record Count
- Breakdown: `call_type_label`

### Widget 5: Pivot table «Heatmap день × час»

- Add chart → **Pivot table** (с heatmap-стилем)
- Data: Звонки
- Row dimension: `date`
- Column dimension: `hour`
- Metric: Record Count
- Style → Heatmap → ON, Color: gradient

### Widget 6: Pie «Распределение по типам»

- Pie chart
- Data: Звонки
- Dimension: `call_type_label`
- Metric: Record Count

### Widget 7: Bar «Топ менеджеров по звонкам»

- Bar chart (Horizontal)
- Data: Звонки
- Dimension: `manager`
- Metric: Record Count
- Sort: Record Count → DESC
- Limit: 15
- Filter: `manager` is not empty (иначе будут «пустые»)

---

## Страница 3: «KPI менеджеров»

Add page → **KPI менеджеров**.

### Widget 1: Таблица «Звонки по менеджерам»

- Table with bars
- Data: Звонки
- Dimension: `manager`
- Metrics:
  - Record Count → Звонков
  - `is_answered` Count → нет, надо иначе:
  - Add field в data source: `answered_flag` = `IF(is_answered="Y",1,0)`, type Number
  - Метрика: `answered_flag` Sum → Дозвонов
  - `call_duration` Sum → Talk time, сек
- Sort: Звонков → DESC

### Widget 2: Таблица «Сделки по менеджерам»

- Table with bars
- Data: Сделки
- Dimension: `manager`
- Metrics:
  - Record Count → Сделок всего
  - `is_won` → не считается сразу, делаем calculated field:
  - В data source `Сделки` → Add field: `won_flag` = `IF(is_won="Y",1,0)`, Number
  - `won_flag` Sum → Выигранных
  - `opportunity` Sum → Сумма (с фильтром is_won=Y? см. ниже)
- Sort: Выигранных → DESC

Для **Сумма выигранных** нужно отдельное поле:
- Add field: `won_amount` = `IF(is_won="Y", opportunity, 0)`, Number
- Метрика: `won_amount` Sum

### Widget 3: Scorecard «Конверсия в выигранные»

- Scorecard
- Data: Сделки
- Metric:
  - Add field: `won_rate` = `SUM(won_flag) / COUNT(deal_id)`, Type Percent
  - Метрика: `won_rate` (без aggregation, поле уже агрегирующее)
- Comparison: Previous period

### Widget 4: Bar «Лидерборд по выручке»

- Bar chart
- Data: Сделки
- Dimension: `manager`
- Metric: `won_amount` Sum
- Sort: DESC, Limit 10
- Filter: `manager` is not empty

---

## Шаг N. После сборки

1. **Сохранить и расшарить:**
   - Кнопка Share вверху справа
   - Add people → вписать email того, кому нужен доступ → Viewer
   - **Только тех, кому реально надо.** Скрипт user-sync ничего не выдаёт сам — снимет только тех, кого уволят в Bitrix.

2. **Поделиться REPORT_ID:**
   - Из URL отчёта вида `https://lookerstudio.google.com/reporting/<id>/page/0`
   - Прислать мне `<id>` → я пропишу в `state/user_sync_state.json:looker_report_ids`
   - После этого user-sync будет revoke'ить доступ и к самому отчёту тоже (а не только к Sheet)

3. **Расписание обновлений:**
   - Refresh Looker Studio data: Resource → Manage data sources → каждый → Edit → Data freshness → 15 minutes
   - Иначе он кэширует на 12 часов и не показывает свежие данные ETL

---

## Если что-то пошло не так

- **Поля показываются как Text вместо Number/Date** → Resource → Edit data source → кликнуть на тип, поменять.
- **Графики пустые** → проверить, что date range control стоит на «Last 30 days» (а не «Yesterday»).
- **Дубликаты в табличке** → добавить filter `manager IS NOT NULL`.
- **«Permission denied»** при добавлении data source → значит сервисник не имеет доступа к Sheet. Проверить Share → должен быть `finance-director-sheets-bot@...` как Editor.

---

## Что дальше (после MVP)

- Добавить страницу «Конверсии» с воронкой стадия → стадия (Sankey диаграмма из community connectors).
- Добавить срез по UTM-источникам для маркетинга.
- Если данных станет больше 50К строк — переехать на BigQuery (Sheet → BigQuery free tier).
- Алерты («менеджер не делал звонков с утра») — отдельным мини-сервисом, шлющим в Telegram. Looker Studio такого не умеет.
