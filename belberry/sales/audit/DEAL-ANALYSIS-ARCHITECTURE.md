# Архитектура автоматизированного разбора сделок Битрикс24

> Передаточный документ для Claude Code коллеги. Описывает реально работающий
> пайплайн Belberry (mpya.ru, sinai-clinic.ru, mitekpumps.ru, geots.ru —
> 5 готовых .docx).
>
> **Честное предупреждение перед чтением.** Это не webhook-driven system.
> Это **Claude Code как агент-разборщик** + Python-инструменты + Whisper + pandoc.
> Триггер — пользователь говорит «разбери сделку 18538». Claude сам выполняет
> 4 шага из PLAYBOOK. LLM-«анализатор» = Claude в Claude Code, отдельной
> AI-API-обвязки нет. Это сделано осознанно — см. раздел 7.

---

## 1. ОБЗОР ПАЙПЛАЙНА

### 1.1 Триггер

**Только ручной.** Webhook'а нет, крона нет.

Входы:
- ID сделки (`18538`)
- URL сделки (`https://<portal>.bitrix24.ru/crm/deal/details/18538/`)
- URL карточки смарт-процесса (бриф/КП — тогда поднимается `parentId2` → сделка)
- Связка «менеджер + клиент» — тогда сначала поиск через `crm.deal.list`

### 1.2 Шаги от события до документа

```
0. Пользователь → Claude Code: «разбери сделку 18538»
   ↓
1. СБОР ДАННЫХ (≈ 30 мин)
   bitrix-sync-state.sh → обновить OAuth
   crm.deal.get → карточка
   crm.item.list (entityTypeId=1048/1056/1106, filter parentId2) → встречи/брифы/КП
   crm.activity.list (filter OWNER_TYPE_ID=2, OWNER_ID=<deal_id>, TYPE_ID=2) → звонки
   crm.timeline.comment.list → переписка (WhatsApp/Telegram через Wazzup)
   crm.activity.list (без TYPE_ID) → задачи/события
   → /tmp/<name>_deal.json + /tmp/<name>_calls.json
   ↓
2. СКАЧИВАНИЕ MP3 (≈ 5 мин)
   crm.activity.get → FILES[0].url → GET → mp3 в /tmp/<name>_calls/
   ↓
3. ТРАНСКРИПЦИЯ (≈ 1.5× длительности аудио)
   faster-whisper medium, language=ru, vad_filter=True
   → /tmp/<name>_transcripts/*.txt с таймкодами
   ↓
4. АНАЛИЗ (Claude как LLM, ≈ 1.5 часа)
   Контекст: deal.json + transcripts/*.txt + PLAYBOOK + insights/
   → Markdown по шаблону deal-review-template
   ↓
5. ГЕНЕРАЦИЯ DOCX (≈ 1 мин)
   pandoc <name>_review.md → ~/Desktop/Разбор_сделки_<name>.docx
   ↓
6. ОБРАТНАЯ ЗАГРУЗКА В CRM (обязательно)
   base64-encode docx → crm.deal.update fields[UF_CRM_DEAL_AUDIT]
   crm.timeline.comment.add → summary с главным диагнозом
```

### 1.3 Вход / выход

| Что | Тип |
|---|---|
| **Вход** | `deal_id: int` (опц. URL/смарт-процесс/менеджер→поиск) |
| **Выход 1** | `~/Desktop/Разбор_сделки_<name>.docx` (18–25 стр) |
| **Выход 2** | `.docx` прикреплён к UF-полю `UF_CRM_DEAL_AUDIT` в карточке |
| **Выход 3** | Summary-комментарий в timeline сделки |
| **Артефакт памяти** | `cases/<name>.md` в Obsidian-vault (паттерны, цитаты) |

**Среднее время на одну сделку:** ~3 часа Claude + 30 минут машинных (Whisper).

---

## 2. ИСТОЧНИКИ ДАННЫХ ИЗ БИТРИКС24

### 2.1 Сущности и методы

