# Wave 4 Execution Report

Дата фиксации: 2026-04-28 МСК.

Статус: completed for approved test-layout moves.

## 1. Выполненные moves

```text
tests/test_search_provider.py -> tests/unit/test_search_provider.py
tests/test_bitrix_app_auth.py -> tests/unit/test_bitrix_app_auth.py
tests/test_bitrix_sales_adapter.py -> tests/unit/test_bitrix_sales_adapter.py
```

## 2. Созданные документы

```text
docs/migration/wave4/test_layout_contract.md
docs/migration/wave5/production_candidate_gate.md
docs/migration/sales_lev/sales_agent_retirement_assessment.md
```

## 3. Проверки после каждого шага

### Step 1

```bash
python3 -m unittest discover -s tests/unit -p 'test_search_provider.py'
```

Результат:

```text
Ran 3 tests
OK
```

### Step 2

```bash
python3 -m unittest discover -s tests/unit -p 'test_bitrix_app_auth.py'
```

Результат:

```text
Ran 6 tests
OK
```

### Step 3

```bash
python3 -m unittest discover -s tests/unit -p 'test_bitrix_sales_adapter.py'
```

Результат:

```text
Ran 3 tests
OK
```

### Step 4

```bash
python3 -m unittest discover -s tests/unit
```

Результат:

```text
Ran 12 tests
OK
```

### Step 5

```bash
python3 -m unittest discover -s tests/unit
```

Результат:

```text
Ran 12 tests
OK
```

## 4. Что не менялось

Не менялись:

- production code;
- imports в `agents/*`;
- imports в `cloudbot/*`;
- `agents/sales_agent`;
- `scripts/run_sales_copilot.py`;
- `configs/*`;
- `infra/*`;
- deploy/rollback/verify scripts;
- runtime/env/cron/systemd/docker;
- `/opt/*`, `/etc/*`, `/root/*`, `/home/ops/*`.

## 5. Итог

```text
Wave 4 test-layout migration completed
Wave 5 production code move remains blocked
```
