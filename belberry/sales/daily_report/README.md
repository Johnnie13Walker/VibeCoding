# Belberry — ежедневный отчёт по отделу продаж

HTML-сводка «как вчера прошёл день у отдела продаж» Belberry. Готовится на следующее утро после рабочего дня, отдаётся РОПу.

**Цель:** за 30 секунд понять — как прошёл день, кого пинать, что глобально исправлять, ключевые задачи на сегодня, где сорвутся сделки.

## Структура папки

```
daily_report/
├── README.md          ← этот файл
└── отчеты/            ← все готовые Сводка_продаж_YYYY-MM-DD.html
```

**Правило:** каждый новый отчёт всегда сохраняем в `daily_report/отчеты/` под именем `Сводка_продаж_YYYY-MM-DD.html` (дата = день, за который отчёт, не день генерации). Никогда не оставлять на Desktop или в других местах.

## Где спецификация

Source of truth — в Obsidian Vault, материнский проект «Анализ сделок»:

- [/Users/pro2kuror/Documents/Cloudbot-Vault/09-Projects/belberry-deal-analysis/DAILY-SALES-REPORT-SPEC.md](file:///Users/pro2kuror/Documents/Cloudbot-Vault/09-Projects/belberry-deal-analysis/DAILY-SALES-REPORT-SPEC.md) — полная структура секций, правила данных, формулировок, визуала, источники Bitrix REST.

Связанные доки в том же проекте: `PLAYBOOK.md`, `methodology/`, `cases/`, `insights/`, `SYSTEMIC-PATTERNS-2026.md`, `SYSTEMIC-GOOD-PRACTICES-2026.md`.

## Структура самого отчёта (кратко)

Шапка → главное за 30 сек (горит/деньги/системно) → кого пинать → сделки под угрозой → цифры → менеджеры → встречи (со столбцом «итоги клиенту») → разбор встреч → брифы и КП → ачивки и стрики → 🐅 Тигр дня → системные паттерны → итог → техдолг → подвал.

**Визуал:** светлая жизнерадостная палитра (без тёмного фона), самодостаточный HTML (inline CSS, фото base64), цветовая кодировка зелёный/жёлтый/красный.

## Источники данных (Bitrix REST)

- `crm.activity.list` — звонки, встречи (запланированные/проведённые)
- `crm.timeline.comment.list` — Wazzup-переписка (в activity не попадает!)
- `crm.item.list` — встречи (1048), брифы (1056), КП (1106)
- `crm.deal.list`, `crm.stagehistory.list` — воронка
- `voximplant.statistic.get` — телефония
- `UF_CRM_16_TRANSCRIPT` — транскрипты встреч (PDF)

OAuth state: `/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json`. Refresh: `bash /Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh`.

## Ключевые правила (зафиксированы в memory)

- `feedback-client-contact-two-sources` — контакт с клиентом проверять по двум источникам (активности + Wazzup-лента)
- `feedback-client-contact-three-sources` — Wazzup в timeline лежит с AUTHOR_ID=2358 (Тартышева, технический пользователь интеграции), реального отправителя и текст «итогов встречи» парсить из тела COMMENT после маркера «Имя Фамилия:»
- `feedback-sales-metrics-official-source` — рейтинги по полю «Опер» из официальной сводки, не пересчитывать
- `feedback-report-tech-issues-bottom` — техпроблемы всегда в самом низу
- `feedback-verify-calendar-in-reports` — день недели через `datetime`, праздники не выдумывать
- `feedback-rop-works-with-base` — РОП, ведущий сделки лично, не подавать как провал
- `feedback-no-anglicisms` — без англицизмов, кратко и ясно
- `feedback-report-clickable-entities` — каждая сделка/бриф/встреча/КП в отчёте = ссылка на Битрикс24
- `feedback-belberry-user-names` — в Битрикс24 belberrycrm всегда «Фамилия Имя», никаких «id=…»

## Что планировалось, но не сделано

**Автоматизация:** скрипт на VPS, крон 08:30 МСК, сбор данных из Bitrix, генерация HTML, отправка ссылки/файла в Telegram РОПу. План из 5 слоёв (см. диалог 27.05.2026): ежедневный отчёт → AI-разбор встреч → извлечение обещаний → база знаний → еженедельная ретроспектива.

Пока генерация ручная (через Claude по данным Bitrix REST в текущей сессии).
