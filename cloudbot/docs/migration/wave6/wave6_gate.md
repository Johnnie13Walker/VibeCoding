# Wave 6 Gate

Дата фиксации: 2026-04-28 МСК.

Статус: gate only. Этот документ не выполняет Wave 6 migration.

## 1. Current migration state

Wave 4 completed:

```text
test layout migration
tests/unit verification OK
```

Wave 5 completed:

```text
config env examples migration
schedule/cron gates documented
```

## 2. What remains blocked

```text
production code move: blocked
runtime move: blocked
schedule/cron move: blocked
agents/sales_agent retirement: blocked
shared-core move: blocked
```

## 3. Why production code move is still blocked

Production code move remains blocked because:

- `agents/sales_agent` is still a temporary compatibility layer;
- Larisa runtime imports old paths;
- Lev/Sales depends on `agents.sales_agent.*`;
- `scripts/run_sales_copilot.py` depends on Sales/Lev compatibility;
- shared-core `cloudbot/*` has broad import surface;
- schedule/cron files are runtime-sensitive;
- no candidate-specific production smoke has been executed.

## 4. Wave 6 allowed scope

Allowed next work:

```text
dependency maps only
design-only documents
read-only import analysis
read-only runtime path analysis
smoke checklist refinement
```

Not allowed:

- production code moves;
- import rewrites;
- runtime/env/cron/systemd/docker changes;
- deploy;
- restart;
- `agents/sales_agent` retirement;
- shared-core move.

## 5. Recommended Wave 6 tracks

| Track | Artifact | Purpose |
| --- | --- | --- |
| Sales/Lev dependency map | `docs/migration/sales_lev/sales_lev_dependency_map.md` | Подтвердить реальные зависимости `agents/sales_agent`, `agents/lev_petrovich`, `scripts/run_sales_copilot.py` |
| Larisa dependency map | `docs/migration/larisa/larisa_dependency_map.md` | Подтвердить imports и runtime entrypoints Ларисы |
| Shared-core import map | `docs/migration/shared_core/shared_core_import_map.md` | Понять blast radius `cloudbot/orchestrator`, `providers`, `skills`, `workflows` |
| Schedule/cron dependency map | `docs/migration/schedules/schedule_runtime_dependency_map.md` | Отделить local schedule docs от runtime cron |

## 6. Gate checks before Wave 6 execution

Перед любым Wave 6 document track:

```bash
python3 -m unittest discover -s tests/unit
git status --short docs/migration config/env/examples configs tests/unit
```

Перед любым production candidate после Wave 6:

1. Candidate-specific import map.
2. Compatibility strategy.
3. Safe tests.
4. Smoke checklist.
5. Rollback plan.
6. Owner approval.

## 7. Verdict

```text
Wave 6 ready for dependency-map planning only
production code move still blocked
runtime no-touch remains active
agents/sales_agent remains compatibility layer
```
