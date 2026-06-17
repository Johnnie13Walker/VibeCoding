# Test Migration Backlog

Дата фиксации: 2026-04-28 МСК.

Статус: backlog only. Этот документ не переносит тесты.

## 1. Already migrated

```text
tests/unit/test_search_provider.py
tests/unit/test_bitrix_app_auth.py
tests/unit/test_bitrix_sales_adapter.py
```

Verification:

```text
python3 -m unittest discover -s tests/unit
Ran 12 tests
OK
```

## 2. Remaining tests

| Test | Suggested class | Decision |
| --- | --- | --- |
| `tests/test_larisa_agent.py` | integration / agent runtime | review before move |
| `tests/test_larisa_search.py` | integration / search workflow | review before move |
| `tests/test_lev_petrovich_runtime.py` | integration / Sales runtime | review before move |
| `tests/test_sales_dispatch_contract.py` | integration / Sales contract | review before move |
| `tests/test_system_health.py` | integration / devops health | review before move |
| `tests/unit/test_finansist_agent.py` | excluded finance contour | separate track |

## 3. Rules

Move only one test at a time.

Before each move:

```bash
python3 -m unittest <old_test_module>
```

After each move:

```bash
python3 -m unittest discover -s <target_dir> -p '<file>'
python3 -m unittest discover -s tests/unit
```

## 4. Blocked tests

Do not move without separate owner approval:

```text
tests/test_lev_petrovich_runtime.py
tests/test_larisa_agent.py
tests/unit/test_finansist_agent.py
```

## 5. Verdict

```text
test backlog documented
no additional test move approved
```
