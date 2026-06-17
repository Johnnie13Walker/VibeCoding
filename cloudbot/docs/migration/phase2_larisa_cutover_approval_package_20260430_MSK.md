# Phase 2 Larisa cutover approval package — 2026-04-30 МСК

## Purpose

This document defines the approval boundary for the future Larisa production cutover.

It is a plan only. It does not perform cutover.

## Approved scope candidate

Only Larisa runtime may be considered for the next live cutover:

- source contour: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- branch: `dev`
- commit: `715225b`
- canonical app path: `apps/larisa_ivanovna`
- compatibility path: `agents/larisa_ivanovna`

## Explicit non-scope

Do not include:

- Lev/Sales runtime;
- `agents/sales_agent` retirement;
- Finance production enablement;
- iOS/FormaNutrition;
- HAPP/VPN/subscription cleanup;
- OpenClaw dirty-state cleanup;
- env/token/chat routing changes;
- cron/systemd/docker changes;
- deploy/rollback script rewrites.

## Current live baseline

From Phase 0:

- live pointer: `/opt/cloudbot-runtime/larisa/current`
- current target: `/opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326`
- latest confirmed daily brief: `2026-04-30 08:00 МСК`
- cron: `/etc/cron.d/cloudbot-larisa-daily-brief`
- wrapper: `/usr/local/bin/cloudbot-larisa-daily-brief.sh`

## Preconditions before live cutover

All must be true:

- Phase 0 runtime confirmation remains valid;
- Phase 1 Larisa dry-run validation remains green;
- rollback target is recorded;
- release creation command is reviewed before execution;
- no env mutation is included;
- no token/chat routing mutation is included;
- no cron/systemd/docker mutation is included;
- post-cutover smoke checklist is ready.

## Required post-cutover smoke

Run immediately after cutover:

- confirm `/opt/cloudbot-runtime/larisa/current` points to the new release;
- import `apps.larisa_ivanovna`;
- import `agents.larisa_ivanovna`;
- run Larisa command path used by wrapper;
- check Telegram delivery path;
- check daily brief report generation;
- check calendar/tasks/weather/search response if production env allows;
- check logs for import/runtime errors;
- confirm no wrong bot token/chat route fallback.

## Rollback trigger

Rollback immediately if any critical item fails:

- Telegram delivery fails;
- Larisa command import fails;
- daily brief generation fails;
- wrong bot/chat route is detected;
- runtime points to a broken release;
- logs show repeated import/runtime exceptions.

## Rollback target

Rollback target from Phase 0:

`/opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326`

Rollback command must not be improvised during incident response. It must be prepared and reviewed before live cutover.

## Owner decision required

Before live cutover, owner must explicitly approve:

1. Create a new Larisa runtime release from `dev` commit `715225b`.
2. Switch only `/opt/cloudbot-runtime/larisa/current`.
3. Do not touch Lev/Sales, OpenClaw, env, cron, systemd, Docker.
4. Run immediate smoke.
5. Roll back to `/opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326` if smoke fails.

## Gate conclusion

Larisa cutover is not executed by this package.

After owner approval, the next step is controlled Larisa cutover with test-after-action and immediate rollback if smoke fails.
