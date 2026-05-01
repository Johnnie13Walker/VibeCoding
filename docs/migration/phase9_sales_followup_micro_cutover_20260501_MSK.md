# Phase 9 Sales follow-up micro-cutover — 2026-05-01 МСК

## Status

Approved by user request: proceed with the remaining steps and avoid further waiting where possible.

This phase covers only the dedicated Sales follow-up report introduced in commit `3b160ba`.

## Scope

Deploy only the generic Lev/Sales runtime release containing:

- dedicated runtime report type `followup`;
- `sales_followup.sh` using `REPORT_TYPE="followup"`;
- follow-up format contract:
  - `📌 Контроль до конца дня`;
  - `Что ещё висит`;
  - `Что требует реакции до конца дня`.

## Current baseline

- Current `dev` commit: `3b160ba fix: add dedicated sales followup report`
- Last stable observation document: `docs/migration/phase8_24h_observation_20260501_MSK.md`
- Observed stable Larisa runtime: `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635`
- Observed stable generic runtime before this micro-cutover: `/opt/cloudbot-runtime/releases/dev_01eeee5`

## Planned release

- Future release id: `dev_3b160ba`
- Target pointer to switch: `/opt/cloudbot-runtime/current`
- Rollback target: `/opt/cloudbot-runtime/releases/dev_01eeee5`

## No-touch boundaries

Do not change:

- `/opt/cloudbot-runtime/larisa/current`
- `/opt/openclaw`
- env files
- cron files
- systemd units
- Docker runtime
- Telegram token/chat routing
- `agents/sales_agent` compatibility layer

## Deployment method

Use a narrow manual release flow instead of `sales_agent_deploy.sh`.

Reason:

- `sales_agent_deploy.sh` also rewrites env, cron and system runner files;
- this micro-cutover only needs the new code in the generic runtime release;
- existing wrappers already `cd /opt/cloudbot-runtime/current`, so switching the symlink is sufficient.

Steps:

1. Build release archive from git commit `3b160ba`.
2. Include runtime source paths from `cloudbot_runtime_files`, including:
   - `apps/lev_petrovich`;
   - `agents/sales_agent`;
   - `shared/contracts`;
   - `shared/time`;
   - Sales workflows;
   - `scripts/run_sales_copilot.py`.
3. Create staging release:
   - `/opt/cloudbot-runtime/releases/.dev_3b160ba.staging`
4. Add runtime root runner scripts inside staging.
5. Run staging smoke:
   - bash syntax for runner scripts;
   - Python compile/import checks;
   - `python3 scripts/run_sales_copilot.py --report followup --json`;
   - dry-run follow-up workflow with isolated report/log paths.
6. If staging passes:
   - move staging to `/opt/cloudbot-runtime/releases/dev_3b160ba`;
   - switch only `/opt/cloudbot-runtime/current`.
7. Run post-cutover smoke:
   - pointer check;
   - `--report followup --json`;
   - isolated `sales_followup.sh` dry-run;
   - marker check for `📌 Контроль до конца дня`;
   - error scan.

## Success criteria

- `/opt/cloudbot-runtime/current` points to `/opt/cloudbot-runtime/releases/dev_3b160ba`.
- `followup` is accepted by runtime CLI.
- Generated follow-up report contains:
  - `📌 Контроль до конца дня`;
  - `Что ещё висит`;
  - `Что требует реакции до конца дня`.
- No `invalid choice`.
- No `format_validation`.
- No import/runtime errors.
- Larisa pointer unchanged.

## Rollback criteria

Rollback to `/opt/cloudbot-runtime/releases/dev_01eeee5` if:

- staging smoke fails after release creation;
- post-cutover smoke fails;
- `followup` is rejected by runtime;
- Telegram route becomes ambiguous;
- import/runtime failure appears.

Rollback action must only switch `/opt/cloudbot-runtime/current`.

## Observation after cutover

Because the 17:00 scheduled follow-up for `2026-05-01` already ran before this micro-cutover, scheduled production observation for the new `followup` report type is pending the next `17:00 МСК` Sales follow-up cron slot.

Manual dry-run/post-cutover smoke can confirm runtime correctness immediately, but live scheduled proof requires the next real cron run.
