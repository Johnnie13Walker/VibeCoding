# Codex-промт — Global Sales Dashboard, Фаза 4 (Auth + Next.js Skeleton)

> Единый промт. Claude спланировал и отревьюил (3 плана verified, 2 итерации checker'а — security-фаза). Codex собирает локально, атомарными коммитами.

## Контекст

Подпроект `/Users/pro2kuror/Desktop/VibeCoding/belberry/sales/sales_command_center/`, ветка `feat/global-sales-dashboard`. Фазы 1-3 готовы (схема БД, ETL, рендер, LLM-разбор). web/ — пока только конфиги + db (schema.ts с users/login_codes/sessions). Эта фаза = passwordless-auth + каркас Next.js.

Планы (читай с диска, `.planning/` gitignored):
- `.planning/phases/04-auth-next-js-skeleton/04-01-PLAN.md` (волна 1) — фундамент: Bitrix-клиент для Next (user.get ACTIVE=Y + im.notify.personal.add от Ларисы 2812), iron-session config, генерация/хеш/проверка кода, миграция 0002 (attempts). → AUTH-01/02/04.
- `.planning/phases/04-auth-next-js-skeleton/04-02-PLAN.md` (волна 2) — route handlers request-code/verify/logout; rate-limit ПО EMAIL за 15-мин окно (перезапрос кода НЕ сбрасывает); живой ACTIVE-re-check; одноразовый хешированный код. → AUTH-01..04.
- `.planning/phases/04-auth-next-js-skeleton/04-03-PLAN.md` (волна 2) — middleware (инвертированный allowlist), robots/noindex, двухшаговая /login форма, authed-shell заглушка. → AUTH-03/04.
- `.planning/REQUIREMENTS.md`, `.planning/research/PITFALLS.md`, `CLAUDE.md` (стек + паттерн passwordless).

Волна 2 (04-02, 04-03) — параллельно (непересекающиеся файлы). Исполняй по `read_first`/`action`/`acceptance_criteria`.

## Git

Ветка `feat/global-sales-dashboard`, коммить ТОЛЬКО `belberry/sales/sales_command_center/**` поимённо. **Также закоммить незакоммиченную правку из ревью Фазы 3:** `runner/src/analyze_llm.py` — дефолт-модель уже изменена на `claude-sonnet-4-6` (Claude-ревью), оформи отдельным коммитом `chore(gsd): bump default anthropic model to claude-sonnet-4-6` перед началом Фазы 4. Атомарные коммиты `feat(gsd)/test(gsd)`, trailer Co-Authored-By: Codex. Не пушить/мёржить.

## Среда и стек

- Next.js 15 + iron-session 8 + Drizzle + vitest. Сеть онлайн → `npm install` нормально. `next build`/`next lint`/`npx tsc --noEmit`/`vitest run` должны проходить локально.
- **Postgres локально НЕТ** → DB-операции (Drizzle: login_codes/sessions/users) в тестах на mock/in-memory; реальный прогон на VPS.
- **Bitrix `im.notify.personal.add` = прод-write в мессенджер** → в тестах ЗАМОКАТЬ (Bitrix-клиент инъекцией); реальная отправка кода — только на VPS. Токен — из общего `BITRIX_STATE_PATH` (install.latest.json), владелец = Лариса 2812 (отсюда «от Ларисы»).

## Жёсткие рамки и security-гейты (СТОП-условия)

- Только **Фаза 4** (auth + каркас). НЕ календарь/день-страница/дашборды (Фазы 5-7) — главная `/` = authed-shell заглушка «скоро календарь».
- Security (обязательно, проверяется acceptance):
  - middleware ИНВЕРТИРОВАННЫЙ allowlist (публичные /login,/api/auth,/_next,статика; остальное → редирект на /login) + проверка сессии в КАЖДОМ /api handler (middleware не ловит Route Handlers).
  - rate-limit ПО EMAIL за 15-мин окно, ДО потребления кода; request-code тоже под лимитом.
  - код — SHA-256 хеш (не плейн), constant-time сравнение (timingSafeEqual), expiry 10 мин, одноразовость.
  - живой `ACTIVE=Y` re-check при verify (уволенный теряет доступ).
  - секреты (SESSION_SECRET, Bitrix-токен) — только server env, НЕ `NEXT_PUBLIC_`; iron-session httpOnly, НЕ JWT-localStorage.
  - robots.txt Disallow + noindex (данные чувствительные).
  - `im.notify.personal.add` от 2812 (НЕ im.message.add); ассерт что токен = Лариса.
- НЕ коммитить секреты (.env только пример). При неоднозначности — стоп и спроси.
- После каждого плана — `SUMMARY.md`.

## ВЫХОД (формат промта на ревью Claude)

```
# REVIEW — feat/global-sales-dashboard (Phase 4)
## КОНТЕКСТ — ветка @ <SHA>, базовая @ <SHA>
## КОММИТЫ — список (вкл. bump модели Фазы 3)
## ЧТО СОЗДАНО (по планам 04-01 / 04-02 / 04-03)
## ТЕСТЫ — vitest → N passed; tsc/next build/lint — OK; всё с моками Bitrix+БД
## ПОКРЫТИЕ — AUTH-01..04 где закрыто
## SECURITY-ПРОВЕРКИ — allowlist middleware; сессия в каждом handler; rate-limit по email (перезапрос не сбрасывает); хеш+constant-time+expiry+одноразовость; живой ACTIVE; нет NEXT_PUBLIC_ секретов; robots/noindex; im.notify от 2812
## ЧТО НЕ ЗАПУСКАЛОСЬ — реальный Bitrix im.notify / Postgres / e2e-логин (VPS)
## ОТКРЫТЫЕ ВОПРОСЫ / РИСКИ
## git log -<N>
```
