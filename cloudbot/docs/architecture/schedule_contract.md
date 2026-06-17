# Контракт Расписаний Cloudbot/OpenClaw

Канонический исполняемый источник: `configs/schedule_contract.env`.

Этот файл нужен, чтобы:
- не держать разные hardcode в `larisa`, `sales`, `OpenClaw jobs` и server-only cron;
- иметь один контракт для inspect/apply workflow;
- сверять live server state с repo до deploy и после repair.

## Active контуры

### Лариса Ивановна
- daily brief: `08:00 MSK`
- evening review: `19:00 MSK` только если явно включён

### OpenClaw jobs
- healthcheck: `09:00 MSK`, внутренний upstream-check без пользовательской доставки
- daily status: `09:30 MSK`, единственный публичный утренний operational-отчёт

### Sales
- daily brief: `09:30 MSK` по рабочим дням
- morning check: `09:40 MSK` по рабочим дням
- followup: `17:00 MSK`
- weekly review: `18:30 MSK` по пятницам

### WHOOP
- morning report: `08:01 MSK`

### Todo-integration
- morning digest: отключён после cutover на Ларису
- midday digest: отключён после cutover на Ларису
- evening digest: отключается через `TODO_DIGEST_EVENING_ENABLED=0`; при явном включении слот `19:00 MSK`
- reminders tick: каждую минуту
- execution tick: каждые 15 минут

## Правило изменений

Любое изменение расписания сначала делается в `configs/schedule_contract.env`, затем:
1. обновляются apply/inspect workflow;
2. выполняется проверка на сервере;
3. только после успешной верификации считается, что контракт изменён.