| Сущность | Метод REST | Параметры | Что даёт |
|---|---|---|---|
| Сделка | `crm.deal.get` | `id=<deal_id>` | сумма, стадия, причина отвала (UF), даты, ответственный, COMPANY_ID, CONTACT_ID |
| Контакт | `crm.contact.get` | `id=<contact_id>` | ФИО, телефон, email, должность |
| Компания | `crm.company.get` | `id=<company_id>` | ИНН, оборот, отрасль, город, сайт |
| Брифы | `crm.item.list` | `entityTypeId=1056, filter[parentId2]=<deal_id>` | сколько брифов, на каких этапах |
| Встречи | `crm.item.list` | `entityTypeId=1048, filter[parentId2]=<deal_id>` | факт проведения, длительность |
| **КП** | `crm.item.list` | `entityTypeId=1106, filter[parentId2]=<deal_id>` | **самое важное** — заведена ли карточка КП |
| Детали смарт-процесса | `crm.item.get` | `entityTypeId=<id>, id=<item_id>` | полные поля |
| Звонки | `crm.activity.list` | `filter[OWNER_TYPE_ID]=2, filter[OWNER_ID]=<deal_id>, filter[TYPE_ID]=2` | длительность, направление, FILES[0].url для mp3 |
| Все активности | `crm.activity.list` | `filter[OWNER_TYPE_ID]=2, filter[OWNER_ID]=<deal_id>` | задачи/события |
| Детали активности | `crm.activity.get` | `id=<activity_id>` | FILES (mp3 url), SETTINGS, RESULT |
| Переписка/комменты | `crm.timeline.comment.list` | `filter[ENTITY_ID]=<deal_id>, filter[ENTITY_TYPE]=deal` | заметки + сообщения из Wazzup |
| Пользователи (менеджеры) | `user.get` | `ID=<user_id>` | ФИО менеджера для подписей в .docx |
| Список UF полей | `crm.deal.userfield.list` | — | расшифровка enum-значений |

### 2.2 Критичные кастомные поля (специфика Belberry — у коллеги будут свои ID!)

| Поле | Тип | Содержимое |
|---|---|---|
| `UF_CRM_1771495464` | enum 9 значений | **Причина отвала**: «Нет связи», «Выручка <30M», «Ушли к конкурентам», «Свой исполнитель», «Нехватка бюджета», «Передумали», «Действующий клиент», «СПАМ», «Нет такой услуги» |
| `UF_CRM_1772007767` | string | **Этап на котором умерла сделка** («Подготовка КП», «Догрев», «Квалификация»…) |
| `UF_CRM_635011179F7DD` | string | Свободный комментарий менеджера о причине |
| `UF_CRM_6179712C57A4D` | enum | Отрасль клиента |
| `UF_CRM_67B35193BAFB4` | money | Оборот компании (`value\|RUB`) |
| `UF_CRM_5FB3854A1EDBC` | string | Город |
| `OPPORTUNITY` | стандартное | Сумма сделки (часто 0 — само по себе диагностично) |
| **`UF_CRM_DEAL_AUDIT`** | file | **Куда заливаем готовый .docx** (создать у себя такое поле!) |

**Шаг 0 для коллеги:** найти/создать собственные эквиваленты этих полей и обновить мапинг в коде.

Получить список своих UF полей сделки:
```bash
python3 bx_call.py crm.deal.userfield.list '{}'
```

### 2.3 Стадии сделки (специфика, нужна расшифровка под свой портал)

Получить:
```bash
python3 bx_call.py crm.dealcategory.stage.list '{"id": 10}'
# id — CATEGORY_ID нужной воронки. crm.dealcategory.list даст список воронок.
```

### 2.4 OAuth — авторизация

Используется **локальное приложение** Битрикс (B24 OAuth, не входящий вебхук — у вебхука лимит ~2/сек и нет права писать в файловые UF при некоторых конфигах).

State хранится в JSON:
```json
{
  "payload": {
    "auth[access_token]": "...",
    "auth[refresh_token]": "...",
    "auth[client_endpoint]": "https://<portal>.bitrix24.ru/rest/",
    "auth[member_id]": "...",
    "auth[expires_in]": 3600
  }
}
```

**Refresh** через скрипт-обёртку, который дёргает `oauth.bitrix.info/oauth/token/`. У Belberry это `shared/scripts/bitrix-sync-state.sh` — простой `curl` с client_id/client_secret.

Запускать **перед каждой сессией разбора** — токен живёт 1 час.

---

## 3. РАСШИФРОВКА ЗВОНКОВ

### 3.1 Откуда mp3

