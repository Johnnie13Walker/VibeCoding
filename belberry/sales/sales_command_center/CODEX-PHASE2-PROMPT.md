# Codex-промт — Global Sales Dashboard, Фаза 2 (ETL Core + Report Rendering)

> Единый промт. Claude спланировал и отревьюил (3 плана verified, 2 итерации checker'а). Codex собирает Фазу 2 локально, атомарными коммитами.

## Контекст

Подпроект: `/Users/pro2kuror/Desktop/VibeCoding/belberry/sales/sales_command_center/`
Фаза 1 (Infrastructure) уже готова на ветке `feat/global-sales-dashboard` (схема БД, timeutil/config/db утилиты, скелет runner/+web/).

GSD-планы Фазы 2 (читай с диска, `.planning/` gitignored):
- `.planning/phases/02-etl-core-report-rendering/02-01-PLAN.md` (волна 1) — Bitrix REST клиент (cursor >ID, token-sync, retry) + `collect_day` по всем источникам + сбор фото + захват фикстуры 2026-05-29. Требования: DATA-02, DATA-03.
- `.planning/phases/02-etl-core-report-rendering/02-02-PLAN.md` (волна 2) — `transform.py`: resolve_target_date, зависшие сделки (по двум источникам контакта вкл. Wazzup), агрегация телефонии, build_db_rows (snake_case). Требования: DATA-01, DATA-03, DATA-04.
- `.planning/phases/02-etl-core-report-rendering/02-03-PLAN.md` (волна 3) — `render.py` (13 детерминированных секций, LLM = плейсхолдеры), идемпотентный `writer.py` (Postgres UPSERT), `daily_runner.py` CLI. Требования: DATA-04, RPT-01, RPT-02, RPT-03.
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` — контекст.

Исполняй планы ЗАДАЧА-ЗА-ЗАДАЧЕЙ, следуя `read_first` / `action` / `acceptance_criteria` каждой.

## Эталонная реализация и выход (ОБЯЗАТЕЛЬНО переиспуй)

- **Рабочие скрипты ручного прогона** `/tmp/sales_2905/*.py` — РЕФЕРЕНС логики (bx.py, collect.py, vox2.py, stuck2.py, details.py со СТАДИЯМИ, photos2.py, gen*.py рендер). Формализуй их в модули runner/, не изобретай заново.
- **Готовая фикстура 2026-05-29 уже есть** в `/tmp/sales_2905/`: `raw.json` (deals/stagehistory/activities/meetings/briefs/kp), `vox.json` (телефония за день), `users.json` (id→имя), `photos.json` (base64). **Переиспуй их как seed фикстуры** `runner/tests/fixtures/2026-05-29/` вместо повторного похода в Bitrix (если нужно дополнить — см. ниже про токен).
- **Эталонный HTML** (целевая структура, RPT-03): `belberry/sales/daily_report/отчеты/Сводка_продаж_2026-05-29.html` — CSS-каркас и порядок 13 секций брать отсюда.
- **Фаза 1 утилиты** (импортируй): `runner/src/timeutil.py` (now_msk, msk_day_utc_range, prev_working_day; добавь `next_working_day` если плана требует), `runner/src/config.py` (load_config), `runner/src/db.py` (connect, build_upsert_sql, upsert).

## Git

Продолжай на ветке `feat/global-sales-dashboard` (НЕ создавай новую). Коммить **только** `belberry/sales/sales_command_center/**` поимённо (никогда `git add -A`). 80 файлов миграции и прочее вне подпроекта — не трогать. Атомарные коммиты по задачам, Conventional Commits `feat(gsd)/test(gsd)/chore(gsd)`, trailer `Co-Authored-By: Codex`. НЕ пушить/мёржить/PR.

## Среда

Сеть онлайн. Node/npm/Python есть. **Postgres локально НЕТ.**
- Модульные тесты (pytest) — на JSON-фикстурах из `/tmp/sales_2905/` → `runner/tests/fixtures/2026-05-29/`. Все тесты Фазы 2 должны проходить ОФЛАЙН (без БД и без Bitrix) — сбор/трансформация/рендер тестируются на фикстуре, writer — на mock-conn.
- **Реальный прогон `collect→write` против живого Bitrix + Postgres — НЕ здесь**, это на VPS (отдельный шаг). Локально достаточно зелёных тестов на фикстуре + успешный `daily_runner.py --help`.
- Если для досбора фикстуры нужен Bitrix (read-only): токен — `bash /Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh`, затем читать через клиент. Но сначала попробуй обойтись готовыми json из /tmp/sales_2905/.

## Жёсткие рамки (СТОП-условия)

- Только **Фаза 2**. **НИКАКОГО реального LLM** (anthropic/messages.create/analyze_llm) — секции «Содержательный разбор встреч», нарратив «30 секунд», подпись Тигра рендерятся как `data-llm-placeholder` каркас. Это Фаза 3. (Планы содержат grep-гейты на отсутствие LLM — соблюдай.)
- НЕ деплоить, не трогать VPS, не выполнять прод-write в Bitrix (только read для фикстуры при необходимости).
- Соблюдай правила данных: имена не ID; контакт = два источника (activity + Wazzup AUTHOR_ID=2358, реальный отправитель в теле); стадии cat10/cat50 как в details.py; C10:LOSE/C50:APOLOGY = отвал, C50:LOSE = отложено; Тигр по телефонии С дисклеймером (офиц. «Опер» недоступна).
- НЕ коммитить секреты. При неоднозначности — остановись и спроси.
- После каждого плана — `SUMMARY.md` рядом с PLAN.md.

## ВЫХОД (в формате готового промта на ревью Claude)

```
# REVIEW — feat/global-sales-dashboard (Phase 2)
## КОНТЕКСТ
- Ветка @ <SHA>, базовая @ <SHA>
## КОММИТЫ
1. <SHA> <subject> ...
## ЧТО СОЗДАНО (по планам 02-01 / 02-02 / 02-03)
- путь — что и зачем
## ТЕСТЫ
- pytest: <команда> → N passed (collect/transform/render/writer/runner)
## ПОКРЫТИЕ ТРЕБОВАНИЙ
- DATA-01..04, RPT-01..03 — где закрыто
## СВЕРКА С ЭТАЛОНОМ
- 13 секций присутствуют? отказы/Тигр-дисклеймер/два источника контакта — да/нет
## ЧТО НЕ ЗАПУСКАЛОСЬ
- реальный collect→write (нет локального Postgres/прод — VPS)
## ОТКРЫТЫЕ ВОПРОСЫ / РИСКИ
## git log -<N>
```
