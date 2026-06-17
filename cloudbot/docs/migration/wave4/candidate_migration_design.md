# Candidate Migration Design: W4-FIRST-TEST-01

Дата фиксации: 2026-04-28 МСК.

Статус: design executed after owner approval. Этот документ не менял production code, imports, runtime/env/cron/systemd/docker и не разрешал deploy.

Execution result на 2026-04-28 МСК:

```text
W4-FIRST-TEST-01 completed
tests/test_search_provider.py -> tests/unit/test_search_provider.py
```

## 1. Выбранный кандидат

```text
candidate_id:
W4-FIRST-TEST-01

current path:
tests/test_search_provider.py

target path:
tests/unit/test_search_provider.py
```

Тип move:

```text
single test-file structural move
```

Это не production code move.

## 2. Цель

Цель будущего move - проверить минимальный controlled structural migration loop на одном изолированном unit-test файле.

Ожидаемый результат после будущего approved move:

- test файл находится в `tests/unit/`;
- тест продолжает проходить;
- production imports не меняются;
- runtime, env, cron, systemd, docker и deploy scripts не меняются;
- `agents/sales_agent` не затронут;
- rollback остается локальным и простым.

## 3. Текущий baseline

Baseline test уже выполнен до создания этого design.

Команда:

```bash
python3 -m unittest tests.test_search_provider
```

Результат:

```text
Ran 3 tests in 0.001s
OK
```

Git tracking status:

```bash
git ls-files tests/test_search_provider.py tests/unit/README.md docs/migration/wave4/wave4_candidate_selection.md
```

Результат: пустой вывод.

Вывод:

- `tests/test_search_provider.py` сейчас untracked;
- `tests/unit/README.md` сейчас untracked;
- `docs/migration/wave4/*` сейчас untracked;
- сам move нельзя выполнять, пока владелец явно не примет этот untracked scope как допустимый baseline.

## 4. Точный список файлов будущего move

Разрешенный список для будущего execution:

```text
tests/test_search_provider.py
tests/unit/test_search_provider.py
```

Файлы, которые можно видеть в status, но нельзя менять как часть move:

```text
tests/unit/README.md
docs/migration/wave4/wave4_gate.md
docs/migration/wave4/import_compatibility_plan.md
docs/migration/wave4/wave4_candidate_selection.md
docs/migration/wave4/candidate_migration_design.md
```

Любой другой измененный файл означает scope breach.

## 5. Запрещенные изменения

В рамках будущего `W4-FIRST-TEST-01` запрещено:

- менять содержимое теста;
- менять production code;
- менять imports в `agents/*`;
- менять imports в `cloudbot/*`;
- менять `cloudbot/providers/search_provider.py`;
- менять `agents/sales_agent`;
- перемещать, удалять или retire `agents/sales_agent`;
- менять `agents/lev_petrovich/*`;
- менять `agents/larisa_ivanovna/*`;
- менять `scripts/run_sales_copilot.py`;
- менять `report_contract.py`;
- менять `configs/*`;
- менять `infra/*`;
- менять deploy/rollback/verify scripts;
- создавать `__init__.py`;
- создавать package shims;
- создавать symlinks;
- создавать env files;
- трогать `/opt/*`, `/etc/*`, `/root/*`, `/home/ops/*`;
- менять runtime pointers;
- менять cron/systemd/docker;
- запускать deploy или restart.

## 6. Compatibility design

Для этого кандидата compatibility requirement минимальный:

```python
from cloudbot.providers import search_provider
```

Этот import должен остаться без изменений.

Не требуется:

- import rewrite;
- shim;
- wrapper;
- package alias;
- изменение `PYTHONPATH`;
- изменение test package structure;
- изменение production code.

Фактическая проверка после будущего move должна запускать тест через discovery по новой директории:

```bash
python3 -m unittest discover -s tests/unit -p 'test_search_provider.py'
```

## 7. Preconditions для выполнения move

Перед future execution должны быть выполнены все условия:

| Check | Requirement | Status | Blocker |
| --- | --- | --- | --- |
| W4-DESIGN-01 | Owner подтвердил, что `tests/test_search_provider.py` можно принять как baseline несмотря на untracked status | not confirmed | yes |
| W4-DESIGN-02 | Owner подтвердил выполнение именно `W4-FIRST-TEST-01` | not confirmed | yes |
| W4-DESIGN-03 | Baseline test проходит до move | pass | no |
| W4-DESIGN-04 | `tests/unit` существует | pass | no |
| W4-DESIGN-05 | Runtime/env/cron/systemd/docker остаются no-touch | pass | no |
| W4-DESIGN-06 | `agents/sales_agent` остается no-touch | pass | no |
| W4-DESIGN-07 | Нет разрешения на любые другие moves | pass | no |

Итог: future execution пока blocked до owner approval по W4-DESIGN-01 и W4-DESIGN-02.

## 8. Execution outline для будущего approved move

Не выполнять сейчас.

Будущий approved move должен быть только:

```text
move tests/test_search_provider.py to tests/unit/test_search_provider.py
```

Допустимый механический эффект:

```text
D tests/test_search_provider.py
?? tests/unit/test_search_provider.py
```

Недопустимый эффект:

```text
M agents/*
M cloudbot/*
M configs/*
M infra/*
M scripts/run_sales_copilot.py
M report_contract.py
```

## 9. Verification plan после будущего move

После future execution обязательно выполнить:

```bash
git status --short tests/test_search_provider.py tests/unit/test_search_provider.py tests/unit/README.md
python3 -m unittest discover -s tests/unit -p 'test_search_provider.py'
rg -n "from cloudbot.providers import search_provider" tests/unit/test_search_provider.py
git status --short agents cloudbot configs infra scripts/run_sales_copilot.py
```

Успешная проверка означает:

- test discovery по `tests/unit` проходит;
- import в тесте сохранен;
- production code не изменен;
- runtime-related зоны не изменены;
- нет изменений в `agents/sales_agent`;
- нет изменений в `cloudbot/providers/search_provider.py`.

Если любой пункт не выполнен, move считается failed.

## 10. Rollback plan

Rollback должен быть локальным:

```text
tests/unit/test_search_provider.py -> tests/test_search_provider.py
```

После rollback нужно выполнить:

```bash
python3 -m unittest tests.test_search_provider
git status --short tests/test_search_provider.py tests/unit/test_search_provider.py
```

Rollback успешен, если:

- старый test path снова существует;
- baseline test снова проходит;
- `tests/unit/test_search_provider.py` отсутствует;
- production/runtime зоны не изменены.

Rollback не должен требовать:

- server access;
- deploy;
- restart;
- runtime pointer changes;
- env changes;
- cron/systemd/docker changes.

## 11. Decision required before execution

Перед фактическим move владелец должен явно подтвердить:

```text
APPROVE W4-FIRST-TEST-01
Accept current untracked tests/test_search_provider.py as migration baseline.
Move only tests/test_search_provider.py to tests/unit/test_search_provider.py.
No code logic changes.
No imports changes.
No runtime/deploy/env changes.
```

Без этого подтверждения migration остается blocked.

## 12. Финальный статус

`candidate_migration_design.md` создан.

Фактический move:

```text
completed after owner approval
```

Следующий шаг:

```text
continue with test layout migration only after successful checks
```