Из стандартной телефонии Битрикс24. У каждого `crm.activity` с `TYPE_ID=2` и `PROVIDER_ID="VOXIMPLANT_CALL"` (или интегрированной IP-АТС) есть `FILES`. Если телефония внешняя без интеграции — звонков в Битрикс не будет, искать в логах АТС.

```python
r = call("crm.activity.get", {"id": activity_id})
files = (r.get("result") or {}).get("FILES") or []
if files:
    url = files[0]["url"]  # уже содержит auth-токен
    with urllib.request.urlopen(url, timeout=60) as rr:
        mp3_bytes = rr.read()
```

URL вида: `https://<portal>.bitrix24.ru/disk/uf/showFile/...?auth=<token>`.

### 3.2 Whisper

**Локально, `faster-whisper`** (не оригинальный openai-whisper — в 4 раза быстрее на CPU за счёт CTranslate2 backend).

```python
from faster_whisper import WhisperModel

model = WhisperModel("medium", device="cpu", compute_type="int8")

segments, info = model.transcribe(
    mp3_path,
    language="ru",          # обязательно — иначе угадывает на коротких репликах
    beam_size=5,
    vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=500),
)
```

Параметры:
- **model**: `medium` — оптимум для русского. `large-v3` лучше, но ×4 медленнее. `small` хуже, но ×3 быстрее. На больших объёмах разумно держать `medium` + `large-v3` как fallback для критичных звонков.
- **device**: `cpu` (на M1/M2 быстро; GPU на Mac возни больше чем профита).
- **compute_type**: `int8` — заметная скорость без видимой потери качества.
- **language**: `ru` (явно).
- **vad_filter**: `True` — выкидывает тишину/гудки, экономит 30–50% времени.

Скорость на M-серии: ~**1.5× реалтайма**. 11 минут аудио → ~17 минут.

### 3.3 Где модель и хранение

| Что | Где |
|---|---|
| Модель Whisper medium | `~/.cache/huggingface/hub/models--Systran--faster-whisper-medium/` (~1.5 GB, скачивается при первом запуске) |
| Python venv для Whisper | `/tmp/whisper_venv/` (можно постоянное место) |
| MP3 файлы | `/tmp/<name>_calls/<номер>_<дата>_<секунды>s.mp3` |
| Транскрипты | `/tmp/<name>_transcripts/*.txt` с таймкодами `[MM:SS]` |

### 3.4 Подводный камень: качество распознавания

Хорошо: общая речь, тон, смысл, таймкоды.
Плохо: латинские бренды (`Belberry` → `Болберин`, `Богури`, `Белберия`), аббревиатуры буква-в-букву, путаница похожих слов («лид» → «глид»).

Для задачи «найти возражение клиента» — **достаточно**. Для договоров — нет.

⚠️ **Персональные данные.** Транскрипты содержат ФИО, телефоны, иногда диагнозы (если медтематика). **Не в Git**, не отправлять в публичные облака, на VPS — только зашифрованный том.

---

## 4. LLM-АНАЛИЗ

### 4.1 Какая модель

**Claude Opus 4.7** в Claude Code. Отдельного API-клиента нет. Это **архитектурное решение** (не лень):
- Контекст 1М токенов — все транскрипты + методология + insights влезают.
- Цена меньше, чем у альтернативы build → eval → tune собственного промта.
- Память Claude (`~/.claude/projects/.../memory/`) накапливает кейсы и паттерны между сессиями.
- При желании переехать на API → нужно эмулировать память отдельным RAG-слоем (Obsidian-vault уже структурирован под это — frontmatter, wikilinks).

### 4.2 «Системный промт»

Полноценного system prompt у Belberry **нет** — Claude Code в каждой сессии **загружает PLAYBOOK** как контекст. Это даёт лучший результат, чем закостенелый prompt.

Структура контекста, которую Claude получает в начале разбора:

1. **PLAYBOOK.md** — пошаговый процесс (~5 KB)
2. **methodology/01-collect-deal-data.md** — какие методы Битрикс дёргать
3. **methodology/03-analyze-content.md** — 8 главных вопросов чек-листа
4. **insights/8-pillars-of-kp-failure.md** — накопленные системные паттерны
5. **insights/manager-communication-patterns.md** — типовые провалы в звонках
6. **insights/lost-deals-real-causes.md** — реальные причины vs CRM-метки
7. **templates/deal-review-template.md** — целевая структура .docx
8. **cases/\*.md** — 5 готовых разборов для калибровки стиля и глубины

