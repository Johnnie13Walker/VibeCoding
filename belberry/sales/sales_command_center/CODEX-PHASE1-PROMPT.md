# Codex-промт — Global Sales Dashboard, Фаза 1 (Infrastructure)

> Передать Codex как единый промт. Claude спланировал (планы в `.planning/`), Codex собирает Фазу 1 локально. Реализуй ВСЁ одним заходом, атомарными коммитами внутри.

## Контекст

Проект **Global Sales Dashboard** (Sales Command Center) — Next.js + PostgreSQL веб-приложение для отдела продаж Belberry. Рабочая папка подпроекта:
`/Users/pro2kuror/Desktop/VibeCoding/belberry/sales/sales_command_center/`

GSD-планы лежат локально (gitignored, не в git) — читай с диска:
- `.planning/PROJECT.md` — что за продукт, решения, ограничения
- `.planning/ROADMAP.md` — 6 фаз, цель и критерии успеха Фазы 1
- `.planning/REQUIREMENTS.md` — требования (Фаза 1 = INFRA-01, INFRA-02, INFRA-03)
- `.planning/research/` — STACK.md (версии/паттерны), ARCHITECTURE.md (9 таблиц, разделение слоёв), PITFALLS.md, SUMMARY.md
- `.planning/phases/01-infrastructure/*-PLAN.md` — **3 готовых плана**, исполняй их ЗАДАЧА-ЗА-ЗАДАЧЕЙ:
  1. `01-project-skeleton-PLAN.md` (волна 1) — скелет runner/ + web/, Next.js 15 + Drizzle config, .env.example + .gitignore
  2. `01-db-schema-PLAN.md` (волна 2) — Drizzle-схема 9 таблиц (TIMESTAMPTZ + UNIQUE натуральные ключи) + SQL-миграция + db-инстанс
  3. `01-runner-shared-utils-PLAN.md` (волна 2) — `now_msk` / `msk_day_utc_range` / `prev_working_day` (праздники РФ через workalendar), fail-fast env-загрузка, UPSERT-хелпер + pytest

Эталон HTML-отчёта (понадобится в Фазе 2, не сейчас): `belberry/sales/daily_report/отчеты/Сводка_продаж_2026-05-29.html`.

## Git (ВАЖНО — не запутать с миграцией)

Сейчас репо на ветке `feat/migrate-engineer-into-cloudbot` с ~80 незакоммиченными файлами (чужая работа по миграции — НЕ ТРОГАТЬ).

1. Создай ветку **от текущего HEAD** (working tree не трогаем, stash не нужен):
   `git checkout -b feat/global-sales-dashboard`
2. Коммить **ТОЛЬКО** файлы внутри `belberry/sales/sales_command_center/` (кроме `.planning/`, которая в .gitignore). Никогда `git add -A` / `git add .` — только явные пути новых файлов приложения.
3. Незакоммиченные 80 файлов миграции оставь как есть (они не попадут в коммиты дашборда при поимённом add).
4. Атомарные коммиты — по одной задаче плана на коммит, Conventional Commits:
   `feat(gsd): <что>`, `chore(gsd): <что>` (scope `gsd` = global sales dashboard).
   Trailer: `Co-Authored-By: Codex`.
5. НЕ пушить, НЕ мёржить, НЕ открывать PR — это сделает пользователь.

## Среда

Сеть **онлайн** (проверено: npm registry + pypi доступны). Node 25 / npm 11 / Python 3.9 — есть.

- **Ставь зависимости нормально** (онлайн): `npm install` для web/ (Next.js 15, drizzle-orm, drizzle-kit, postgres.js, iron-session — версии из STACK.md), `pip install` в venv для runner/ (`workalendar`, `python-dotenv`, `psycopg[binary]`, `pytest`). Реестры доступны — не закладывай офлайн-обходы.
- **Postgres локально НЕТ** — это единственное ограничение Фазы 1. Схему генерируй через `drizzle-kit generate` (БД не нужна, только TS-схема → SQL-файл). Миграцию **не применяй** (нет БД) — только сгенерируй `db/migrations/0000_init.sql` как артефакт. Применение миграции и live-БД — Фаза 2+ на VPS.
- **pytest** для time-утилит/конфига/UPSERT-хелпера должен пройти (тесты не требуют живой БД — проверяют логику МСК/праздников/построение SQL-строки). Прогони и приложи результат.
- Если какая-то конкретная установка реально упадёт (не из-за офлайна, а по другой причине) — зафиксируй в SUMMARY и спроси, не замалчивай.

## Жёсткие рамки (СТОП-условия)

- Только **Фаза 1**. Никакого ETL/LLM/auth/UI/дашбордов (это фазы 2–6) — даже если кажется логичным.
- НЕ деплоить, не трогать VPS, не выполнять live/прод-команды, не обращаться к Bitrix/проду.
- НЕ коммитить секреты: `.env` в .gitignore, в репо только `.env.example` с плейсхолдерами.
- При неоднозначности или если план требует решения вне его текста — **остановись и спроси**, не придумывай.
- Не рефактори чужой код вне sales_command_center/.
- Следуй `read_first` / `acceptance_criteria` каждой задачи — это критерии приёмки.
- После каждого плана создай `SUMMARY.md` рядом с PLAN.md (что сделано, отклонения, что не запускалось).

## ВЫХОД (обязательно — в формате готового промта на ревью Claude)

В конце верни блок ровно такого вида, чтобы я (Claude) сразу провёл ревью:

```
# REVIEW — feat/global-sales-dashboard (Phase 1)
## КОНТЕКСТ
- Ветка: feat/global-sales-dashboard @ <SHA>
- Базовая: <откуда форкнул> @ <SHA>
## КОММИТЫ
1. <SHA> <subject>
...
## ЧТО СОЗДАНО (по планам 01-project-skeleton / 01-db-schema / 01-runner-shared-utils)
- путь — что и зачем
## ТЕСТЫ
- pytest: <команда> → N passed (или почему не запускалось)
- drizzle generate: <результат / офлайн>
## ПОКРЫТИЕ ТРЕБОВАНИЙ
- INFRA-01/02/03 — где закрыто
## ЧТО НЕ ЗАПУСКАЛОСЬ
- <npm install / миграция / Postgres — явно>
## ОТКРЫТЫЕ ВОПРОСЫ / РИСКИ
- <если есть>
## git log -<N>
<копия>
```
