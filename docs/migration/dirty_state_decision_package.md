# Dirty State Decision Package

## Current Baseline

Safe migration commit created:

- `cb1c80b` — `миграция: зафиксировать безопасную структуру`

After that commit, the remaining working tree is still dirty, but it is now separated from the committed migration baseline.

This document classifies the remaining dirty-state. It does not approve staging, deletion, restore, deploy, or runtime changes.

## Executive Decision

Do not run `git add .`.

Do not commit remaining dirty-state as one batch.

The remaining state must be split into separate owner decisions:

- production-critical review;
- infra/deploy review;
- deleted files disposition;
- finance track;
- iOS track;
- HAPP/VPN/subscription cleanup track;
- docs/control-plane review;
- config/env/cron contract review.

## Bucket A — Production-Critical Review Required

These paths are close to live Larisa / Sales / shared runtime behavior.

They must not be accepted silently.

| path / zone | current state | likely role | decision |
|---|---:|---|---|
| `agents/larisa_ivanovna/agent.py` | modified | Larisa runtime agent | manual review required |
| `agents/larisa_ivanovna/config.py` | modified | Larisa config contract | manual review required |
| `agents/larisa_ivanovna/providers/calendar_provider.py` | modified | calendar integration | manual review required |
| `agents/larisa_ivanovna/providers/telegram_provider.py` | modified | Telegram delivery | manual review required |
| `agents/larisa_ivanovna/workflows/daily_brief.py` | modified | daily brief behavior | manual review required |
| `agents/larisa_ivanovna/workflows/evening_review.py` | modified | evening review behavior | manual review required |
| `agents/larisa_ivanovna/commands/get_web_search.py` | untracked | Larisa search feature | separate Larisa feature track |
| `agents/larisa_ivanovna/workflows/search.py` | untracked | Larisa search feature | separate Larisa feature track |
| `agents/larisa_ivanovna/workflows/content_topics.py` | untracked | Larisa content feature | separate Larisa feature track |
| `cloudbot/workflows/larisa_search.py` | untracked | Larisa search bridge | separate Larisa feature track |
| `cloudbot/workflows/larisa_content_topics.py` | untracked | Larisa content bridge | separate Larisa feature track |
| `cloudbot/workflows/larisa_content_post.py` | untracked | Larisa content bridge | separate Larisa feature track |
| `agents/sales_agent/sales_agent.py` | modified | Sales runtime | manual review required |
| `agents/sales_agent/sales_formatter.py` | modified | Sales report formatting | manual review required |
| `agents/sales_agent/pipeline_analyzer.py` | modified | Sales analytics | manual review required |
| `agents/sales_agent/risk_detector.py` | modified | Sales risks | manual review required |
| `scripts/run_sales_copilot.py` | modified | Sales bridge script | manual review required |
| `cloudbot/orchestrator/orchestrator.py` | modified | shared routing | manual review required |
| `cloudbot/orchestrator/router.py` | modified | shared routing | manual review required |
| `cloudbot/providers/search_provider.py` | modified | shared search provider | manual review required |
| `cloudbot/skills/web_search.py` | modified | shared web search skill | manual review required |

Recommended decision:

- split into `larisa-feature-review`, `sales-runtime-review`, and `shared-core-review`;
- run targeted tests per track;
- do not include these paths in structural migration commits until reviewed.

## Bucket B — Config / Env / Cron Contract Review

These paths affect runtime configuration or schedule assumptions.

| path | current state | risk | decision |
|---|---:|---|---|
| `.env.integrations.example` | modified | may expose or change integration contract | review before accept |
| `configs/schedule_contract.env` | modified | schedule/runtime contract | review before accept |
| `configs/schedules.cron` | modified | cron semantics | review before accept |
| `configs/README.md` | untracked | docs around config | review with config track |
| `infra/remote-ops.env.example` | untracked | remote ops env contract | review with infra track |

Recommended decision:

- do not stage with app code;
- create a separate `config-contract-review` package;
- verify no secrets before any commit.

## Bucket C — Infra / Deploy / Runtime No-Touch

These paths are operationally sensitive.

| path / zone | current state | risk | decision |
|---|---:|---|---|
| `infra/orchestrator/run_workflow.sh` | modified | workflow runner | manual review required |
| `infra/orchestrator/workflows/*` | modified/deleted/untracked | deploy/runtime workflows | manual review required |
| `infra/orchestrator/workflows/deploy.sh` | deleted | deploy path may be needed | investigate first |
| `infra/orchestrator/workflows/rollback.sh` | deleted | rollback path may be needed | investigate first |
| `infra/orchestrator/workflows/verify.sh` | deleted | verification path may be needed | investigate first |
| `infra/orchestrator/workflows/audit.sh` | deleted | audit path may be needed | investigate first |
| `scripts/verify_integrations.sh` | modified | verification script | manual review required |
| `scripts/larisa_finalize.sh` | modified | Larisa operational script | manual review required |
| `checks/*` | modified/deleted/untracked | smoke/ops checks | manual review required |