Каждый файл — обычный markdown с YAML frontmatter (`type`, `tags`, `related`, `sot`). Обновляются после каждого разбора. Это **живой промт**.

Эквивалент для нового портала:
```
deal-analysis/
├── PLAYBOOK.md                          ← как делать
├── methodology/
│   ├── 01-collect-deal-data.md          ← UF и API специфика твоего портала
│   ├── 02-transcribe-calls.md           ← где брать mp3, параметры Whisper
│   ├── 03-analyze-content.md            ← чек-лист
│   └── 04-generate-word.md              ← pandoc
├── insights/                            ← накопленные паттерны (пусто на старте)
├── templates/deal-review-template.md    ← структура docx
└── cases/                               ← готовые разборы (растёт по мере работы)
```

### 4.3 Что в контексте на конкретную сделку

Для каждой сделки Claude получает:
- `/tmp/<name>_deal.json` — сырая карточка + связанные смарт-процессы
- `/tmp/<name>_calls.json` — список звонков с метаданными
- `/tmp/<name>_transcripts/*.txt` — все транскрипты с таймкодами
- (если есть) timeline-комментарии и переписка в plain text

### 4.4 Формат ответа

**Markdown по фиксированному шаблону** (`templates/deal-review-template.md`):

```
---
title: "Разбор сделки <название> — что мы потеряли и почему"
author: "Belberry · Отдел продаж"
date: "<ДД месяц ГГГГ>"
geometry: margin=2cm
---

# Разбор сделки <название>
## Резюме на одной странице          ← таблица
## Что обещало быть хорошим лидом     ← 5–7 пунктов
## Как это умирало (хронология)       ← таблица «дата → событие»
## Что было создано в системе         ← таблица: встречи/брифы/КП/звонки
## Содержательные провалы (с цитатами) ← 5–8 блоков с прямой речью клиента
## Что бы спасло сделку               ← 3 варианта по этапам
## Системные выводы для отдела        ← таблица «что сломано → как лечить»
## Главный вывод                      ← 1 абзац
```

Целевой объём: **18–25 страниц** .docx. Меньше — поверхностно, больше — не читают.

JSON-вывод не используется — финальный артефакт человеко-читаемый, и Claude генерирует markdown сразу.

---

## 5. ГЕНЕРАЦИЯ ДОКУМЕНТА

### 5.1 Чем

**pandoc** (3.x). Не python-docx, не docx-js — pandoc даёт ToC, таблицы, цитаты, заголовки, frontmatter→титульник «бесплатно».

```bash
pandoc /tmp/<name>_review.md \
  -o ~/Desktop/Разбор_сделки_<name>.docx \
  --from markdown \
  --toc --toc-depth=2
```

Опции:
- `--toc` — оглавление
- `--toc-depth=2` — только H1 и H2
- `--from markdown` — стандартный pandoc-markdown (**не gfm** — иначе таблицы поедут)
- `--reference-doc=template.docx` (опционально) — если нужны фирменные шрифты, передать пустой .docx с заранее настроенными стилями

YAML frontmatter в начале md → титульник + поля 2 см:
```yaml
---
title: "Разбор сделки <name>"
author: "<команда продаж>"
date: "<дата>"
geometry: margin=2cm
---
```

Цитаты — через `>` markdown blockquote, pandoc делает «отступ + курсив».

### 5.2 Куда кладётся .docx

**Три места одновременно:**

1. `~/Desktop/Разбор_сделки_<name>.docx` — для пользователя под рукой (архив)
2. **`UF_CRM_DEAL_AUDIT` в карточке сделки** — обязательно. Без этого менеджер и РОП не видят разбор, vault им недоступен.
3. (опц.) summary-комментарий в timeline сделки

### 5.3 Прикрепление к UF-полю файла (обязательный шаг)

Это нетривиально для file-UF, поэтому отдельно:

```python
import base64

with open(f"/tmp/Разбор_сделки_{name}.docx", "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")

call("crm.deal.update", {
    "id": deal_id,
    "fields[UF_CRM_DEAL_AUDIT][fileData][0]": f"Разбор_сделки_{name}.docx",
    "fields[UF_CRM_DEAL_AUDIT][fileData][1]": b64,
})
```

Ключевое: формат **`fields[<UF>][fileData][0]=<имя>`** + **`fields[<UF>][fileData][1]=<base64>`**. Через webhook у некоторых порталов файловые UF не пишутся — нужен полноценный OAuth.

