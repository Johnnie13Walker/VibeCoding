# WHOOP contour

Локальный source-of-truth для WHOOP-контуров после переноса из старых папок Desktop.

## Что здесь лежит

- `scripts/whoop_telegram_report.py` — актуальный source активного VPS-скрипта `/usr/local/bin/send_whoop_report.py`.
- `scripts/progress_tracker_whoop.py` — standalone progress tracker.
- `ops/` — вспомогательные server-check/repair scripts из старого `OpenClo/projects/engineer`.
- `legacy/openclaw-extensions/` — старые JS-прототипы WHOOP-интеграции, только для reference.
- `server-snapshots/` — исторический snapshot live server за `2026-03-25`, не основной source.
- `docs/` — контекстные заметки по live contour.

Секреты, токены, sqlite/state и `.venv` не перенесены. Runtime-секреты держать вне repo, например в `/Users/pro2kuror/.config/vibecoding/whoop/` или на VPS в `/etc/openclaw/whoop.env`.

## WHOOP Progress Tracker (10 000/day logic)

Этот модуль переделывает трекинг «10 000/день» на WHOOP API с сохранением логики пингов, прогноза и мотивации.

## Диагностика API (обязательный результат)
Проверено по WHOOP OpenAPI specification (`/developer/doc/openapi.json`):
- поля/эндпоинты `steps`, `step_count`, `distance_walked` **в официальной спецификации не найдены**;
- для выбранной дневной метрики используется scope `read:cycles`.

## Что изменилось (важно)
Так как steps недоступны официально в WHOOP Developer API, реализован вариант **A (только WHOOP)**:
- метрика прогресса дня: `kilojoule` из `cycle.score.kilojoule`;
- цель по умолчанию: `PROGRESS_GOAL_DEFAULT=10000` (настраивается);
- вся логика прогнозов/пингов сохранена.

## Архитектура
- OAuth2 WHOOP: `auth-url` -> `exchange-code` -> auto-refresh;
- хранилище: SQLite;
- таблицы: `daily_state`, `samples`, `settings`, `tokens` (+ `notifications` для дедупликации);
- scheduler: командой `run-scheduler` (под cron/systemd).

## Команды
- `progress_status` — статус и прогноз сейчас
- `progress_goal <число>` — изменить цель
- `progress_pause` / `progress_resume` — выключить/включить пинги
- `progress_insights` — аналитика за 7/14 дней + weekday/weekend
- `run-scheduler` — обязательные/умные пинги
- `diagnose-steps` — диагностика доступности шагов в WHOOP OpenAPI

## Прогноз и профили
- A) Линейная модель по темпу с 06:00 до 23:59
- B) Профильная модель по истории (окно 21 день, минимум 7)
- Итог:
  - если профиль надёжен: `0.7*profile + 0.3*linear`
  - иначе: `linear`

### Weekend mode
- история делится на `weekday` (Пн-Пт) и `weekend` (Сб-Вс);
- строятся 2 профиля доли прогресса по часам: `weekday_profile`, `weekend_profile`;
- fallback:
  - если weekend-данных < 4 дней -> общий профиль `all`;
  - если weekday-данных < 5 дней -> общий профиль `all`.

### Auto-adaptation
- профили пересчитываются ежедневно (при первом запуске нового дня и поздним вечером после 23:50);
- агрегирование по часам: медиана;
- сглаживание: `share[h] = 0.25*prev + 0.5*current + 0.25*next`.

### Auto-weekend
- в будний день сравнивается отклонение текущего ритма от weekday/weekend профилей;
- если weekend отклоняется меньше минимум на 30%, включается профиль `auto-weekend`.

## Пинги
- обязательные: 10:00, 15:00, 20:00 (Europe/Moscow)
- доп.пинги:
  - 12:00: если <20% цели
  - 17:00: если прогноз <100%
  - после 21:30: если осталось <=15%
- антиспам: не более `PROGRESS_MAX_PINGS_PER_DAY` (по умолчанию 6)
- для прод рекомендуется polling каждые 10 минут (scheduler сам решает, слать пинг или нет)

Пример cron (Europe/Moscow):
```cron
*/10 * * * * cd /Users/pro2kuror/Desktop/VibeCoding/personal/whoop && /usr/bin/python3 /Users/pro2kuror/Desktop/VibeCoding/personal/whoop/scripts/progress_tracker_whoop.py run-scheduler >> /Users/pro2kuror/.config/vibecoding/whoop/progress_scheduler.log 2>&1
```

## Запуск OAuth
1. Ссылка авторизации:
```bash
python3 /Users/pro2kuror/Desktop/VibeCoding/personal/whoop/scripts/progress_tracker_whoop.py auth-url
```
2. После `GRANT` взять `code` из redirect URL.
3. Обменять на токены:
```bash
python3 /Users/pro2kuror/Desktop/VibeCoding/personal/whoop/scripts/progress_tracker_whoop.py exchange-code "<CODE>"
```

## Selftest
```bash
cd /Users/pro2kuror/Desktop/VibeCoding/personal/whoop
npm run selftest
```
Selftest проверяет:
- конфиг OAuth,
- 1 запрос к WHOOP,
- симуляцию 3 сообщений (10:00/15:00/20:00),
- weekend/weekday/auto-weekend на синтетической истории,
- диагностику steps в OpenAPI.

Проверка weekend mode вручную:
```bash
python3 /Users/pro2kuror/Desktop/VibeCoding/personal/whoop/scripts/progress_tracker_whoop.py progress_insights
```
В выводе должны быть:
- средние/закрытие цели отдельно по будням и выходным;
- пиковые окна отдельно для weekday/weekend;
- строка `Текущий профиль: weekday|weekend|auto-weekend|all`.

## Примеры сообщений
- 10:00: «утренний прогресс, прогноз к 23:59, план»
- 15:00: «дневной прогресс, сколько осталось, прогноз»
- 20:00: «вечерний дожимающий план»

## Вариант B (если нужен именно шагомер)
Если нужно оставить цель строго в шагах 10 000, steps надо брать из другого источника (Apple Health / Google Fit), а WHOOP использовать как доп.метрики.
