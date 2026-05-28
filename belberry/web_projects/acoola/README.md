# Acoola — web project + marketing assets

Объединённая папка проекта Acoola (одного из двух брендов агентства — see [reference-belberry-acoola-two-brands](file:///Users/pro2kuror/.claude/projects/-Users-pro2kuror-Desktop-VibeCoding/memory/reference_belberry_acoola_two_brands.md)). Перенесена 2026-05-28 из `~/Desktop/Cloude/` в рамках консолидации десктопа.

## Структура

```
acoola/
├── README.md
├── landing/                ← Next.js production app (acoola-landing)
│   ├── app/, components/, lib/, public/
│   ├── package.json (scripts: dev, build, start, lint, typecheck)
│   └── .gitignore (node_modules, .next, dist)
├── assets/                 ← brand assets (4.9 МБ)
│   ├── acoola_logo.png, acoola_logo_white.png
│   └── photos/ (Unsplash, для презентаций)
├── docs/                   ← маркетинг-материалы
│   ├── acoola_designer_brief.{docx,md}
│   ├── acoola_designer_tz_v3_short.{docx,md}
│   ├── acoola_marketing_kit_brief{,_v2}.{docx,md}
│   ├── acoola_marketing_kit_v{2,3_creative,4_reordered}.pptx
│   └── build_pptx{,_v3,_v4_reordered}.py (генераторы deck'ов)
├── build_acoola_deck.py    ← главный сборщик KP-deck (rich visual)
└── prep_assets.py          ← подготовка Unsplash фото под aspect ratio
```

## Запуск landing (Next.js)

```bash
cd belberry/web_projects/acoola/landing
npm install
npm run dev       # localhost:3000
npm run build     # prod build
npm run typecheck # ts проверки
```

## Запуск сборщика KP-deck

```bash
cd belberry/web_projects/acoola
pip install python-pptx pillow
python build_acoola_deck.py
```

## Что НЕ перенесено

- `node_modules/` (363 МБ) — не нужно в git, восстанавливается через `npm install`
- `.next/` (build cache) — не нужно
- `tsconfig.tsbuildinfo` — кеш TypeScript

## История

- **До 2026-05-28:** в `~/Desktop/Cloude/` (отдельная папка на десктопе)
- **2026-05-28:** перенесено в `belberry/web_projects/acoola/` как часть VibeCoding монорепо. `node_modules` исключён из переноса.