### 5.4 Summary-комментарий в timeline (опционально, но рекомендуется)

После прикрепления .docx:
```python
call("crm.timeline.comment.add", {
    "fields[ENTITY_ID]": deal_id,
    "fields[ENTITY_TYPE]": "deal",
    "fields[COMMENT]": (
        f"Аудит сделки готов. "
        f"Главный диагноз: {main_diagnosis}. "
        f"Топ-3 провала: {top3}. "
        f"Полный разбор в поле «Аудит сделки (Word)»."
    ),
})
```

---

## 6. ИНФРАСТРУКТУРА

### 6.1 Где крутится

**Локальный Mac (MacBook M1/M2).** Не VPS, не n8n, не Make.

Причины:
- Транскрипция содержит ПД клиентов → не уходит во внешние сервисы (политика Belberry)
- Claude Code и так живёт на машине разработчика
- 5 разборов в неделю не оправдывают серверную инфраструктуру

Когда переезжать на VPS:
- Если поток > 20 сделок/неделю
- Если нужен auto-trigger (например ежедневный дайджест всех закрытых сделок прошлого дня)
- Тогда: VPS + Whisper там + Claude API + Telegram-уведомления

### 6.2 Зависимости и версии

| Инструмент | Версия | Установка |
|---|---|---|
| Python | 3.11+ | `brew install python@3.11` |
| ffmpeg | latest | `brew install ffmpeg` |
| pandoc | 3.x | `brew install pandoc` |
| faster-whisper | 1.0+ | `pip install faster-whisper` |
| ftfy | latest | `pip install ftfy` (для битых транскрипций) |
| Whisper model | `medium` (~1.5 GB) | автозагрузка при первом `WhisperModel("medium")` |

Зависимостей Python для самих скриптов сбора **ноль** — только stdlib (`urllib`, `json`, `base64`). Это сознательное решение — не таскать requirements за one-shot скриптами.

### 6.3 Переменные / конфиг

Не env-переменные, а **JSON state-файл**:

```
~/.config/<project>/bitrix24-state/install.latest.json
```

Содержит:
- `payload.auth[access_token]` — текущий OAuth-токен
- `payload.auth[refresh_token]` — для refresh
- `payload.auth[client_endpoint]` — endpoint REST (`https://<portal>.bitrix24.ru/rest/`)
- `payload.auth[member_id]` — ID портала

Refresh-скрипт:
```bash
#!/usr/bin/env bash
# bitrix-sync-state.sh
STATE=~/.config/<project>/bitrix24-state/install.latest.json
CLIENT_ID=<from env or hardcoded for local app>
CLIENT_SECRET=<...>
REFRESH=$(jq -r '.payload."auth[refresh_token]"' "$STATE")
NEW=$(curl -s "https://oauth.bitrix.info/oauth/token/?grant_type=refresh_token&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET&refresh_token=$REFRESH")
# обновить access_token, refresh_token, expires_in в state.json
```

Файлов с секретами **не должно быть в git**. Belberry хранит в `~/.config/vibecoding/` и в `shared/config/bitrix24-state/` который в .gitignore.

### 6.4 Точки выхода файлов на диске

```
~/.config/<project>/bitrix24-state/install.latest.json    ← OAuth state
~/.cache/huggingface/hub/models--Systran--faster-whisper-medium/    ← Whisper модель
/tmp/whisper_venv/                                        ← Python venv для Whisper
/tmp/<name>_deal.json                                     ← сырая карточка (промежуточный)
/tmp/<name>_calls.json                                    ← список звонков (промежуточный)
/tmp/<name>_calls/*.mp3                                   ← mp3 файлы (ПД!)
/tmp/<name>_transcripts/*.txt                             ← транскрипты (ПД!)
/tmp/<name>_review.md                                     ← markdown-источник
~/Desktop/Разбор_сделки_<name>.docx                       ← финальный артефакт
<vault>/09-Projects/<project>/cases/<name>.md             ← паттерны в Obsidian
```

`/tmp/*` чистится автоматически OS. `~/Desktop/*.docx` остаются как архив.

---

## 7. ИЗВЕСТНЫЕ ПОДВОДНЫЕ КАМНИ

### 7.1 Сложные моменты

