# CODEX — деплой редизайна платформы (Фаза 1) на прод

> LIVE-ПРОД, **лёгкая выкатка фронта**. Сервер Global Sales Dashboard уже работает
> (Hetzner 178.104.222.163, `/opt/scc/VibeCoding`, PM2 `scc-web`, nginx+TLS). Деплоим
> ТОЛЬКО изменения веба — фирстиль Belberry «Командный центр». Доступы и порядок —
> по `09-Projects/belberry-global-sales-dashboard/AI-AGENTS-SETUP.md` (vault).

## Что выкатываем
Коммиты на ветке `feat/global-sales-dashboard` поверх уже задеплоенного `e4d15f7`
(7 коммитов веба, вершина ~`4d46fdd`): тёмный индиго-сайдбар с логотипом, hero+aurora,
health-gauge, KPI с count-up/Δ/спарклайнами, бренд-воронка, встроенный отчёт дня
(iframe + тулбар), «Открыть последний отчёт», формат Δ, свежесть, мобайл.

**Объём — только `web/` (Next.js).** Проверено:
- Раннер (Python), БД, миграции, cron, Telegram — **НЕ менялись и НЕ трогаем**.
- Новых зависимостей нет (lucide-react уже в package.json). `npm install` — no-op/безопасен.
- Отчёт дня встраивается через iframe на существующий `/day/[date]` (тот же origin,
  за nginx работает; печать — `iframe.contentWindow.print()`).

## Предусловие (пользователь)
Ветка запушена в origin (`git push origin feat/global-sales-dashboard`, вершина `4d46fdd`).

## ⛔ СТОП-УСЛОВИЯ
1. Деплой из `origin/feat/global-sales-dashboard`. НЕ merge в main, НЕ force-push.
2. **Не трогать**: раннер, БД/миграции, cron, Telegram, `/etc/scc/scc.env`.
3. Секреты не светить в логах/отчёте.
4. Если `npm run build` упрётся в память (4 ГБ) — добавь swap или
   `NODE_OPTIONS=--max-old-space-size=2048`, не убивай прод молча.
5. Сервис не должен открыться без сессии: любой маршрут без логина → 307 на /login.
6. При провале — откат (см. ВЫХОД): `git checkout e4d15f7` → rebuild → reload.

## ШАГИ (канонический web-deploy из runbook)
```bash
ssh -i ~/.ssh/temp_migration_key root@178.104.222.163
cd /opt/scc/VibeCoding
git fetch origin
git checkout feat/global-sales-dashboard
git pull --ff-only origin feat/global-sales-dashboard
git rev-parse --short HEAD          # ожидаем 4d46fdd (или новее)

cd belberry/sales/sales_command_center/web
npm install
npm test                            # ожидаем 57 passed (vitest, прод-данные не трогает)
npm run build                       # + postbuild prepare-standalone
pm2 reload scc-web
pm2 status scc-web
```
После reload первые ~3 сек возможен `502` — повторить smoke через паузу.

## SMOKE (обязательно)
1. **Auth-гейт** (без сессии → 307 /login):
```bash
for p in / /dashboard /daily /day/2026-06-02; do
  curl -s -o /dev/null -w "$p → %{http_code} %{redirect_url}\n" \
    "https://static.163.222.104.178.clients.your-server.de$p"
done
```
Ожидаем `/` → 307 на /dashboard ИЛИ /login; `/dashboard`,`/daily`,`/day/...` без сессии → 307 /login.

2. **CSS реально подгрузился** (редизайн — это весь смысл; проверяем, что стили на месте).
   Открой страницу логина (она доступна без сессии) и убедись, что подтянут
   `/_next/static/css/app/layout.css`, и он содержит брендовые классы:
```bash
BASE=https://static.163.222.104.178.clients.your-server.de
CSS=$(curl -s "$BASE/login" | grep -oE '/_next/static/css/[^"?]*\.css' | head -1)
curl -s "$BASE$CSS" | grep -o "bb-rail\|bb-hero\|bb-card\|bb-nav-item\|bb-rframe" | sort -u
```
Должны найтись `bb-card`, `bb-hero`, `bb-nav-item`, `bb-rail`, `bb-rframe`.
Если классов нет — стили не собрались, СТОП и разбор (не оставляй прод с голой версткой).

3. **Глазами под сессией** (владелец логинится кодом от Ларисы):
   - тёмный индиго-сайдбар с **логотипом Belberry** (белый), активная вкладка светится;
   - Dashboard: hero + health-gauge (число добегает), KPI count-up, бренд-воронка, команда;
   - «Дневной отчёт» → клик по дню (или «Открыть последний отчёт») → богатый разбор
     открывается **внутри платформы** в рамке с тулбаром (навигация дней, печать);
   - мобильная ширина: сайдбар → верхняя полоса, карточки в столбец.

## Что НЕ делаем
Раннер/cron/Telegram/БД не трогаем; плановая генерация отчётов идёт как была.
Деплой чисто фронтовый: новый билд + `pm2 reload`.

## ВЫХОД (отчёт в формате готового промта на ревью Claude)
```
# DEPLOY REPORT — редизайн платформы Фаза 1 (web)
## КОД — SHA до (e4d15f7) → после (4d46fdd), ветка feat/global-sales-dashboard
## СБОРКА — npm install (no-op?), npm test N passed, npm run build (память ок?), pm2 reload scc-web online
## SMOKE auth — / /dashboard /daily /day: коды (307→login без сессии) ✓/✗
## SMOKE css — классы bb-* найдены в layout.css ✓/✗
## SMOKE визуал — сайдбар+лого, gauge, KPI, встроенный отчёт, мобайл — что видно/не видно
## НЕ ТРОГАЛ — раннер, БД, cron, Telegram, scc.env
## РИСКИ / ОТКРЫТЫЕ ВОПРОСЫ — память при сборке, кэш браузера (hard-refresh), прочее
## ОТКАТ — git checkout e4d15f7 && (cd web && npm run build && pm2 reload scc-web)
```
