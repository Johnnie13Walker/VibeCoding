# Codex-промт — Global Sales Dashboard, Фаза 3 (LLM Meeting Analysis)

> Единый промт. Claude спланировал и отревьюил (3 плана verified, 2 итерации checker'а). Codex собирает Фазу 3, атомарными коммитами. Это фаза качества — глубокий разбор встреч.

## Контекст

Подпроект `/Users/pro2kuror/Desktop/VibeCoding/belberry/sales/sales_command_center/`, ветка `feat/global-sales-dashboard`. Фазы 1+2 готовы (схема, ETL, детерминированный рендер с `data-llm-placeholder`).

Планы Фазы 3 (читай с диска, `.planning/` gitignored):
- `.planning/phases/03-llm-meeting-analysis/03-01-PLAN.md` (волна 1) — скачивание транскрипта (`ufCrm16Transcript.urlMachine`) + enrich + сверка соответствия встрече + СИНТЕТИЧЕСКАЯ фикстура. → LLM-01.
- `.planning/phases/03-llm-meeting-analysis/03-02-PLAN.md` (волна 2) — `analyze_llm.py`: per-meeting разбор по чек-листу (JSON, отлов «статус-vs-суть»), `analyze_day_narrative` (агрегатный нарратив), retry x3, mocked Anthropic. → LLM-02.
- `.planning/phases/03-llm-meeting-analysis/03-03-PLAN.md` (волна 3) — миграция `0001_meeting_transcript.sql` (transcript в meetings), изоляция (`partial_llm_failure`), `--phase llm` (читает из БД, без Bitrix, кеш), наполнение плейсхолдеров render. → LLM-03.
- `.planning/REQUIREMENTS.md`, `.planning/research/PITFALLS.md`, `.planning/research/ARCHITECTURE.md`.

Исполняй ЗАДАЧА-ЗА-ЗАДАЧЕЙ по `read_first`/`action`/`acceptance_criteria`.

## Эталон качества разбора (встроен в планы)

Чек-лист (DAILY-SALES-REPORT-SPEC.md + память): **брифинг** — диалог-не-анкета·потребность·кейсы·БЮДЖЕТ·след.шаг; **защита КП** — кейсы(обязательно)·аргументация цифр·запрос след.шагов·итоги клиенту. LLM ставит ✅/⚠️/❌ + цитата клиента из транскрипта + системный вывод. **Критично:** ловить расхождение «Bitrix-статус „успех“ vs суть по транскрипту» (реальный кейс kandela #2180: статус успех, но защита не закрыта). Нет транскрипта → честная пометка «записи нет», без выдумывания. Учитывать Wazzup-итоги.

Реальный транскрипт kandela `/tmp/sales_2905/transcript_2180.txt` — только для ЛОКАЛЬНОЙ ручной сверки формата; **в репозиторий НЕ копировать** (приватность). Фикстура для тестов — синтетическая (план 03-01).

## Git

Ветка `feat/global-sales-dashboard` (не новая). Коммить ТОЛЬКО `belberry/sales/sales_command_center/**` поимённо. Атомарные коммиты `feat(gsd)/test(gsd)`, trailer `Co-Authored-By: Codex`. Не пушить/мёржить.

## Среда и стек

- LLM = Anthropic Python SDK. Следуй best-practices: **prompt caching** системного промта (чек-лист переиспуётся по встречам дня), актуальная модель Claude, **retry x3 + backoff** (PITFALLS п.7). Ключ `ANTHROPIC_API_KEY` из env (стек Лев Петровича), через load_config Фазы 1 (fail-fast).
- **Реальные вызовы Anthropic — НЕ в тестах** (не жечь токены). Все тесты Фазы 3 офлайн с ЗАМОКАННЫМ клиентом (FakeAnthropic, фикс. JSON): парсинг транскрипта, сборка промта, маппинг JSON→analysis_json, нарратив, наполнение плейсхолдеров, **partial_llm_failure при исключении клиента**, идемпотентность (кеш analysis_json), `--phase llm` читает из БД.
- Postgres локально нет → mock-conn в тестах. Миграция 0001 — артефакт, не применять локально. Реальный прогон против Anthropic+Bitrix+Postgres — на VPS.

## Жёсткие рамки (СТОП-условия)

- Только **Фаза 3** (LLM-разбор + наполнение). НЕ делать auth/web/cron (Фазы 4-6).
- Изоляция обязательна: сбой/таймаут LLM → детерминированный отчёт Фазы 2 ВСЁ РАВНО рендерится (плейсхолдеры/фолбэки), день = `partial_llm_failure`. LLM-фаза НЕ должна ронять пайплайн.
- Реальные данные клиента в git НЕ коммитить (синтетическая фикстура). Секреты — только env.
- `html.escape` на всех динамических строках в HTML (память feedback_telegram_html_escape_dynamic_data).
- При неоднозначности — остановись и спроси.
- После каждого плана — `SUMMARY.md`.

## ВЫХОД (формат готового промта на ревью Claude)

```
# REVIEW — feat/global-sales-dashboard (Phase 3)
## КОНТЕКСТ — ветка @ <SHA>, базовая @ <SHA>
## КОММИТЫ — список
## ЧТО СОЗДАНО (по планам 03-01 / 03-02 / 03-03)
## ТЕСТЫ — pytest → N passed (enrich/analyze_llm/render/runner, всё с mock Anthropic)
## ПОКРЫТИЕ — LLM-01/02/03 где закрыто
## ПРОВЕРКИ КАЧЕСТВА — отлов статус-vs-суть; нет транскрипта→пометка; изоляция (сбой→partial_llm_failure+отчёт жив); --phase llm из БД без Bitrix; кеш
## ЧТО НЕ ЗАПУСКАЛОСЬ — реальный Anthropic/Bitrix/Postgres (VPS)
## ОТКРЫТЫЕ ВОПРОСЫ / РИСКИ
## git log -<N>
```
