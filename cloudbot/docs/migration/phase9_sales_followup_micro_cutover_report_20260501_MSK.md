# Phase 9 Sales follow-up micro-cutover report — 2026-05-01 МСК

## Status

Controlled micro-cutover completed successfully.

Only the generic Lev/Sales runtime pointer was changed:

`/opt/cloudbot-runtime/current` -> `/opt/cloudbot-runtime/releases/dev_3b160ba`

## Scope

Released the dedicated Sales follow-up report from commit:

`3b160ba fix: add dedicated sales followup report`

This release changes the Sales follow-up runtime from reusing `focus` to using a dedicated `followup` report type.

Expected follow-up markers:

- `📌 Контроль до конца дня`
- `Что ещё висит`
- `Что требует реакции до конца дня`

## No-touch confirmation

Not changed:

- `/opt/cloudbot-runtime/larisa/current`
- `/opt/openclaw`
- env files
- cron files
- systemd units
- Docker runtime
- Telegram token/chat routing
- `agents/sales_agent` compatibility layer

## Baseline

Before cutover:

- rollback target: `/opt/cloudbot-runtime/releases/dev_01eeee5`
- Larisa pointer: `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635`

After cutover:

- generic pointer: `/opt/cloudbot-runtime/releases/dev_3b160ba`
- Larisa pointer: `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635`
- release commit file: `3b160ba`

## Deployment method

Used narrow manual release flow instead of `sales_agent_deploy.sh`.

Reason:

- `sales_agent_deploy.sh` also rewrites env, cron and system runner files;
- Phase 9 only needed the new code under `/opt/cloudbot-runtime/current`;
- existing production wrappers already `cd /opt/cloudbot-runtime/current`.

Actions performed:

1. Created archive from git commit `3b160ba`.
2. Uploaded archive to the server.
3. Created staging release:
   - `/opt/cloudbot-runtime/releases/.dev_3b160ba.staging`
4. Added runtime root runner scripts inside staging.
5. Ran staging syntax/compile/smoke checks.
6. Moved staging to:
   - `/opt/cloudbot-runtime/releases/dev_3b160ba`
7. Switched only:
   - `/opt/cloudbot-runtime/current`
8. Ran post-cutover follow-up smoke.

## Staging notes

First staging attempt stopped before symlink switch.

Reason:

- smoke used `scripts/run_sales_copilot.py --report followup --json` directly on the server;
- that bridge command expects SSH bridge variables when run in that context.

Resolution:

- changed staging smoke to the production-equivalent command:
  - `python3 -m agents.lev_petrovich --report followup`
- reran staging from scratch.

No production pointer was switched during the failed first attempt.

## Successful staging smoke

Staging smoke directory:

`/tmp/dev_3b160ba_smoke_20260501_201029_MSK`

Generated smoke report:

`/tmp/dev_3b160ba_smoke_20260501_201029_MSK/sales_followup_20260501_201116_MSK.txt`

Checks passed:

- runner shell syntax;
- Python compileall for `agents`, `apps`, `cloudbot`, `shared`;
- direct `agents.lev_petrovich --report followup`;
- isolated `sales_followup.sh` dry-run;
- marker `📌 Контроль до конца дня`;
- marker `Что ещё висит`;
- marker `Что требует реакции до конца дня`;
- no `Traceback`;
- no `ModuleNotFoundError`;
- no `ImportError`;
- no `ERROR`;
- no `FAILED`;
- no `Exception`;
- no `format_validation`;
- no `invalid choice`.

## Post-cutover smoke

Post-cutover check:

- `/opt/cloudbot-runtime/current` -> `/opt/cloudbot-runtime/releases/dev_3b160ba`
- `/opt/cloudbot-runtime/current/RELEASE_COMMIT` -> `3b160ba`
- CLI help exposes `followup`
- `python3 -m agents.lev_petrovich --report followup` on current release passed marker check

Result:

`post_cutover_smoke=ok`

## Rollback

Rollback was not needed.

Rollback target remains available:

`/opt/cloudbot-runtime/releases/dev_01eeee5`

Rollback action, if ever needed, must only switch `/opt/cloudbot-runtime/current`.

## Remaining observation

The `2026-05-01 17:00 МСК` scheduled Sales follow-up ran before this micro-cutover.

Therefore, scheduled production observation for the new dedicated `followup` report type is pending the next real Sales follow-up cron slot:

`2026-05-02 17:00 МСК`

Observation check should run at:

`2026-05-02 17:10 МСК`

Success criteria:

- new `sales_followup_20260502_1700*_MSK.txt`;
- Telegram delivery OK;
- route `lev-petrovich`;
- report type `followup`;
- marker `📌 Контроль до конца дня`;
- no `invalid choice`;
- no `format_validation`;
- no import/runtime errors.

## Verdict

Phase 9 micro-cutover is complete and stable by staging/post-cutover smoke.

Final scheduled confirmation is pending the next `17:00 МСК` Sales follow-up cron.
