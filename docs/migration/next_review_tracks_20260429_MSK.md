# Next Review Tracks — 2026-04-29 МСК

## Purpose

This document converts the owner decisions into separate review tracks.

It does not approve staging, commit, deploy, runtime changes, env changes, cron changes, systemd changes, or docker changes.

## Track 1 — Finance Contour

Owner decision:

- keep separate from OpenCloud migration.

Scope:

- `apps/finansist/` canonical, `agents/finansist/` compatibility shim
- `cloudbot/workflows/finance_*`
- `cloudbot/workflows/pnl_analysis.py`
- `cloudbot/workflows/cashflow_analysis.py`
- `cloudbot/workflows/receivables_analysis.py`
- `cloudbot/workflows/payables_analysis.py`
- `scripts/finansist_*.mjs`
- `checks/finansist_google_smoke.mjs`
- `tests/unit/test_finansist_agent.py`

Recommended handling:

- create a separate finance branch or separate repo decision;
- do not include in OpenCloud migration commits;
- run finance-specific tests before any acceptance.

## Track 2 — Larisa Content / Search Feature

Owner decision:

- accept as a separate feature review track, not migration.

Scope:

- `agents/larisa_ivanovna/commands/get_web_search.py`
- `agents/larisa_ivanovna/commands/get_content_topics.py`
- `agents/larisa_ivanovna/commands/get_content_post.py`
- `agents/larisa_ivanovna/workflows/search.py`
- `agents/larisa_ivanovna/workflows/content_topics.py`
- `agents/larisa_ivanovna/formatters/telegram_content_topics.py`
- `agents/larisa_ivanovna/formatters/telegram_content_post.py`
- `agents/larisa_ivanovna/schemas/content.py`
- `cloudbot/workflows/larisa_search.py`
- `cloudbot/workflows/larisa_content_topics.py`
- `cloudbot/workflows/larisa_content_post.py`
- `infra/orchestrator/workflows/larisa_content_topics.sh`

Recommended handling:

- review as Larisa feature;
- run Larisa integration tests;
- define Telegram smoke checklist before production use;
- do not mix with structural migration.

## Track 3 — Sales / Lev Runtime Review

Owner decision:

- accept as a separate Sales / Lev runtime review track, not migration.

Scope:

- `agents/sales_agent/sales_agent.py`
- `agents/sales_agent/sales_formatter.py`
- `agents/sales_agent/pipeline_analyzer.py`
- `agents/sales_agent/risk_detector.py`
- `scripts/run_sales_copilot.py`
- `checks/sales_morning_dispatch_smoke.py`

Recommended handling:

- review behavior changes explicitly;
- run Sales / Lev runtime tests;
- run smoke checklist before production acceptance;
- keep `agents/sales_agent` compatibility layer intact.

## Track 4 — Config / Env / Cron Review

Owner decision:

- review first; do not treat as current truth yet.

Scope:

- `.env.integrations.example`
- `configs/schedule_contract.env`
- `configs/schedules.cron`
- `configs/README.md`
- `infra/remote-ops.env.example`

Recommended handling:

- scan for secrets;
- classify as example, schema, draft, or current truth;
- do not apply to live env or cron;
- commit separately after approval.

## Track 5 — CI Workflow Review

Owner decision:

- review and adapt before acceptance.

Scope:

- `.github/workflows/sales-contract-checks.yml`

Known issue:

- current workflow references old test module paths and must be adapted to the new `tests/integration/` layout before acceptance.

Recommended handling:

- update test commands to new paths;
- verify no required secrets are assumed;
- commit as separate CI track.

## Track 6 — Docs / Control-Plane Review

Owner decision:

- review separately and commit as docs/control-plane if accepted.

Scope:

- `docs/architecture/larisa_live_contour_audit_20260325_MSK.md`
- `docs/architecture/runtime_map.md`
- `docs/architecture/schedule_contract.md`
- `docs/architecture/system_map.md`
- `docs/larisa_execution_checklist_MSK.md`
- `docs/message_for_larisa_MSK.md`
- `docs/sales_copilot.md`
- `ops/external_data_sources_MSK.md`
- `ops/owner_operating_contract_MSK.md`
- `ops/runbook_openclaw_security_profile_MSK.md`

Recommended handling:

- verify whether each document describes current truth or future intent;
- commit accepted docs separately from code;
- do not use docs changes to imply runtime approval.

## Explicitly Not In Scope

The following are not part of the next review tracks:

- server mutation;
- `/opt/*`;
- `/etc/*`;
- `/root/*`;
- live env;
- cron deployment;
- systemd changes;
- docker changes;
- runtime pointer changes.

## Recommended Order

1. Config / env / cron review.
2. Sales / Lev runtime review.
3. Larisa content / search feature review.
4. CI workflow review.
5. Docs / control-plane review.
6. Finance contour ownership decision.

## Status

Review tracks prepared.