Recommended decision:

- do not delete or restore blindly;
- first decide whether `deploy.sh`, `rollback.sh`, `verify.sh`, `audit.sh` are obsolete or must be restored;
- keep this as `infra-deploy-disposition` track.

## Bucket D — Deleted Files Disposition

Deleted tracked files still need explicit disposition.

| group | examples | recommended decision |
|---|---|---|
| old health / VPN checks | `checks/morning_health_report.sh`, `checks/vpn_smoke_happ.sh`, `checks/vpn_verify.sh` | investigate first |
| deploy workflow scripts | `infra/orchestrator/workflows/deploy.sh`, `rollback.sh`, `verify.sh`, `audit.sh` | investigate first, likely restore or officially obsolete |
| control-plane snapshots | `control_plane_snapshots/architect_workspace_20260325_MSK/*` | archive decision required |
| HAPP/VPN files | `infra/happ-vpn.env.example`, `infra/templates/sing-box.service`, `ops/*happ*`, `services/vpn/*` | separate HAPP/VPN cleanup track |
| subscription service | `services/subscription/*` | separate subscription cleanup track |

Recommended decision:

- no silent deletion acceptance;
- prepare a restore/archive/obsolete decision for each group;
- deleted deploy/rollback/verify files are blockers for broad infra cleanup.

## Bucket E — Finance Track

Finance is a separate contour and must not be mixed with OpenCloud migration.

Untracked examples:

- `apps/finansist/` canonical, `agents/finansist/` compatibility shim
- `cloudbot/workflows/finance_runtime.py`
- `cloudbot/workflows/finance_summary.py`
- `cloudbot/workflows/pnl_analysis.py`
- `cloudbot/workflows/cashflow_analysis.py`
- `cloudbot/workflows/receivables_analysis.py`
- `cloudbot/workflows/payables_analysis.py`
- `scripts/finansist_*.mjs`
- `checks/finansist_google_smoke.mjs`
- `tests/unit/test_finansist_agent.py`

Recommended decision:

- create separate `finance-contour-review`;
- do not migrate into shared OpenCloud structure until finance ownership is approved;
- do not include in migration commits.

## Bucket F — iOS Track

Untracked iOS contour:

- `ios/FormaNutrition/`

Recommended decision:

- keep external to OpenCloud migration;
- create separate `ios-forma-review`;
- do not stage with Cloudbot migration.

## Bucket G — Docs / Control-Plane Review

Modified docs:

- `docs/architecture/runtime_map.md`
- `docs/architecture/schedule_contract.md`
- `docs/architecture/system_map.md`
- `docs/architecture/larisa_live_contour_audit_20260325_MSK.md`
- `docs/larisa_execution_checklist_MSK.md`
- `docs/message_for_larisa_MSK.md`
- `docs/sales_copilot.md`
- `ops/external_data_sources_MSK.md`
- `ops/owner_operating_contract_MSK.md`
- `ops/runbook_openclaw_security_profile_MSK.md`

Recommended decision:

- review as docs/control-plane track;
- commit separately from code/runtime changes;
- confirm they describe current truth and not future intent.

## Bucket H — Tooling / CI

Untracked:

- `.github/workflows/sales-contract-checks.yml`

Recommended decision:

- review as CI track;
- do not include until expected checks and secrets assumptions are confirmed.

## Minimal Owner Decisions

1. Decide whether deleted `deploy.sh`, `rollback.sh`, `verify.sh`, `audit.sh` must be restored or officially obsolete.
2. Decide whether Larisa search/content files are an approved feature track.
3. Decide whether Sales runtime/formatter dirty changes are approved feature/runtime changes.
4. Decide whether shared search/orchestrator dirty changes are approved shared-core changes.
5. Decide whether finance contour belongs in this repo or separate repo.
6. Decide whether iOS contour belongs in this repo or separate repo.
7. Decide whether HAPP/VPN/subscription deleted files should be archived or restored.
8. Decide whether config/env/cron contract changes are current truth or drafts.
9. Decide whether docs/control-plane modifications describe accepted current truth.
10. Decide whether CI workflow additions are approved.

## Recommended Next Sequence

1. `infra-deploy-disposition`: resolve deleted deploy/rollback/verify/audit files.
2. `sales-runtime-review`: review Sales dirty files and run Sales tests.
3. `larisa-feature-review`: review Larisa search/content dirty files and run Larisa tests.
4. `config-contract-review`: review env/cron/schedule files for secrets and runtime impact.
5. `finance-contour-review`: decide repo ownership before staging anything.
6. `ios-forma-review`: decide repo ownership before staging anything.
7. `docs-control-plane-review`: commit accepted docs separately.

## Status

Dirty-state is classified, but not resolved.

Remaining dirty files must be handled by separate owner decisions, not by a single bulk commit.
