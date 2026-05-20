# Belberry WD Calculator v2

Калькулятор веб-разработки Belberry — генерирует структурированный Google Sheet
с гибким конструктором, авто-сметой и готовым телом КП для копи-пасты в
карточку КП Битрикс24.

## Что внутри

| Файл | Назначение |
|---|---|
| [build_calculator.py](build_calculator.py) | Билдер — заливает структуру в Google Sheet |
| [rates.py](rates.py) | Single source of truth для ставок и нормативов |

## Структура итогового Sheet (6 листов)

| # | Лист | Что |
|---|---|---|
| 01 | Старт | ID сделки, ЛПР, бюджет, дедлайн, сфера |
| 02 | Конструктор | Платформа × Тип × Страницы × Интеграции × SEO × Контент |
| 03 | Ставки | Single source of truth: все ставки, лицензии, скидки, НДС |
| 04 | Смета | Авто-расчёт по этапам + светофор бюджета (зелёный/жёлтый/красный) |
| 05 | Текст КП | Markdown для копи-пасты в карточку КП Битрикс24 |
| 06 | Чек-лист 8 pillars | Обязательные галочки до отправки клиенту |

## Почему новый калькулятор

В сравнении со старым WD-Калькулятором (Google Sheet `1AZ6I8Lz6Ppu5y2OLSG7Tw0p8X0pC3N1Fq3Yk8TG4RoY`):

| Старый | Новый |
|---|---|
| 3 фиксированных пакета (Strapi / Битрикс / Индивидуал) | Гибкий конструктор: 5 платформ × 6 типов × произвольный набор страниц/интеграций |
| Считает 3 варианта параллельно | Один точный расчёт под выбранную конфигурацию |
| Нет генератора КП | Лист «05 Текст КП» с готовым Markdown для карточки КП Битрикс24 (закрывает Pillar 1, 5) |
| Нет чек-листа | Лист «06 Чек-лист» — 8 обязательных пунктов из инсайтов (Pillar 1-8) |
| Нет привязки к сделке | Поле «ID сделки в Битрикс24» + авто-ссылка на карточку |
| Этапы скрыты в часах | Явные 10 этапов: Discovery / Прототип / Дизайн / Бэк / Фронт / QA / Launch / Страницы / Интеграции / SEO |

## Как запустить (3 шага)

### Шаг 1. Создай пустой Sheet

В Google Drive: «Создать» → «Google Таблицы» → дай имя
например **«WD-Калькулятор Belberry v2»**.

Скопируй ID из URL (между `/d/` и `/edit`):
```
https://docs.google.com/spreadsheets/d/1AaBbCc...XxYyZz/edit
                                       └────────┬────────┘
                                              ID
```

### Шаг 2. Расшарь Sheet с service-account

В новом Sheet нажми «Поделиться» и добавь как **редактор**:

```
finance-director-sheets@finance-director-sheets.iam.gserviceaccount.com
```

(Service account нашего проекта. Ключ лежит в `~/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json`.)

### Шаг 3. Запусти builder

```bash
cd /Users/pro2kuror/Desktop/VibeCoding/belberry/web_calculator

# Используем venv с установленным google-api-python-client
PYTHON=/Users/pro2kuror/Desktop/VibeCoding/belberry/bitrix24/.worktrees/Обогащение*/belberry/bitrix24/crm_company_enrich/.venv/bin/python

# Сначала проверь доступ
$PYTHON build_calculator.py --spreadsheet-id <ID> --check-only

# Если ОК — заливай
$PYTHON build_calculator.py --spreadsheet-id <ID>
```

После запуска все 6 листов будут заполнены, валидации (dropdown'ы и
чекбоксы) расставлены, формулы протянуты.

## Опции CLI

```
--spreadsheet-id <ID>     ID целевого Sheet (обязательно)
--key <path>              путь к service-account JSON
                          (по умолчанию ~/.config/vibecoding/assistant/secrets/...)
--dry-run                 вывести структуру в stdout без записи
--check-only              только проверить доступ к Sheet
--keep-existing-tabs      не удалять существующие листы
```

## Как менять ставки

Все цены — в [rates.py](rates.py):

- `HourlyRates` — часовые ставки (база, премиум-дизайн, техлид, PM)
- `PLATFORMS` — лицензии и часы по каждой платформе
- `PAGE_TYPES` — часы на тип страницы
- `INTEGRATIONS` — часы на каждую интеграцию + дефолтные галки
- `SEO_LEVELS` — уровни SEO
- `ContentRates` — цены текстов
- `Discounts` — скидки и НДС
- `BudgetRules` — допустимое превышение, срок действия КП
- `Buffer` — буферы на правки и риски

После изменения — перезапусти `build_calculator.py` с тем же `--spreadsheet-id`.
Builder сначала очищает листы и заливает заново, формулы и связи восстанавливаются.

## Что калькулятор НЕ делает

- Не создаёт карточку КП в Битрикс24 (только генерирует Markdown для копи-пасты)
- Не подтягивает данные сделки из Битрикс24 (поля заполняются вручную)
- Не отправляет КП клиенту
- Не отслеживает срок «КП лежит без отправки» (это задача роботов в Битриксе)

Эти автоматизации — отдельный план («контур карточек КП» из
`[[09-Projects/belberry-deal-analysis/STATUS]]`), не привязан к этому
калькулятору.

## Связанное

- [[09-Projects/belberry-deal-analysis/insights/8-pillars-of-kp-failure]] — обоснование структуры калькулятора
- [[09-Projects/belberry-deal-analysis/STATUS]] — статус проекта
- Старый калькулятор: <https://docs.google.com/spreadsheets/d/1AZ6I8Lz6Ppu5y2OLSG7Tw0p8X0pC3N1Fq3Yk8TG4RoY/>
