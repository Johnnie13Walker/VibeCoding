# Finance Google tools decision — 2026-04-29 МСК

## Статус

`scripts/finansist_*.mjs` остаются вне finance core и вне safe migration baseline.

Причина: эти scripts работают с Google Sheets API и требуют отдельного контракта безопасности.

## Read-only candidates

Эти файлы приняты как read-only tooling candidates после локальной проверки:

- `apps/finansist/tools/analyze_employee_names.mjs`
- `apps/finansist/tools/google_read_ranges.mjs`
- `apps/finansist/tools/google_sheet_inspect.mjs`

Compatibility wrappers remain at:

- `scripts/finansist_analyze_employee_names.mjs`
- `scripts/finansist_google_read_ranges.mjs`
- `scripts/finansist_google_sheet_inspect.mjs`

Подтверждено:

- `finansist_analyze_employee_names.mjs` использует scope `https://www.googleapis.com/auth/spreadsheets.readonly`.
- `finansist_google_read_ranges.mjs` использует scope `https://www.googleapis.com/auth/spreadsheets.readonly`.
- `finansist_google_sheet_inspect.mjs` использует scope `https://www.googleapis.com/auth/spreadsheets.readonly`.
- локальный syntax check проходит.
- write endpoints Sheets API в этих трёх файлах не найдены.

Не подтверждено:

- безопасный runtime credentials contract;
- отсутствие записи во внешние таблицы при всех режимах запуска;
- пригодность для CI без live secrets.

## Write/build candidates

Эти файлы нельзя принимать без отдельного owner approval, потому что они используют Google Sheets write operations:

- `scripts/finansist_build_employee_dictionary.mjs`
- `scripts/finansist_build_fot_analytics.mjs`
- `scripts/finansist_build_fot_demo.mjs`
- `scripts/finansist_build_fot_dynamics.mjs`
- `scripts/finansist_build_fot_salary_articles.mjs`
- `scripts/finansist_build_opiu_from_dds.mjs`
- `scripts/finansist_build_opiu_two_tabs.mjs`
- `scripts/finansist_update_employee_department.mjs`
- `scripts/finansist_update_employee_name.mjs`

Найденные признаки write behavior:

- `spreadsheets:batchUpdate`
- `spreadsheets.values:batchUpdate`
- `valueInputOption=USER_ENTERED`

## Проверки, выполненные локально

- `node --check scripts/finansist_*.mjs` — синтаксис проходит.
- грубый secret scan по assignment-паттернам — явных секретов не найдено.

Эти проверки не являются live Google approval.

## Решение

Read-only subset можно принять отдельным commit без запуска live Google API.

Write/build subset не stage и не commit в текущую migration line.

Write/build subset оставлен как local/pending tooling и добавлен в `.gitignore`, чтобы не попасть в git случайно. Файлы не удалены.

Следующий допустимый шаг:

1. принять read-only subset отдельным commit;
2. для write/build subset создать отдельный finance-tools branch или удалить/архивировать после явного owner decision;
3. не смешивать read-only subset с write/build subset.

## Local pending files ignored by git

- `scripts/finansist_build_employee_dictionary.mjs`
- `scripts/finansist_build_fot_analytics.mjs`
- `scripts/finansist_build_fot_demo.mjs`
- `scripts/finansist_build_fot_dynamics.mjs`
- `scripts/finansist_build_fot_salary_articles.mjs`
- `scripts/finansist_build_opiu_from_dds.mjs`
- `scripts/finansist_build_opiu_two_tabs.mjs`
- `scripts/finansist_update_employee_department.mjs`
- `scripts/finansist_update_employee_name.mjs`

## Запрет

Не запускать write/build scripts против live Google Sheets без отдельного owner approval.
