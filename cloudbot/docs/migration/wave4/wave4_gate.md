# Wave 4 Gate

Date: 2026-04-28 MSK.

This is gate planning for the first possible code migration candidate. It does not execute migration.

No code is moved. No imports are changed. No runtime, env, cron, systemd, docker, deploy, rollback, verify, or server-only path is touched.

## 1. Inputs

Completed:

- Wave 2 structural preparation.
- Wave 3 source-of-truth markers.
- Wave 3 target skeleton.
- Wave 3 code-adjacent README markers.
- Wave 3 marker report.

Current constraints:

- `agents/sales_agent` remains temporary compatibility layer.
- `apps/`, `shared/`, `config/`, `archive/`, and test subfolders are placeholders only.
- `cloudbot` remains active shared-core path.
- `configs` remains active config examples/contracts path.
- runtime and server-only integrations remain no-touch.
- finance/iOS/HAPP/VPN/subscription remain excluded.

## 2. Import Coupling Snapshot

Read-only scan found active import coupling across the current paths:

- `agents/lev_petrovich/agent.py` imports from `agents.sales_agent.sales_agent`.
- `agents/sales_agent/sales_agent.py` imports `agents.lev_petrovich.telegram_route`.
- `scripts/run_sales_copilot.py` imports `agents.sales_agent.report_contract` and `agents.lev_petrovich.agent`.
- `cloudbot/devops/sales_dispatch_health.py` imports `agents.sales_agent.*` and `agents.lev_petrovich.*`.
- `cloudbot/workflows/larisa_runtime.py` imports `agents.larisa_ivanovna.*`.
- tests import `agents.larisa_ivanovna`, `agents.lev_petrovich`, `agents.sales_agent`, and `cloudbot.*`.
- `cloudbot/*` modules import each other extensively.

Conclusion: direct code moves are not safe without import compatibility planning.

## 3. Candidate Code Migration Moves

| candidate_id | candidate | exact paths | requires import changes? | touches runtime? | blast radius | risk | gate decision |
|---|---|---|---|---|---|---|---|
| W4-CAND-01 | Move a small Larisa utility/module to `apps/larisa_ivanovna` | `agents/larisa_ivanovna/*` to `apps/larisa_ivanovna/*` | yes | no direct runtime touch, but runtime imports affected | Larisa + tests | high | not approved |
| W4-CAND-02 | Move Lev facade to `apps/lev_petrovich` | `agents/lev_petrovich/*` to `apps/lev_petrovich/*` | yes | possible runtime bridge impact | Lev/Sales runtime | high | not approved |
| W4-CAND-03 | Move `agents/sales_agent` under `apps/lev_petrovich/legacy_sales_agent` | `agents/sales_agent/*` | yes | possible Sales runtime break | Sales/Lev critical | critical | prohibited now |
| W4-CAND-04 | Move a shared provider to `shared/providers` | `cloudbot/providers/*` | yes | provider behavior risk | shared-core | high | not approved |
| W4-CAND-05 | Move config examples to `config/env/examples` | `configs/*` | possibly docs/tests references | no runtime if examples only, but config confusion risk | config/contracts | medium/high | not approved |
| W4-CAND-06 | Move tests into `tests/unit|integration|smoke` | `tests/test_*.py` | likely no runtime imports but test discovery changes | no | validation surface | medium | not approved |
| W4-CAND-07 | Create import compatibility plan before code movement | `docs/migration/wave4/import_compatibility_plan.md` | no | no | docs only | low | recommended next |

## 4. Recommended Gate Verdict

First code migration should **not** execute yet.

Recommended next move:

```text
docs/migration/wave4/import_compatibility_plan.md
```

This is not code migration. It is the required plan before any code movement.

Reason:

- Current code has direct imports from old paths.
- Tests lock old import paths.
- `agents/sales_agent` compatibility cannot be broken.
- Shared-core is still active under `cloudbot`.
- Moving even one module without a compatibility plan risks breaking runtime or tests.

## 5. Required Import Compatibility Plan

Before any code move, the plan must define:

- exact source path
- exact target path
- old import path preservation strategy
- whether compatibility shim is required
- whether wrapper module is allowed
- test list to run without live env/server/secrets
- rollback method
- owner approval point
- smoke validation plan for impacted contour

## 6. Anti-Scope

Do not perform in Wave 4 Gate:

- code moves
- import rewrites
- compatibility shim creation
- package file creation
- `__init__.py` creation
- runtime changes
- env changes
- cron/systemd/docker changes
- deploy/rollback/verify changes
- server path changes
- `agents/sales_agent` retirement
- finance/iOS/HAPP/VPN/subscription changes

## 7. Ready Checklist for Future Code Migration

| check_id | requirement | status | notes |
|---|---|---|---|
| W4-GATE-01 | exact one code migration candidate selected | fail | no candidate safe enough yet |
| W4-GATE-02 | import compatibility plan exists | fail | recommended next doc |
| W4-GATE-03 | rollback plan exists | fail | must be candidate-specific |
| W4-GATE-04 | tests safe to run identified | fail | must avoid live env/server/secrets |
| W4-GATE-05 | Larisa/Lev/Sales smoke plan selected if impacted | fail | depends on candidate |
| W4-GATE-06 | `agents/sales_agent` preserved | pass | no retirement allowed |
| W4-GATE-07 | runtime no-touch preserved | pass | no runtime changes in gate |
| W4-GATE-08 | owner approval for code move | fail | not requested by this gate |

## 8. Final Status

Wave 4 Gate completed.

Final verdict: **code migration still blocked**.

The project is ready for the next safe planning step:

```text
docs/migration/wave4/import_compatibility_plan.md
```

No code movement is approved by this gate.

## 9. What to Send Back to ChatGPT

```text
Wave 4 Gate completed.

Verdict:
code migration still blocked

Reason:
active imports bind agents/*, cloudbot/*, scripts/run_sales_copilot.py, and tests to current paths.

Recommended next step:
create docs/migration/wave4/import_compatibility_plan.md

No code/import/runtime/deploy/env/cron/systemd/docker/server changes were made.
```
