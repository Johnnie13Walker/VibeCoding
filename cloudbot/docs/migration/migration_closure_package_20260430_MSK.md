# Cloudbot apps migration closure package — 2026-04-30 МСК

## Status

This is a docs-only closure package prepared while waiting for scheduled production cron observations.

No runtime pointer, env, cron, systemd, Docker, Telegram routing, `/opt/openclaw`, or compatibility shim was changed by this document.

## Current migration state

Code migration is complete for the main Cloudbot app contours:

| Contour | Canonical source | Compatibility layer | Runtime status |
| --- | --- | --- | --- |
| Larisa Ivanovna | `apps/larisa_ivanovna` | `agents/larisa_ivanovna` | cut over to `dev_2bb6635` |
| Lev Petrovich | `apps/lev_petrovich` | `agents/lev_petrovich` | cut over through generic runtime `dev_0c76cdf` |
| Sales legacy layer | `apps/lev_petrovich/legacy_sales_agent` | `agents/sales_agent` | cut over through generic runtime `dev_0c76cdf`; compatibility layer must remain |
| Finansist | `apps/finansist` | `agents/finansist` | code migrated; not part of current production runtime cutover |
| Shared layer | `shared/*` | n/a | required by runtime releases |

Current production runtime pointers from the latest recorded checks:

| Pointer | Target |
| --- | --- |
| `/opt/cloudbot-runtime/larisa/current` | `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635` |
| `/opt/cloudbot-runtime/current` | `/opt/cloudbot-runtime/releases/dev_0c76cdf` |

Historical note:

- `docs/migration/current_reports_inventory_20260430_MSK.md` was created before Lev/Sales cutover and records the old Sales runtime state at that moment.
- Current Lev/Sales status is recorded in `phase6_lev_sales_cutover_report_20260430_MSK.md` and `phase7_lev_sales_manual_live_observation_20260430_MSK.md`.

## Completed gates

### Code and tests

- Apps structure introduced and merged into `dev`.
- Compatibility shims retained for all migrated contours.
- `agents/sales_agent` retained as a temporary compatibility layer.
- `shared/` included in runtime release packaging after the first Larisa staging failure exposed the dependency.
- Unit, integration and smoke checks passed after the latest docs changes.

### Larisa

- Dry-run validation passed.
- Approval package prepared.
- Controlled cutover completed.
- Manual live-smoke completed after cutover.
- Telegram route resolved to `larisa-ivanovna`.
- Rollback not needed.

### Lev/Sales

- Dry-run validation found and fixed:
  - invalid `followup` report type in Sales follow-up workflow;
  - weekly report format marker mismatch.
- Regression tests added for Sales dispatch contracts.
- Approval package prepared.
- Controlled cutover completed.
- Manual live observation completed for:
  - Sales follow-up;
  - Sales weekly review;
  - Sales morning report package.
- Telegram route resolved to `lev-petrovich`.
- Rollback not needed.

### OpenClaw

- Read-only server-only audit completed.
- `/opt/openclaw` confirmed as a separate dirty runtime/repo contour.
- OpenClaw was not changed and must remain out of the Cloudbot apps migration closure.

## Pending scheduled observation

Manual live checks do not replace scheduled cron observation. Final migration closure requires real scheduled cron evidence.

Pending cron facts:

| Required fact | Expected time МСК | Success criteria |
| --- | --- | --- |
| Sales follow-up | `2026-04-30 17:00` | new `sales_followup_*_MSK.txt`, Telegram send OK, no report type/format/runtime errors |
| Larisa daily brief | `2026-05-01 08:00` | new `larisa_daily_brief_*_MSK.txt`, cron log fresh, Telegram delivery OK, no import/token/chat errors |
| Sales morning report | `2026-05-01 09:30` | new `sales_morning_report_*_MSK.txt`, Sales/Risks/Focus delivered, no Bitrix/runtime errors |
| Sales morning check | `2026-05-01 09:40` | new `sales_morning_report_check_*_MSK.txt`, delivery sequence accepted or explainable |
| Sales weekly review | `2026-05-01 18:30` | new `sales_weekly_review_*_MSK.txt`, weekly marker present, Telegram send OK |

If any scheduled fact fails, do not continue legacy cleanup. Diagnose first and use the recorded rollback targets if needed.

## Final closure checklist

The migration can be marked as closed only when all items below are true:

- [ ] `/opt/cloudbot-runtime/larisa/current` still points to `dev_2bb6635`.
- [ ] `/opt/cloudbot-runtime/current` still points to `dev_0c76cdf`.
- [ ] Larisa scheduled cron run after cutover is confirmed.
- [ ] Sales follow-up scheduled cron run after cutover is confirmed.
- [ ] Sales morning report scheduled cron run after cutover is confirmed.
- [ ] Sales morning check scheduled cron run after cutover is confirmed or any duplicate-log noise is documented as non-runtime failure.
- [ ] Sales weekly scheduled cron run after cutover is confirmed.
- [ ] No `ModuleNotFoundError`, `ImportError`, `Traceback`, token/chat routing error, or format validation failure is present in fresh runtime artifacts.
- [ ] Telegram delivery is confirmed for both Larisa and Lev/Sales routes.
- [ ] No rollback was required, or rollback was executed and documented.
- [ ] `docs/migration/phase8_24h_observation_YYYYMMDD_MSK.md` is committed to `dev`.
- [ ] `agents/sales_agent` remains present after closure.
- [ ] `/opt/openclaw` remains unchanged by Cloudbot apps migration closure.

## Rollback targets

| Contour | Current target | Rollback target |
| --- | --- | --- |
| Larisa | `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635` | `/opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326` |
| Lev/Sales | `/opt/cloudbot-runtime/releases/dev_0c76cdf` | `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60` |

Rollback must only switch the relevant runtime symlink. Do not mix rollback with env, cron, systemd, Docker, or OpenClaw changes.

## No-touch list until closure

- `/opt/openclaw`
- `/etc/openclaw`
- env files
- cron files
- systemd units
- Docker runtime
- Telegram token/chat routing
- `agents/sales_agent` retirement or deletion
- Finance/iOS/HAPP/VPN/subscription cleanup
- OpenClaw backup/state cleanup

## Post-closure backlog

### Track A — scheduled observation closure

Create and commit:

`docs/migration/phase8_24h_observation_YYYYMMDD_MSK.md`

Required content:

- current runtime pointers;
- latest scheduled Larisa report and cron log timestamp;
- latest scheduled Sales follow-up report;
- latest scheduled Sales morning report and morning check;
- latest scheduled Sales weekly report;
- Telegram delivery evidence with chat ids redacted;
- error scan results;
- verdict: `stable`, `observe more`, or `rollback needed`.

### Track B — legacy compatibility policy

After stable scheduled observation:

- keep `agents/larisa_ivanovna` as a compatibility shim until all entrypoints are confirmed on `apps/larisa_ivanovna`;
- keep `agents/lev_petrovich` as a compatibility shim until all entrypoints are confirmed on `apps/lev_petrovich`;
- keep `agents/finansist` as a compatibility shim until finance runtime ownership is decided;
- keep `agents/sales_agent` as an explicit temporary compatibility layer.

Do not delete or retire `agents/sales_agent` without a separate approval package.

### Track C — runtime entrypoint cleanup

After closure:

- inventory production wrappers that still call compatibility paths;
- decide whether each wrapper should continue using compatibility imports or move to `apps/*`;
- update one contour at a time;
- preserve rollback targets for each entrypoint change.

### Track D — OpenClaw server-only cleanup

Use `docs/migration/openclaw_server_only_audit_20260430_MSK.md` as the starting point.

Allowed future work only with separate approval:

- extract tracked web-search/SearXNG/DuckDuckGo changes into a reviewed patch;
- define ownership for OpenClaw repo versus engineer repo;
- archive backup files outside git;
- decide what belongs to OpenClaw core and what belongs to Cloudbot runtime.

Still forbidden without approval:

- copying `.env*`;
- copying `state/`;
- committing backup files;
- restarting Docker;
- changing `/opt/openclaw`;
- changing OpenClaw cron or env.

### Track E — monitoring and daily status

After closure:

- make the 09:30 МСК daily status depend on concrete report/log freshness checks;
- include Larisa, Sales, WHOOP and OpenClaw Todo contours;
- report `ОК` only when scheduled artifacts and delivery logs are fresh;
- include actionable failure reason and next check time when not OK.

## Final migration verdict template

Use this wording only after scheduled observation is green:

`Cloudbot apps migration is complete for Larisa and Lev/Sales production runtime. Canonical source is apps/*, compatibility shims remain in place, agents/sales_agent remains active as a temporary compatibility layer, and OpenClaw remains a separate server-only contour.`

Until then, the correct verdict is:

`Cloudbot apps migration is functionally cut over and manually live-smoked, but still pending scheduled cron observation.`