**1. Файловые UF-поля и webhook.** Через входящий webhook (тип "вебхук", не "приложение") `crm.deal.update fields[UF_FILE]` часто не работает — портал возвращает 200 OK, но файл не появляется. **Решение:** локальное OAuth-приложение Битрикс. Получить `auth[access_token]` + `auth[refresh_token]` и работать через него.

**2. `crm.activity.update` не позволяет менять owner.** Если нужно перепривязать звонок к другой сделке — `crm.activity.update fields[OWNER_ID]` молча игнорируется или возвращает «Fields is not specified». **Решение:** `crm.activity.binding.add` / `crm.activity.binding.delete`. (Не критично для пайплайна аудита, но впишется в смежные задачи.)

**3. Wazzup-переписка в timeline.** Сообщения WhatsApp/Telegram через Wazzup приходят как `crm.timeline.comment` с особым форматированием. Часто содержит HTML и base64 вложения. Парсить аккуратно — лучше через регулярку выдрать text-content и таймстампы.

**4. Whisper и латинские бренды.** `Belberry` → `Болберин`, `Богури` и т.п. Если в звонках важны бренды (например название клиента) — добавить пост-обработку: `transcript.replace("Болберин", "Belberry")` или промтом сообщить Claude список аббревиатур.

**5. Двойная кодировка UTF-8.** Если транскрипция пришла из стороннего сервиса (memoai.tech и т.п.) — может быть `Ð¡Ð¿Ð¸ÐºÐµÑ` вместо `Спикер`. Лечится `ftfy.fix_text(text)`, иногда нужно два прохода.

**6. ID UF-полей у вас будут другими.** Перечисленные в разделе 2.2 — специфика Belberry. Первый шаг для коллеги: `crm.deal.userfield.list` → выписать свои аналоги «причина отвала», «этап смерти» и т.п. Без этого Claude не сможет сопоставить CRM-метку с реальностью.

**7. Стадии воронок специфичны.** Маппинг `C10:EXECUTING` ↔ «Подготовка КП» — у вас будут другие коды. `crm.dealcategory.stage.list` даст актуальный список.

**8. Whisper и тишина.** Если в звонке долгая тишина (записан hold music или нет ответа) — Whisper может выдать «Спасибо за внимание» (типовая галлюцинация). `vad_filter=True` + `min_silence_duration_ms=500` лечит. Звонки длительностью 0 секунд игнорировать (это «не дозвонился» — звонок без файла).

**9. PII (персональные данные).** Транскрипции содержат имена, телефоны, иногда медицинские факты. **Никогда не пушить в git, не отправлять во внешние LLM-API без согласия владельца портала, удалять с диска после завершения разбора.** Если работаешь через Claude API (а не Claude Code локально) — это **дополнительный риск**, обсудить с DPO.

**10. Контекст Claude vs объём аудио.** Если у сделки 50+ звонков по 10 минут — транскрипты могут не влезть. Стратегия: сначала отфильтровать звонки длительностью <30 секунд (нулевые), затем по критичным датам (последние перед отвалом, первый разговор после отправки КП). 10–15 звонков с разбором обычно даёт полную картину.

### 7.2 Ограничения Битрикс24 REST которые обошли

| Лимит | Как обходим |
|---|---|
| 2 запроса/сек на webhook | OAuth-приложение даёт ~50 RPS |
| `crm.activity.list` без OWNER_ID возвращает всё (медленно) | Всегда фильтровать по `OWNER_TYPE_ID=2, OWNER_ID=<deal>` |
| `crm.item.list` не отдаёт UF по умолчанию | Передавать `select[]=*&select[]=UF_*` или `select[]=ufCrm...` для UCI-стиля |
| `crm.timeline.comment.list` пагинация по 50 | Цикл с `start=0, 50, 100…` |
| Файлы mp3 экспайрятся через ~1 час | Скачивать сразу после `crm.activity.get`, не складывать URL «на потом» |

### 7.3 Что проверить в первую очередь у себя (чек-лист для Claude Code коллеги)

