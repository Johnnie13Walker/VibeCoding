# Codex-промт — Global Sales Dashboard, Фаза 6 (Cron + Telegram + Backups) — ФИНАЛ MVP

> Единый промт. Claude спланировал и отревьюил (3 плана verified, checker PASSED). Codex собирает локально (код+тесты), cron/pg_dump/Telegram — артефакты для VPS. Это последняя фаза MVP.

## Контекст

Подпроект `/Users/pro2kuror/Desktop/VibeCoding/belberry/sales/sales_command_center/`, ветка `feat/global-sales-dashboard`. Фазы 1-5 готовы. daily_runner.py уже оркестрирует collect→transform→(LLM изолированно)→render→write с already_done()/partial_llm_failure/argparse. Фаза 6 = обвязка: расписание, доставка ссылки, бэкапы. **Пайплайн НЕ переписывать.**

Планы (читай с диска, `.planning/` gitignored):
- `.planning/phases/06-cron-telegram-backups/06-01-PLAN.md` (волна 1) — `notify.py`: Telegram `send_report_link` (ссылка на `/day/<date>`) + `send_alert`, fire-and-forget, html.escape, токены из env, маскирование. → DLV-02/03.
- `.planning/phases/06-cron-telegram-backups/06-03-PLAN.md` (волна 1) — `scripts/run_daily.sh` (flock + TZ МСК), `scripts/backup_postgres.sh` (pg_dump + ротация find -mtime), `scripts/crontab.scc` (`0 9 * * 1-5` + бэкап), README. → DLV-01/03.
- `.planning/phases/06-cron-telegram-backups/06-02-PLAN.md` (волна 2) — `lock.py` single_instance (fcntl.flock) + `daily_runner.cron_entry` (ссылка на успех, alert на partial/исключение). → DLV-01/02/03.

Волна 1 (06-01, 06-03) — параллельно. Исполняй по `read_first`/`action`/`acceptance_criteria`.

## Git

Ветка `feat/global-sales-dashboard`, коммить ТОЛЬКО `belberry/sales/sales_command_center/**` поимённо, атомарными коммитами по планам (`feat(gsd)/test(gsd)/chore(gsd)`), trailer Co-Authored-By: Codex. Не пушить/мёржить.

**ВАЖНО — сначала закоммить 2 незакоммиченных фикса Фазы 5** (ревью Claude нашло баг навигации календаря, я поправил):
- `web/src/components/ui/calendar.tsx` — навигация месяцев (react-day-picker v10: `months` сделан relative, `nav` — полоса по верху; кнопки ‹ › теперь на месте, листание работает).
- `web/src/components/CalendarView.tsx` — календарь открывается на месяце последнего отчёта (видеть свежее первым).
Оформи их коммитом `fix(gsd): calendar month navigation + open on latest report month` перед Фазой 6. (Тесты Фазы 5 — 46 — не затронуты.)

## Среда и стек

- Python stdlib (urllib для Telegram — без сторонних http-либ). Сеть онлайн.
- **Реальные cron-install / pg_dump / живой Telegram — НЕ в тестах и НЕ локально**, это на VPS (Codex деплоит). Локально: код + pytest на моках.
- Тесты pytest: notify (URL `/day/<date>`, html.escape, fire-and-forget при HTTP-ошибке, маскирование токена — инъекция http_post), lock (второй инстанс не стартует при удержании — на временном файле), cron_entry (ссылка на успех, alert при partial/исключении — инъекция notify/lock спаями). Shell-скрипты — статически (`bash -n` + grep на cron-строку/TZ/ротацию). **Сохранить существующие 5 тестов test_runner + 53 теста суммарно зелёными.**

## Жёсткие рамки (СТОП-условия)

- Только **Фаза 6** — завершает MVP. НЕ дашборды (DASH — v2). Пайплайн Фаз 2-3 не трогать.
- cron `0 9 * * 1-5` с `TZ=Europe/Moscow`; защита от параллельного запуска — flock (и в shell-обёртке, и python single_instance на том же lock-пути; двойная защита ок).
- notify: ссылка `{SCC_BASE_URL}/day/<date>`, fire-and-forget (сбой Telegram НЕ валит прогон), токены/chat_id только из env (SCC_TELEGRAM_BOT_TOKEN, SCC_TELEGRAM_CHAT_ID, SCC_ALERT_CHAT_ID, SCC_BASE_URL), маскировать в логах, html.escape на динамике.
- pg_dump + ротация (хранить N дней, env BACKUP_KEEP_DAYS); алерт в Telegram при сбое ГЕНЕРАЦИИ (исключение/partial_llm_failure); сбой самого бэкапа — в cron-лог (так и задумано).
- shell: `set -euo pipefail`. Секреты не в репо/логах.
- При неоднозначности — стоп и спроси. После каждого плана — `SUMMARY.md`.

## Открытые значения (env, ставятся на VPS при деплое — не блокируют сборку)

`SCC_BASE_URL` (домен сервиса), `SCC_TELEGRAM_BOT_TOKEN` + `SCC_TELEGRAM_CHAT_ID` (чат менеджеров — возможно бот «Лев Петрович»), `SCC_ALERT_CHAT_ID`. В `.env.example` задокументировать.

## ВЫХОД (формат промта на ревью Claude)

```
# REVIEW — feat/global-sales-dashboard (Phase 6, ФИНАЛ MVP)
## КОНТЕКСТ — ветка @ <SHA>
## КОММИТЫ — список (вкл. fix календаря Фазы 5)
## ЧТО СОЗДАНО (по планам 06-01 / 06-02 / 06-03 + scripts)
## ТЕСТЫ — pytest → N passed (notify/lock/cron_entry + прежние 53); shell bash -n OK; мок Telegram/flock
## ПОКРЫТИЕ — DLV-01..03 где закрыто
## ПРОВЕРКИ — cron 0 9 * * 1-5 TZ МСК; double-flock; ссылка /day fire-and-forget; токены env+маска+html.escape; pg_dump+ротация; alert при сбое генерации
## ЧТО НЕ ЗАПУСКАЛОСЬ — реальный cron/pg_dump/Telegram (VPS)
## ОТКРЫТЫЕ ВОПРОСЫ / РИСКИ — env-значения для деплоя (chat_id, base_url, token)
## git log -<N>
## ИТОГ: MVP (Фазы 1-6) собран — что нужно для деплоя на VPS
```
