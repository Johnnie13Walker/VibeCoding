# Acoola.Team — лендинг digital-агентства

Продакшен-готовый одностраничник на Next.js 14 (App Router) + TypeScript + Tailwind CSS + Framer Motion.

## Запуск

```bash
npm install
npm run dev
```

Дев-сервер: http://localhost:3000.

## Сборка

```bash
npm run build
npm start
```

## Полезные команды

```bash
npm run typecheck   # tsc --noEmit
npm run lint        # next lint
```

## Структура проекта

```
acoola-landing/
├── app/
│   ├── layout.tsx          # шрифты, метатеги, Open Graph, Schema.org, Metrika placeholder
│   ├── page.tsx            # композиция всех секций
│   └── globals.css         # Tailwind + CSS-переменные темы
├── components/
│   ├── sections/           # Hero, Stats, Services, Cases, Approach, Team, Awards, Testimonials, FAQ, CTA
│   ├── ui/                 # Button, Card, Badge, ServiceCard, CaseCard, CountUp
│   └── layout/             # Header, Footer
├── lib/
│   ├── content.ts          # ВЕСЬ контент сайта в одном месте, типизированный
│   └── utils.ts            # cn() — объединение CSS-классов
└── public/
    └── og-image.jpg        # 1200×630 для Open Graph (TODO: добавить файл)
```

Весь копирайт лендинга лежит в [`lib/content.ts`](./lib/content.ts) — редактировать тексты можно, не заходя в JSX.

## Дизайн-система

Цвета объявлены как CSS-переменные в [`app/globals.css`](./app/globals.css) и пробрасываются в Tailwind:

| Токен            | Назначение                                  | Значение                |
| ---------------- | ------------------------------------------- | ----------------------- |
| `bg`             | Основной фон                                | `#0a0a0b`               |
| `surface`        | Фон карточек                                | `#111114`               |
| `accent`         | CTA, цифры, hover                           | `#00e5c7`               |
| `accent-strong`  | Hover-состояние acent-кнопок                | `#00c2a8`               |
| `text`           | Основной текст                              | `#ffffff`               |
| `muted`          | Подписи и второстепенный текст              | `#7a7a85`               |
| `border`         | Границы карточек и разделители              | `rgba(255,255,255,.08)` |

Шрифты: `Manrope` (Display) и `Inter` (Body) — через `next/font/google`.

## Аналитика

- В `app/layout.tsx` оставлен закомментированный сниппет Яндекс.Метрики и плейсхолдер `METRIKA_ID`.
- Чтобы включить — раскомментируйте блок в `<body>` и подставьте идентификатор счётчика.

## Schema.org

В `<body>` рендерится JSON-LD `Organization` с полями `name`, `url`, `slogan`, `description`, `email`, `telephone`, `address`. Поле `sameAs` (соцсети) пустое — см. TODO ниже.

## TODO до публикации

| Где                                       | Что сделать                                                                          |
| ----------------------------------------- | ------------------------------------------------------------------------------------ |
| `lib/content.ts` → `services[*].price`    | Подтвердить ориентировочные цены по всем 8 услугам                                   |
| `lib/content.ts` → `company.positioningBadge` | Уточнить год основания агентства (сейчас «С 2019 года»)                          |
| `lib/content.ts` → `team`                 | Подтвердить распределение людей по 6 направлениям, при необходимости добавить `count` |
| `lib/content.ts` → `faq[0]`               | Подтвердить минимальные пороги бюджета по услугам                                    |
| `app/layout.tsx` → `organizationJsonLd.sameAs` | Добавить ссылки на соцсети (VK, Telegram, ВКонтакте, и т.д.)                    |
| `app/layout.tsx` → `METRIKA_ID`           | Вставить идентификатор Яндекс.Метрики и раскомментировать сниппет                    |
| `public/og-image.jpg`                     | Положить картинку 1200×630 px для соцсетей                                           |
| `components/layout/Footer.tsx`            | Подтвердить ссылки в колонке «Компания» и «Партнёрам» (Блог, Вакансии, AcoolaShop)  |
| `components/sections/Cases.tsx` (`href`)  | Прописать реальные URL кейсов в `lib/content.ts → cases[*].href`                     |
| `components/sections/CTA.tsx`             | Подключить отправку формы в CRM/почту вместо `console.info`                         |
| Политика конфиденциальности и карта сайта | Создать страницы и заменить `href="#"` в Footer                                      |

## Что не сделано осознанно

- Стоковые изображения и логотипы клиентов в кейсах не вставлены — ждут реальных файлов.
- Карусель отзывов — без автоплея (по требованию ТЗ).
- Слайдеры и тяжёлые JS-библиотеки не использованы.

## Lighthouse

Цели: Performance ≥ 90, Accessibility ≥ 95, Best Practices ≥ 95, SEO ≥ 95. Перед прогонкой
закройте dev-режим и снимайте метрики со сборки `npm run build && npm start`.