```
[ ] 1. Создать локальное OAuth-приложение Битрикс
       (Настройки → Разработчикам → Другое → Локальное приложение)
       Scope минимум: crm, telephony, user, im
[ ] 2. Сохранить client_id/client_secret + получить первичный access_token+refresh_token
       → ~/.config/<project>/bitrix24-state/install.latest.json
[ ] 3. Написать bitrix-sync-state.sh для refresh
[ ] 4. Создать UF-поле "Аудит сделки (Word)" типа "Файл" у сущности «Сделка»
       Запомнить FIELD_NAME (что-то вроде UF_CRM_DEAL_AUDIT или UF_CRM_<timestamp>)
[ ] 5. Получить список своих UF-полей: crm.deal.userfield.list
       Сопоставить с таблицей 2.2 (причина отвала, этап смерти, оборот, отрасль, город)
[ ] 6. Получить смарт-процессы: crm.type.list
       Сопоставить с 1048 (встречи) / 1056 (брифы) / 1106 (КП) — у вас будут свои entityTypeId
[ ] 7. Получить стадии воронок: crm.dealcategory.list + crm.dealcategory.stage.list
       Зафиксировать в methodology/01-collect-deal-data.md
[ ] 8. Установить ffmpeg + pandoc + python venv + faster-whisper
[ ] 9. Прогнать smoke на одной закрытой сделке с 1-2 звонками от начала до конца
[ ] 10. Убедиться что .docx прикрепляется к UF-полю (главный риск)
[ ] 11. Адаптировать insights/ под свой бизнес — у вас будут свои паттерны провалов,
        чек-лист из 03-analyze-content нужно перенастроить
```

### 7.4 Что НЕ автоматизировано осознанно

- Содержательный анализ (шаг 3) делает **сам Claude Opus 4.7** в Claude Code. Не пытайтесь подменить его на отдельный API-вызов с фиксированным промтом — потеряете качество и адаптивность к новым типам сделок.
- Не делается автоматический разбор всех сделок подряд. Каждый разбор = отдельный запрос. Это **фича**: разбор по факту читается командой, а 50 авто-разборов в неделю → никто не прочтёт.
- Не отправляется в публичные облака (Google Docs, Dropbox). .docx живёт в карточке сделки внутри Bitrix.

---

## 8. ПРИЛОЖЕНИЕ — Минимальная обёртка REST (bx_call.py)

```python
"""Минимальный CLI-вызов REST. stdlib only."""
import json, sys, urllib.request, urllib.parse

STATE = "~/.config/<project>/bitrix24-state/install.latest.json"

def load_auth():
    import os
    with open(os.path.expanduser(STATE)) as f:
        d = json.load(f)
    p = d["payload"]
    return p["auth[access_token]"], p["auth[client_endpoint]"]

def flatten(prefix, value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            flatten(f"{prefix}[{k}]", v, out)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            flatten(f"{prefix}[{i}]", v, out)
    else:
        out[prefix] = value

def call(method, params=None):
    token, endpoint = load_auth()
    params = params or {}
    flat = {}
    for k, v in params.items():
        flatten(k, v, flat)
    flat["auth"] = token
    url = endpoint.rstrip("/") + "/" + method
    data = urllib.parse.urlencode(flat, doseq=True).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

if __name__ == "__main__":
    method = sys.argv[1]
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(call(method, params), ensure_ascii=False, indent=2))
```

Использование:
```bash
python3 bx_call.py crm.deal.get '{"id":18538}'
python3 bx_call.py crm.item.list '{"entityTypeId":1106,"filter":{"parentId2":18538}}'
python3 bx_call.py crm.activity.list '{"filter":{"OWNER_TYPE_ID":2,"OWNER_ID":18538,"TYPE_ID":2}}'
```

---

## 9. ССЫЛКИ И ОБРАЗЦЫ

**Готовые .docx разборов как ориентир качества:**
- `Разбор_сделки_mpya.ru.docx` — постмортем закрытого отвала (18 стр)
- `Разбор_сделки_sinai-clinic.ru.docx` — аудит открытой сделки (22 стр)
- `Разбор_сделки_mitekpumps.ru.docx` — аудит тендерной сделки

**Стандарт документации Битрикс REST:** https://apidocs.bitrix24.ru/

**faster-whisper:** https://github.com/SYSTRAN/faster-whisper

**pandoc Word output:** https://pandoc.org/MANUAL.html#options-affecting-specific-writers

---

*Документ описывает реально работающий пайплайн на 2026-05-21.
Для адаптации Claude Code должен пройти чек-лист 7.3 и адаптировать
ID UF-полей и стадий воронок под свой портал. После 3–5 успешных
разборов начнут накапливаться собственные insights/ — это нормально
и ожидаемо.*
