# Config / env / cron owner decision — 2026-04-29 МСК

## Статус

Принято как безопасный examples/contracts baseline.

Это не live cron, не live env и не runtime migration.

## Решения владельца

1. Канонический локальный путь для examples:

   `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`

2. Daily brief Ларисы:

   `08:00 МСК`

   Contract:

   `LARISA_DAILY_CRON_MSK="0 8 * * *"`

   UTC equivalent:

   `LARISA_DAILY_CRON_EXPR_UTC="0 5 * * *"`

3. `larisa_content_topics` в `19:30 МСК`:

   Не принимается как current truth.

   Статус: future candidate, blocked pending Larisa content/search feature review.

   Причина: это feature contour, а не безопасный schedule baseline.

## Что входит в baseline

- `.env.integrations.example` как example-only файл без секретов.
- `configs/README.md` как marker для config examples.
- `configs/schedule_contract.env` как локальный schedule contract.
- `configs/schedules.cron` как локальный cron example.
- `infra/remote-ops.env.example` как example-only файл для remote ops параметров.

## Что не разрешено этим решением

- менять live cron;
- менять live env;
- менять server runtime;
- включать `larisa_content_topics` в production schedule;
- переносить config в новую структуру без отдельного approval;
- добавлять секреты в git.

## Проверка перед commit

- `git diff --check`
- staged secret scan
- unit tests
- integration tests, если не требуют live env/server/secrets
