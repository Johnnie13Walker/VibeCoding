# Codex-промт — Global Sales Dashboard, Фаза 5 (Calendar UI + Day Report Page)

> Единый промт. Claude спланировал и отревьюил (3 плана verified, checker PASSED с первой попытки). Codex собирает локально, атомарными коммитами.

## Контекст

Подпроект `/Users/pro2kuror/Desktop/VibeCoding/belberry/sales/sales_command_center/`, ветка `feat/global-sales-dashboard`. Фазы 1-4 готовы (схема, ETL, LLM-разбор, auth-каркас Next.js). Эта фаза = веб-интерфейс: календарь → отчёт дня.

Планы (читай с диска, `.planning/` gitignored):
- `.planning/phases/05-calendar-ui-day-report-page/05-01-PLAN.md` (волна 1) — установка shadcn/ui Calendar + react-day-picker (ru), `lib/reports.ts` (availableReportDates/getReportHtml), `lib/dates.ts` (zod-валидация даты) + тесты на mock-db. → WEB-01/02/03 (данные).
- `.planning/phases/05-calendar-ui-day-report-page/05-02-PLAN.md` (волна 2) — `/day/[date]` Route Handler: session self-check + валидация даты + **DOMPurify.sanitize** + text/html + 404 + тесты. → WEB-02.
- `.planning/phases/05-calendar-ui-day-report-page/05-03-PLAN.md` (волна 2) — `page.tsx` → серверная страница календаря + `CalendarView` ('use client', доступные дни кликабельны → /day в новой вкладке, архив по месяцам). → WEB-01/03.
- `.planning/REQUIREMENTS.md`, `.planning/research/PITFALLS.md`, `CLAUDE.md` (STACK-версии).

Волна 2 (05-02, 05-03) — параллельно (непересекающиеся файлы). Исполняй по `read_first`/`action`/`acceptance_criteria`.

## Эталон визуала

Отдельной UI-SPEC нет — направление вложено в планы. Звезда = сам отчёт (открывается своей самодостаточной страницей со своим inline CSS — эталон `belberry/sales/daily_report/отчеты/Сводка_продаж_2026-05-29.html`). Оболочка вокруг календаря — минимальная (заголовок, имя вошедшего, logout, календарь по центру). Светлая тема, Tailwind 3.4 + shadcn/ui, ru-локаль (пн — первый день), адаптивно.

## Git

Ветка `feat/global-sales-dashboard`, коммить ТОЛЬКО `belberry/sales/sales_command_center/**` поимённо. **Атомарные коммиты по планам** (`feat(gsd): ...` на каждый план/задачу — в Фазе 4 был один общий коммит, в этот раз дробнее для bisect). Trailer Co-Authored-By: Codex. Не пушить/мёржить.

## Среда и стек

- Next.js 15 + shadcn/ui + react-day-picker 10 + isomorphic-dompurify 3 + date-fns 3 + Tailwind **3.4.x** (НЕ v4 — несовместим с shadcn). Сеть онлайн → `npm install`/`npx shadcn@latest` нормально. `next build`/`next lint`/`npx tsc --noEmit`/`vitest run` проходят локально.
- **Postgres локально НЕТ** → query-слой reports (`lib/reports.ts`) в тестах на mock/in-memory; реальный — на VPS.
- Тесты vitest: календарь (доступные дни подсвечены/кликабельны, недоступные нет), /day (санитизация применяется — тест с `<script>` в исходном HTML, 404 на отсутствие/плохую дату, session-guard 401), валидация даты.

## Жёсткие рамки и security (СТОП-условия)

- Только **Фаза 5** (календарь + просмотр отчёта + архив). НЕ дашборды/графики (v2/Recharts), НЕ cron/Telegram (Фаза 6).
- Security (проверяется acceptance):
  - `/day/[date]` ОБЯЗАТЕЛЬНО `DOMPurify.sanitize(html)` (isomorphic-dompurify) перед отдачей — HTML содержит LLM-вывод (XSS). Отдавать `new Response(clean, {text/html})`, НЕ `dangerouslySetInnerHTML`.
  - `/day` + любой `/api/reports*` — ЯВНАЯ проверка сессии в route handler (middleware не покрывает route handlers), без сессии → 401/redirect.
  - Несуществующая/невалидная дата → 404 (zod-валидация формата YYYY-MM-DD), НЕ 500.
  - Календарь 'use client'; доступные даты грузятся в Server Component и передаются пропсом (плоский массив дат, НЕ секреты/сессия на клиент).
  - `window.open(..., '_blank', 'noopener')` (анти-tabnabbing).
- НЕ коммитить секреты. При неоднозначности — стоп и спроси.
- После каждого плана — `SUMMARY.md`.

## ВЫХОД (формат промта на ревью Claude)

```
# REVIEW — feat/global-sales-dashboard (Phase 5)
## КОНТЕКСТ — ветка @ <SHA>, базовая @ <SHA>
## КОММИТЫ — список
## ЧТО СОЗДАНО (по планам 05-01 / 05-02 / 05-03)
## ТЕСТЫ — vitest → N passed; tsc/build/lint OK; mock reports-слой
## ПОКРЫТИЕ — WEB-01..03 где закрыто
## SECURITY — DOMPurify (тест на <script>); session self-check в /day; 404 на плохую дату; данные сервер→проп; _blank noopener
## ЧТО НЕ ЗАПУСКАЛОСЬ — реальный Postgres / e2e просмотр (VPS)
## ОТКРЫТЫЕ ВОПРОСЫ / РИСКИ
## git log -<N>
```
