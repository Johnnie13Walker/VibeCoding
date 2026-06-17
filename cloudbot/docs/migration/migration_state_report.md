# Migration State Report

Дата фиксации: 2026-04-28 МСК.

Статус: current migration state after Wave 4/Wave 5 controlled structural moves.

## 1. Completed structural moves

### Wave 4: tests layout

Перенесено:

```text
tests/test_search_provider.py -> tests/unit/test_search_provider.py
tests/test_bitrix_app_auth.py -> tests/unit/test_bitrix_app_auth.py
tests/test_bitrix_sales_adapter.py -> tests/unit/test_bitrix_sales_adapter.py
```

Проверка:

```text
python3 -m unittest discover -s tests/unit
Ran 12 tests
OK
```

### Wave 5: config env examples

Перенесено:

```text
configs/app_config.env.example -> config/env/examples/app_config.env.example
configs/integrations.env.example -> config/env/examples/integrations.env.example
```

Проверка:

```text
secret-like patterns: no matches
python3 -m unittest discover -s tests/unit
Ran 12 tests
OK
```

## 2. Completed documents

Wave 4:

```text
docs/migration/wave4/test_layout_contract.md
docs/migration/wave4/wave4_execution_report.md
```

Wave 5:

```text
docs/migration/wave5/app_config_example_review.md
docs/migration/wave5/integrations_example_review.md
docs/migration/wave5/config_examples_execution_report.md
docs/migration/wave5/env_examples_contract.md
docs/migration/wave5/schedule_contract_review.md
docs/migration/wave5/schedule_contract_gate.md
docs/migration/wave5/schedules_cron_review.md
docs/migration/wave5/cron_template_gate.md
```

Wave 6:

```text
docs/migration/wave6/wave6_gate.md
```

## 3. Blocked zones

Still blocked:

```text
production code move
runtime move
live env move
cron/systemd/docker changes
deploy/rollback/verify scripts
agents/sales_agent retirement
shared-core move
schedule_contract.env move
schedules.cron move
```

## 4. No-touch confirmations

Не менялись в рамках этих шагов:

- `agents/*`;
- `cloudbot/*`;
- `scripts/run_sales_copilot.py`;
- `configs/schedule_contract.env`;
- `configs/schedules.cron`;
- live env;
- runtime pointers;
- cron/systemd/docker;
- deploy/rollback/verify scripts;
- `/opt/*`, `/etc/*`, `/root/*`, `/home/ops/*`.

Примечание: `configs/schedule_contract.env` и `configs/schedules.cron` уже находятся в dirty state, но текущие шаги их не редактировали.

## 5. Current successful test command

```bash
python3 -m unittest discover -s tests/unit
```

Expected:

```text
Ran 12 tests
OK
```

## 6. Next recommended move

Следующий безопасный шаг:

```text
docs/migration/sales_lev/sales_lev_dependency_map.md
```

Тип:

```text
read-only dependency map
```

Цель:

- понять реальные зависимости `agents/sales_agent`;
- подтвердить связи `agents/lev_petrovich`;
- подтвердить bridge через `scripts/run_sales_copilot.py`;
- не выполнять retirement;
- не менять imports;
- не трогать runtime.

## 7. Final verdict

```text
Wave 4 test-layout migration completed
Wave 5 config examples migration completed
Wave 6 ready for dependency-map planning only
production code move still blocked
```
