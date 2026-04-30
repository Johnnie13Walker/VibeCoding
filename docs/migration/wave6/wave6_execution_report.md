# Wave 6 Execution Report

Дата фиксации: 2026-04-28 МСК.

Статус: completed for dependency-map planning only.

## 1. Documents created

Sales/Lev:

```text
docs/migration/sales_lev/sales_lev_dependency_map.md
docs/migration/sales_lev/sales_lev_runtime_bridge_map.md
docs/migration/sales_lev/sales_lev_report_contract_map.md
docs/migration/sales_lev/sales_lev_smoke_checklist_refined.md
```

Larisa:

```text
docs/migration/larisa/larisa_dependency_map.md
docs/migration/larisa/larisa_runtime_entrypoint_map.md
docs/migration/larisa/larisa_smoke_checklist_refined.md
```

Shared-core:

```text
docs/migration/shared_core/shared_core_import_map.md
docs/migration/shared_core/provider_boundary_map.md
docs/migration/shared_core/workflow_boundary_map.md
```

General:

```text
docs/migration/runtime_no_touch_register.md
docs/migration/legacy_archive_candidate_register.md
docs/migration/test_migration_backlog.md
```

## 2. What was not changed

Not changed:

- production code;
- imports;
- `agents/*`;
- `cloudbot/*`;
- `scripts/run_sales_copilot.py`;
- live env;
- runtime pointers;
- cron/systemd/docker;
- deploy/rollback/verify scripts;
- `/opt/*`, `/etc/*`, `/root/*`, `/home/ops/*`.

## 3. Tests after every step

After each document step:

```bash
python3 -m unittest discover -s tests/unit
```

Result after each step:

```text
Ran 12 tests
OK
```

## 4. Current blockers

Still blocked:

```text
Sales/Lev production migration
Larisa production migration
shared-core migration
provider migration
workflow migration
runtime/env/cron migration
agents/sales_agent retirement
```

## 5. Verdict

```text
Wave 6 dependency-map planning completed
production code move still blocked
next step: next-wave readiness decision
```
