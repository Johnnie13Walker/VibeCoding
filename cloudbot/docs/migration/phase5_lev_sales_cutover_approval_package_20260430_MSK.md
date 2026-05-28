# Phase 5 Lev/Sales cutover approval package — 2026-04-30 МСК

## Purpose

This document defines the approval boundary for a future controlled Lev/Sales production cutover.

It is a plan and approval package only. It does not perform cutover.

## Current status

Phase 4 Lev/Sales dry-run validation is green after local fixes.

Confirmed at `2026-04-30 12:08 МСК`:

| Path | Current target |
| --- | --- |
| `/opt/cloudbot-runtime/current` | `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60` |
| `/opt/cloudbot-runtime/larisa/current` | `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635` |

Local source baseline:

| Field | Value |
| --- | --- |
| Source repo | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` |
| Branch | `dev` |
| Candidate commit | `0c76cdf` |
| Candidate release id | `dev_0c76cdf` |

## Approved scope candidate

Only the generic Sales/Lev runtime may be considered for the next controlled cutover:

- current pointer: `/opt/cloudbot-runtime/current`;
- old target: `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60`;
- future target candidate: `/opt/cloudbot-runtime/releases/dev_0c76cdf`;
- canonical Lev path: `apps/lev_petrovich`;
- canonical Sales compatibility layer: `apps/lev_petrovich/legacy_sales_agent`;
- compatibility shims: `agents/lev_petrovich`, `agents/sales_agent`.

The expected server-side mutation, after explicit approval, is only:

```text
/opt/cloudbot-runtime/current -> /opt/cloudbot-runtime/releases/dev_0c76cdf
```

## Explicit non-scope

Do not include:

- Larisa runtime pointer changes;
- `/opt/cloudbot-runtime/larisa/current`;
- `/opt/openclaw` edits or cleanup;
- env changes;
- cron changes;
- systemd changes;
- Docker changes;
- token/chat routing changes;
- Bitrix state mutation;
- OpenClaw server-only audit;
- Finance/iOS/HAPP/VPN/subscription cleanup;
- `agents/sales_agent` retirement or deletion.

`agents/sales_agent` remains a temporary compatibility layer and must continue to import.

## Preconditions before live cutover

All must be true before controlled cutover:

- Phase 4 remains green on `dev`;
- worktree is clean;
- release archive includes `apps/`, `agents/`, `shared/`, `cloudbot/`, `infra/`, `scripts/`, and required tests/checks;
- `shared/` is included in the release archive;
- old target exists and is recorded;
- rollback command is prepared before the switch;
- no env mutation is included;
- no cron/systemd/docker mutation is included;
- no token/chat routing mutation is included;
- no `/opt/openclaw` mutation is included.

## Phase 4 evidence

Phase 4 fixed two blockers before this approval package:

1. `sales_followup.sh` used invalid runtime report type `followup`.
   It now uses supported runtime report type `focus` while preserving the job/report name `sales_followup`.

2. Weekly report failed format validation because the generated title did not match the contract marker.
   The weekly formatter now emits `📊 Отчёт Льва Петровича по продажам`.

Phase 4 checks passed:

| Check | Result |
| --- | --- |
| imports `apps.lev_petrovich`, `agents.lev_petrovich`, `apps.lev_petrovich.legacy_sales_agent`, `agents.sales_agent` | OK |
| `python3 -m unittest discover -s tests/unit` | OK, 18 tests |
| `python3 -m unittest discover -s tests/integration` | OK, 102 tests |
| `python3 checks/sales_morning_dispatch_smoke.py` | OK |
| `python3 checks/smoke_test.py` | OK |
| `sales_morning_report.sh` fixture + Telegram dry-run | OK |
| `sales_followup.sh` fixture + Telegram dry-run | OK |
| `sales_weekly_review.sh` fixture + Telegram dry-run | OK |

## Cutover procedure candidate

After explicit owner approval only:

1. Reconfirm current server target:

   ```bash
   readlink -f /opt/cloudbot-runtime/current
   ```

2. Create staged release from local `dev` commit `0c76cdf`:

   ```text
   /opt/cloudbot-runtime/releases/.dev_0c76cdf.staging
   ```

3. Verify staged release before symlink switch:

   ```bash
   bash -n run_sales_morning_report_from_runtime_env.sh
   bash -n run_sales_morning_report_check_from_runtime_env.sh
   bash -n run_sales_followup_from_runtime_env.sh
   bash -n run_sales_weekly_review_from_runtime_env.sh
   bash -n infra/orchestrator/workflows/sales_morning_report.sh
   bash -n infra/orchestrator/workflows/sales_morning_report_check.sh
   bash -n infra/orchestrator/workflows/sales_followup.sh
   bash -n infra/orchestrator/workflows/sales_weekly_review.sh
   python3 -m compileall apps agents shared cloudbot scripts
   python3 -c "import apps.lev_petrovich; import agents.lev_petrovich; import apps.lev_petrovich.legacy_sales_agent; import agents.sales_agent"
   ```

4. Promote staged release to:

   ```text
   /opt/cloudbot-runtime/releases/dev_0c76cdf
   ```

5. Switch only:

   ```text
   /opt/cloudbot-runtime/current
   ```

6. Run post-cutover smoke immediately.

## Required post-cutover smoke

Run immediately after switching `/opt/cloudbot-runtime/current`:

| Smoke item | Required result |
| --- | --- |
| `readlink -f /opt/cloudbot-runtime/current` | `/opt/cloudbot-runtime/releases/dev_0c76cdf` |
| import `apps.lev_petrovich` | OK |
| import `agents.lev_petrovich` | OK |
| import `apps.lev_petrovich.legacy_sales_agent` | OK |
| import `agents.sales_agent` | OK |
| morning sales report dry-run or controlled send | report generated; contract sequence preserved |
| morning dispatch health check | confirms `sales`, `risks`, `focus` package |
| follow-up dry-run or controlled send | no `--report followup` failure |
| weekly review dry-run or controlled send | no weekly format validation failure |
| Bitrix pull sanity | app state or live adapter readable |
| Telegram route sanity | expected Sales chat route, no Larisa route crossover |
| logs | no `Traceback`, `ImportError`, `ModuleNotFoundError`, format validation failure, wrong route |

Live Telegram send must be explicitly chosen before execution:

- default safe option: dry-run smoke only;
- stronger option: one controlled live Sales smoke message if owner approves.

## Rollback target

Rollback target:

```text
/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60
```

Rollback action:

```text
/opt/cloudbot-runtime/current -> /opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60
```

Rollback must not touch:

- Larisa pointer;
- `/opt/openclaw`;
- env;
- cron;
- systemd;
- Docker;
- token/chat routing.

## Rollback triggers

Rollback immediately if any critical item fails:

- `/opt/cloudbot-runtime/current` points to an unexpected path;
- imports fail;
- morning report generation fails;
- morning dispatch contract misses `sales`, `risks`, or `focus`;
- follow-up still fails with invalid report type;
- weekly still fails format validation;
- Telegram route points to the wrong chat/bot;
- Bitrix state cannot be read by the Sales runtime;
- logs show repeated runtime/import exceptions.

## Observation after cutover

If controlled cutover succeeds, observe the following scheduled jobs:

| Job | Expected schedule МСК |
| --- | --- |
| Sales morning report | next weekday `09:30` |
| Sales morning check | next weekday `09:40` |
| Sales follow-up | next `17:00` |
| Sales weekly review | next Friday `18:30` |

Observation must check:

- report files in `/home/ops/cloudbot-sales-agent/reports`;
- cron logs for the four Sales jobs;
- `sales_agent.log`;
- `sales_daily_history.json`;
- Telegram delivery status;
- no format/import/runtime errors.

## Owner decision required

Before controlled cutover, owner must explicitly approve:

1. Create release `/opt/cloudbot-runtime/releases/dev_0c76cdf`.
2. Switch only `/opt/cloudbot-runtime/current`.
3. Keep Larisa, `/opt/openclaw`, env, cron, systemd, Docker, and Telegram routing unchanged.
4. Keep `agents/sales_agent` as compatibility layer.
5. Run immediate post-cutover smoke.
6. Roll back to `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60` if smoke fails.

## Gate conclusion

This package approves only the next decision point.

Controlled Lev/Sales cutover is still not executed by this document.

Next step after explicit owner approval:

- perform controlled Lev/Sales cutover for `/opt/cloudbot-runtime/current` only;
- run post-cutover smoke;
- document the result in `docs/migration/phase6_lev_sales_cutover_report_YYYYMMDD_MSK.md`.
