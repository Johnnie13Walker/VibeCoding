<!-- GSD:project-start source:PROJECT.md -->
## Project

**Global Sales Dashboard**

Полноценное веб-приложение («Командный центр продаж») для отдела продаж Belberry. Каждый рабочий день в 09:00 МСК оно автоматически формирует подробную сводку по работе ОП за прошлый рабочий день (с LLM-разбором проведённых встреч по транскриптам), хранит историю в БД и показывает её через свой интерфейс: календарь → отчёт за выбранный день в новой вкладке, плюс дашборды по отделу, сотрудникам и выполнению планов. Ссылка на свежий отчёт уходит в Telegram-чат менеджеров. Пользователи — руководитель, РОП и менеджеры по продажам.

**Core Value:** Руководитель и РОП каждое утро за 30 секунд видят полную, честную картину вчерашнего дня отдела (кого пинать, где горят деньги, как прошли встречи) — и могут открыть любой прошлый день из истории. Если всё остальное отвалится, это должно работать.

### Constraints

- **Tech stack**: Next.js (фронт+API) + PostgreSQL — выбрано пользователем. Python-ядро сбора/анализа переиспуем из `daily_report/`.
- **Hosting**: деплой на VPS «КлаудБот» (nginx, поддомен, TLS). Выполняет Codex (live/прод — не Claude).
- **Security**: данные чувствительные (клиенты, суммы, метрики людей) → авторизация обязательна с первого релиза веб-части; доступ только активным сотрудникам Битрикс24.
- **Process**: Claude проектирует и собирает приложение локально; деплой на VPS и прод-интеграции (cron, Bitrix-сообщения от Ларисы, Telegram) — Codex.
- **LLM**: Anthropic (предполагается переиспользование ключа/бюджета стека Лев Петровича — подтвердить).
- **Расписание**: Пн–Пт 09:00 МСК, период = прошлый рабочий день (учёт выходных/праздников РФ).
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Контекст выбора
## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Почему именно это |
|------------|---------|---------|-----------------|
| Next.js | **15.x** (latest stable) | Фронт + API Routes + SSR | App Router стабилен. Caching по умолчанию отключён в 15 (fetch не кешируется) — правильно для дашбордов с живыми данными. `next.config.ts` с TypeScript. Async Request APIs (`cookies`, `params`) — асинхронные, важно знать при работе с сессиями. |
| React | **19.x** | UI | Включён в Next.js 15. Server Components — запросы к БД прямо в компонентах без отдельного API-слоя. |
| PostgreSQL | **16.x** | Хранение истории, снимков, отчётов | Один сервер с Python-ETL. Python пишет, Next.js читает. Sub-millisecond latency на одном VPS. |
| Drizzle ORM | **0.45.x** (v1.0 RC ещё нестабилен) | Типобезопасный ORM поверх Postgres | SQL-ориентированный: схема = TypeScript, запросы = почти SQL. Нет "магии" Prisma. Лёгкий (`drizzle-kit` для миграций). Критично: Python-ETL пишет напрямую в Postgres — схема должна быть простой и предсказуемой, без ORM-магии в БД. Drizzle для этого идеален. |
| postgres.js | **3.4.x** | PostgreSQL-драйвер для Node | Рекомендован Drizzle для self-hosted Postgres. Быстрее `pg`, нативный Promise API, работает в Node.js без дополнительных настроек. |
| iron-session | **8.0.x** | Зашифрованные cookie-сессии | Рекомендован в официальной документации Next.js для App Router. Stateless (без Redis), зашифрованный seal через `@hapi/iron`. Идеально для одиночного VPS без внешнего кеша. Проще, чем next-auth, для custom passwordless-флоу. |
### Supporting Libraries
| Library | Version | Purpose | Когда использовать |
|---------|---------|---------|-------------|
| Recharts | **3.8.x** | Графики на дашбордах | 2.4M еженедельных загрузок, SVG + D3, декларативный React API. shadcn/ui Charts построены поверх него. Для воронки, динамики, план-факт. |
| shadcn/ui | **latest (2.x)** | UI-компоненты | Copy-paste компоненты (не npm-зависимость). Calendar, Card, Table, Badge, Sheet — всё нужное для дашборда есть. Совместим с Next.js 15 + React 19. |
| react-day-picker | **10.0.x** | Базовый движок календаря | shadcn/ui Calendar использует его под капотом. Версия 10 — текущий стабильный релиз. Для страницы выбора дня отчёта. |
| isomorphic-dompurify | **3.15.x** | Санитизация HTML-отчётов | DOMPurify работает только в браузере. isomorphic-dompurify решает проблему SSR в Next.js — один и тот же код на сервере и клиенте. Обязателен перед `dangerouslySetInnerHTML`. |
| Tailwind CSS | **3.4.x** | Стили | Интегрирован в shadcn/ui. Не тащить отдельный CSS-фреймворк. |
| zod | **3.x** | Валидация форм и API | Совместим с Server Actions Next.js 15. Для валидации email при логине, API-параметров. |
| date-fns | **3.x** | Манипуляции с датами | Локаль ru, рабочие дни РФ, форматирование. Легче Moment.js. Используется react-day-picker. |
| drizzle-kit | **0.31.x** | Миграции схемы | CLI для `generate` и `migrate`. Схема = source of truth. Python-ETL работает с той же схемой. |
### Development Tools
| Tool | Purpose | Настройки |
|------|---------|-------|
| TypeScript | Типобезопасность | `strict: true`. Drizzle генерирует типы из схемы автоматически. |
| ESLint + eslint-config-next | Линтер | Next.js 15 поддерживает ESLint 9 (flat config). |
| Turbopack (dev) | Быстрый dev-сервер | `next dev --turbo`. Стабилен в Next.js 15, до 76% быстрее старта. |
| PM2 | Процесс-менеджер на VPS | `exec_mode: 'cluster'`, `instances: 'max'`. Автоперезапуск, логи, zero-downtime reload. Стандарт для Node.js на VPS. |
| nginx | Reverse proxy + TLS | Проксирует на `localhost:3000`. Certbot для TLS. Обслуживает статику из `.next/static` напрямую. |
## Installation
# Создать проект
# Core runtime
# UI и графики
# Dev
# shadcn компоненты (по мере надобности)
## Архитектурные паттерны
### Паттерн 1: Чтение HTML-отчёта из Postgres
### Паттерн 2: Passwordless-аутентификация через Bitrix24
### Паттерн 3: Схема Drizzle совместная с Python-ETL
## Alternatives Considered
| Рекомендуем | Альтернатива | Когда альтернатива лучше |
|-------------|-------------|-------------------------|
| Drizzle ORM 0.45.x | Prisma 5.x | Если команда уже знает Prisma. У Prisma лучше документация для новичков, но сложнее с прямыми SQL-запросами и raw доступом из Python. |
| iron-session | next-auth v5 | Если нужны OAuth-провайдеры (Google, GitHub). Для custom passwordless через Bitrix24 next-auth добавляет сложность без выгоды. |
| postgres.js | node-postgres (pg) | `pg` — старый проверенный вариант. Используй если уже есть другие сервисы на `pg` в экосистеме. |
| Recharts + shadcn/ui | Tremor | Tremor = быстрый старт для SaaS-дашбордов с pre-built компонентами. Но менее гибкий для кастомной воронки и слот-графиков. Recharts + shadcn — больше контроля. |
| PM2 | Docker Compose | Docker проще унифицирует окружение, но требует больше памяти и опыта. На VPS с уже работающими cron-процессами Python PM2 органичнее. |
| isomorphic-dompurify | sanitize-html | sanitize-html проще настраивается через allowedTags, но хуже для SSR. isomorphic-dompurify — стандарт для Next.js. |
## What NOT to Use
| Избегать | Почему | Вместо |
|----------|--------|--------|
| Prisma с `db push` (без миграций) | Python-ETL пишет в ту же БД. `db push` затирает изменения схемы без SQL-истории. | `drizzle-kit generate && drizzle-kit migrate` — явные SQL-миграции под контролем git. |
| next-auth для этого кейса | Избыточен для единственного custom-провайдера (Bitrix24 код). Добавляет свои таблицы, сложную конфигурацию. | iron-session + custom route handlers. |
| JWT в localStorage | XSS-уязвимость. Любой скрипт на странице читает токен. | iron-session: httpOnly cookie, зашифровано, недоступно из JS. |
| Looker Studio / внешние BI | Пользователь явно отказался. Требует отдельного источника данных, нет прямого Postgres. | Recharts + shadcn внутри приложения. |
| `dangerouslySetInnerHTML` без sanitize | LLM-вывод в HTML-отчёте может содержать `<script>`. | Всегда `DOMPurify.sanitize(html)` перед рендером. |
| React Server Components для интерактивных графиков | Recharts — клиентская библиотека (D3/SVG манипуляции). | `'use client'` на компонентах с графиками. Данные грузить в Server Component родителе, передавать как props. |
| `instances: 1` в PM2 | Одноядерный процесс не использует VPS. | `instances: 'max'` — PM2 cluster mode по числу CPU. |
| Tailwind v4 (alpha) | Несовместим с shadcn/ui в текущих версиях. | Tailwind v3.4.x — стабильный, проверенный с shadcn. |
## Stack Patterns by Variant
- Используй только: Next.js + Drizzle + postgres.js + iron-session + isomorphic-dompurify
- shadcn/ui добавляй по мере появления конкретных UI-компонентов
- Recharts только в Фазе 5+ (дашборды)
- Начинай с JSDoc-аннотаций в `.js` файлах, постепенно мигрируй
- Drizzle работает с JS, но теряет главное преимущество — автотипы
- Рассмотри: Python-ETL делает всю логику, Next.js = thin display layer
- `instances: 2` вместо `'max'` в PM2
- Postgres с `shared_buffers = 256MB`
- Отключи Turbopack в проде (только `next start`)
## Version Compatibility
| Пакет | Совместим с | Примечания |
|-------|-------------|------------|
| next@15.x | react@19.x | Обязательно! Next.js 15 требует React 19 для App Router. |
| drizzle-orm@0.45.x | postgres@3.4.x | `postgres.js` — рекомендованный драйвер Drizzle для node. |
| drizzle-orm@0.45.x | drizzle-kit@0.31.x | Версии должны быть синхронизированы, иначе CLI ломается. |
| shadcn/ui (2026) | react-day-picker@10.x | shadcn Calendar перешёл на v9/v10 в новых релизах. Проверяй версию при `npx shadcn@latest add calendar`. |
| iron-session@8.x | next@15.x | Поддерживает App Router, Server Actions, async cookies API. |
| isomorphic-dompurify@3.x | next@15.x | jsdom под капотом — работает в Edge Runtime Next.js. |
| tailwindcss@3.4.x | shadcn/ui | Tailwind v4 (alpha) несовместим с текущим shadcn/ui. |
| Node.js | ≥18.18.0 | Минимум для Next.js 15. |
## Деплой на VPS (конфигурация)
### Next.js standalone build
### PM2 конфигурация
### nginx конфигурация (фрагмент)
## Sources
- [Next.js 15 Release Blog](https://nextjs.org/blog/next-15) — версия, App Router, async params, standalone build, self-hosting. **HIGH confidence.**
- [Drizzle ORM Docs — Get Started](https://orm.drizzle.team/docs/get-started) — текущая версия 0.45.x (v1.0 RC нестабилен). **HIGH confidence.**
- [iron-session GitHub](https://github.com/vvo/iron-session) — v8.0.4, App Router совместимость. **HIGH confidence.**
- [shadcn/ui Date Picker](https://ui.shadcn.com/docs/components/radix/date-picker) — react-day-picker v10. **HIGH confidence.**
- [Recharts vs Tremor сравнение 2026](https://www.pkgpulse.com/guides/recharts-v3-vs-tremor-vs-nivo-react-charting-2026) — Recharts v3 стандарт, 2.4M загрузок. **MEDIUM confidence** (вторичный источник).
- [DOMPurify + Next.js SSR](https://dev.to/hijazi313/using-dangerouslysetinnerhtml-safely-in-react-and-nextjs-production-systems-115n) — isomorphic-dompurify паттерн. **MEDIUM confidence.**
- [VPS Deploy Next.js + PM2 + nginx](https://vps.do/how-to-deploy-a-next-js-full-stack-app-on-a-vps-with-postgresql-and-pm2/) — standalone + cluster mode. **MEDIUM confidence.**
- npm info (локальный): next@16.2.6 (**ВНИМАНИЕ**: 16.2.6 — это canary, latest stable 15.x), drizzle-orm@0.45.2, iron-session@8.0.4, recharts@3.8.1, postgres@3.4.9, react-day-picker@10.0.1, isomorphic-dompurify@3.15.0, drizzle-kit@0.31.10. **HIGH confidence** (npm registry).
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
