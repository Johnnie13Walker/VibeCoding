# Wave 4 Candidate Selection

Дата фиксации: 2026-04-28 МСК.

Статус: selection only. Этот документ не выполняет migration, не меняет imports, не переносит файлы и не разрешает runtime/deploy/env изменения.

## 1. Решение

Первым кандидатом для будущего минимального structural move выбирается:

```text
W4-FIRST-TEST-01
tests/test_search_provider.py -> tests/unit/test_search_provider.py
```

Это не production code move. Это перенос одного изолированного unit-test файла в уже созданный target test skeleton.

## 2. Почему выбран именно этот кандидат

`tests/test_search_provider.py` выбран как самый безопасный первый structural candidate, потому что:

- не находится в `agents/*`;
- не находится в `cloudbot/*`;
- не меняет shared-core behavior;
- не требует изменения runtime imports;
- не зависит от live env/server/secrets;
- использует `unittest` и mock через `patch.object`;
- проверяет текущий `cloudbot.providers.search_provider` без реального HTTP-вызова;
- позволяет проверить механику migration через test discovery без риска для Telegram, Larisa, Lev/Sales или runtime.

Цель этого кандидата - не перенести бизнес-логику, а подтвердить безопасный migration loop:

1. выбран ровно один файл;
2. есть точный current path;
3. есть точный target path;
4. есть проверка до и после;
5. есть простой rollback;
6. нет runtime blast radius.

## 3. Почему другие кандидаты не выбраны первыми

| Candidate | Почему не первый |
| --- | --- |
| `agents/larisa_ivanovna/* -> apps/larisa_ivanovna/*` | Высокий риск: `cloudbot/workflows/larisa_runtime.py` зависит от старых import paths |
| `agents/lev_petrovich/* -> apps/lev_petrovich/*` | Высокий риск: связан с `agents/sales_agent`, `scripts/run_sales_copilot.py`, report contract и Sales runtime |
| `agents/sales_agent/* -> apps/lev_petrovich/legacy_sales_agent/*` | Запрещено сейчас: `agents/sales_agent` остается active temporary compatibility layer |
| `cloudbot/providers/* -> shared/providers/*` | Shared-core move с большим blast radius |
| `configs/* -> config/env/examples|schemas` | Риск confusion между examples и live config/env контрактами |
| Массовый перенос `tests/*` | Слишком широкий scope для первого move |

## 4. Exact scope будущего move

Разрешаемый будущий scope только после отдельного owner approval:

```text
current path:
tests/test_search_provider.py

target path:
tests/unit/test_search_provider.py
```

Потенциально изменяемые файлы:

```text
tests/test_search_provider.py
tests/unit/test_search_provider.py
```

Никакие другие файлы не должны изменяться в рамках этого move.

## 5. Anti-scope

В рамках будущего `W4-FIRST-TEST-01` категорически нельзя:

- менять production code;
- менять imports в `agents/*`;
- менять imports в `cloudbot/*`;
- менять `agents/sales_agent`;
- retire или move `agents/sales_agent`;
- менять `agents/lev_petrovich/*`;
- менять `agents/larisa_ivanovna/*`;
- менять `scripts/run_sales_copilot.py`;
- менять `report_contract.py`;
- менять `configs/*`;
- менять `infra/*`;
- менять deploy/rollback/verify scripts;
- создавать runtime scripts;
- создавать env files;
- трогать `/opt/*`, `/etc/*`, `/root/*`, `/home/ops/*`;
- менять runtime pointers;
- менять cron/systemd/docker;
- включать finance/iOS/HAPP/VPN/subscription/server-only integrations;
- переносить больше одного test-файла;
- переписывать test logic.

## 6. Compatibility requirements

Для этого кандидата compatibility strategy простая:

1. Production import paths не меняются.
2. `cloudbot.providers.search_provider` остается на текущем active path.
3. Test import остается:

```python
from cloudbot.providers import search_provider
```

4. Старый test discovery должен быть заменен явной проверкой нового path.
5. Нельзя добавлять `__init__.py` или package files без отдельного approval.

## 7. Проверки до выполнения move

Перед будущим переносом нужно выполнить:

```bash
git status --short tests/test_search_provider.py tests/unit
python3 -m unittest tests.test_search_provider
```

Условие перехода к переносу:

- baseline test проходит;
- файл существует в старом path;
- target directory `tests/unit` существует;
- нет неожиданных изменений в `agents/*`, `cloudbot/*`, `configs/*`, `infra/*`;
- owner явно подтвердил выполнение `W4-FIRST-TEST-01`.

## 8. Проверки после будущего move

После будущего переноса нужно выполнить:

```bash
git status --short tests
python3 -m unittest discover -s tests/unit -p 'test_search_provider.py'
rg -n "from cloudbot.providers import search_provider" tests/unit/test_search_provider.py
```

Критерий успеха:

- новый test path существует;
- старый файл отсутствует только как результат approved move;
- unit-test проходит из нового расположения;
- import в тесте не изменил production behavior;
- `agents/*`, `cloudbot/*`, `configs/*`, `infra/*`, runtime/env/cron/systemd/docker не изменены.

## 9. Rollback

Rollback должен быть простым и локальным:

```text
tests/unit/test_search_provider.py -> tests/test_search_provider.py
```

Rollback не должен требовать:

- server access;
- deploy;
- restart;
- runtime pointer changes;
- env changes;
- cron/systemd/docker changes.

Если после переноса test discovery не проходит, move считается неуспешным и должен быть откатан до старого path.

## 10. Gate status

| Check | Requirement | Status | Blocker for move |
| --- | --- | --- | --- |
| W4-SEL-01 | Выбран ровно один candidate | pass | no |
| W4-SEL-02 | Candidate не затрагивает production code | pass | no |
| W4-SEL-03 | Candidate не затрагивает runtime/env/cron/systemd/docker | pass | no |
| W4-SEL-04 | Candidate не затрагивает `agents/sales_agent` | pass | no |
| W4-SEL-05 | Baseline test проходит до move | pass | no |
| W4-SEL-06 | Owner approval на выполнение move получен | not confirmed | yes |
| W4-SEL-07 | Candidate migration design создан | not confirmed | yes |
| W4-SEL-08 | Source test file принят в baseline/tracking scope | not confirmed | yes |

## 11. Baseline verification results

Проверка выполнена 2026-04-28 МСК.

Baseline test:

```bash
python3 -m unittest tests.test_search_provider
```

Результат:

```text
Ran 3 tests in 0.001s
OK
```

Git tracking check:

```bash
git ls-files tests/test_search_provider.py tests/unit/README.md docs/migration/wave4/wave4_candidate_selection.md
```

Результат: пустой вывод.

Вывод:

- `tests/test_search_provider.py` сейчас untracked;
- `tests/unit/README.md` сейчас untracked;
- `docs/migration/wave4/wave4_candidate_selection.md` сейчас untracked;
- перед реальным move нужно явно принять `tests/test_search_provider.py` в baseline/tracking scope или выбрать другой tracked candidate.

Это не блокирует подготовку `candidate_migration_design.md`, но блокирует сам перенос до owner decision.

## 12. Следующий шаг

Следующий безопасный шаг:

```text
docs/migration/wave4/candidate_migration_design.md
```

Этот design должен подтвердить:

- точный список файлов;
- точные команды проверки;
- baseline test result;
- rollback;
- что `W4-FIRST-TEST-01` остается единственным разрешенным move.

До этого перенос `tests/test_search_provider.py` не выполнять.
