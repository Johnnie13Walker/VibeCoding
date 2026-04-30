# Next Wave Readiness Decision

Дата фиксации: 2026-04-28 МСК.

Статус: readiness decision. Этот документ не разрешает production migration.

## 1. Current state

Completed:

```text
Wave 4 test-layout migration
Wave 5 config env examples migration
Wave 6 dependency-map planning
```

Current successful verification:

```text
python3 -m unittest discover -s tests/unit
Ran 12 tests
OK
```

## 2. Readiness verdict

```text
ready for next planning wave
not ready for production code move
```

## 3. Why production move is not ready

Production move is still blocked because:

- `agents/sales_agent` is still active compatibility layer;
- `scripts/run_sales_copilot.py` is live-sensitive;
- Larisa entrypoints use `python3 -m agents.larisa_ivanovna`;
- shared-core `cloudbot.*` import surface is broad;
- provider and workflow boundaries are high-risk;
- runtime/env/cron remain no-touch;
- no candidate-specific production smoke has been executed.

## 4. Recommended next wave

Next safe wave:

```text
Wave 7A: choose one non-runtime, non-agent production-adjacent candidate for design only
```

Allowed candidate classes:

```text
docs-only contracts
test migration backlog item after review
dependency maps refinement
one low-risk helper only after import map and owner approval
```

Not allowed:

```text
agents/sales_agent retirement
Larisa code move
Lev/Sales code move
shared-core move
runtime/env/cron/deploy changes
```

## 5. Required before any code move

Before any code move:

1. One exact candidate.
2. Import compatibility plan.
3. Old-path compatibility.
4. Safe tests.
5. Smoke checklist.
6. Rollback plan.
7. Owner approval.

## 6. Final decision

```text
next wave may continue as planning/design only
production code move remains blocked
runtime no-touch remains active
```
