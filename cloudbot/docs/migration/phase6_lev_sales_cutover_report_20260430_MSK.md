# Phase 6 Lev/Sales cutover report — 2026-04-30 МСК

## Status

Controlled Lev/Sales cutover completed.

Rollback was not needed.

## Scope

Changed on server:

- created new generic Sales/Lev runtime release:
  `/opt/cloudbot-runtime/releases/dev_0c76cdf`;
- switched only generic current pointer:
  `/opt/cloudbot-runtime/current`.

Not changed:

- `/opt/cloudbot-runtime/larisa/current`;
- `/opt/openclaw`;
- env files;
- cron files;
- systemd units;
- Docker runtime;
- `/usr/local/bin/cloudbot-sales-daily-brief.sh`;
- `/usr/local/bin/cloudbot-sales-morning-check.sh`;
- `/usr/local/bin/cloudbot-sales-followup.sh`;
- `/usr/local/bin/cloudbot-sales-weekly-review.sh`;
- Telegram token/chat routing;
- `agents/sales_agent` retirement.

## Release

| Field | Value |
| --- | --- |
| Source repo | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` |
| Branch | `dev` |
| Commit used for release | `0c76cdf` |
| Release id | `dev_0c76cdf` |
| Old target | `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60` |
| New target | `/opt/cloudbot-runtime/releases/dev_0c76cdf` |
| Release timestamp | `2026-04-30 12:17:57 МСК` |

Current pointers after cutover:

| Path | Target |
| --- | --- |
| `/opt/cloudbot-runtime/current` | `/opt/cloudbot-runtime/releases/dev_0c76cdf` |
| `/opt/cloudbot-runtime/larisa/current` | `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635` |

## Staging validation

Created staging release:

`/opt/cloudbot-runtime/releases/.dev_0c76cdf.staging`

The release was built from a git archive of commit `0c76cdf`.

Root runtime runners were added to staging:

- `run_sales_morning_report_from_runtime_env.sh`;
- `run_sales_focus_from_runtime_env.sh`;
- `run_sales_followup_from_runtime_env.sh`;
- `run_sales_weekly_review_from_runtime_env.sh`;
- `run_sales_morning_report_check_from_runtime_env.sh`.

Staging checks before switching symlink:

| Check | Result |
| --- | --- |
| `bash -n` for all root Sales runners | OK |
| `bash -n` for Sales workflow scripts | OK |
| `python3 -m compileall` for `apps`, `agents`, `shared`, `cloudbot`, `scripts` | OK |
| import `apps.lev_petrovich` | OK |
| import `agents.lev_petrovich` | OK |
| import `apps.lev_petrovich.legacy_sales_agent` | OK |
| import `agents.sales_agent` | OK |

Staging dry-run reports:

| Workflow | Result | Report |
| --- | --- | --- |
| Morning report | OK | `/opt/cloudbot-runtime/releases/.dev_0c76cdf.staging/reports/sales_morning_report_20260430_121817_MSK.txt` |
| Follow-up | OK | `/opt/cloudbot-runtime/releases/.dev_0c76cdf.staging/reports/sales_followup_20260430_121817_MSK.txt` |
| Weekly review | OK | `/opt/cloudbot-runtime/releases/.dev_0c76cdf.staging/reports/sales_weekly_review_20260430_121817_MSK.txt` |

Staging log evidence showed:

- `telegram_send_dry_run`;
- `route_key`: `lev-petrovich`;
- `sent_reports`: `sales`, `risks`, `focus` for morning dispatch;
- `sent_reports`: `focus` for follow-up;
- `sent_reports`: `weekly` for weekly review;
- `missing_format_markers`: `[]`.

## Cutover action

Applied at approximately `2026-04-30 12:22 МСК`.

Action:

```text
/opt/cloudbot-runtime/current -> /opt/cloudbot-runtime/releases/dev_0c76cdf
```

Only this pointer was switched.

## Post-cutover smoke

Post-cutover smoke used Telegram dry-run mode only.

No live Telegram Sales message was sent during this cutover smoke.

Generated post-cutover reports:

| Workflow | Result | Report |
| --- | --- | --- |
| Morning report | OK | `/opt/cloudbot-runtime/current/reports/sales_morning_report_20260430_122242_MSK.txt` |
| Follow-up | OK | `/opt/cloudbot-runtime/current/reports/sales_followup_20260430_122242_MSK.txt` |
| Weekly review | OK | `/opt/cloudbot-runtime/current/reports/sales_weekly_review_20260430_122242_MSK.txt` |
| Isolated morning report | OK | `/opt/cloudbot-runtime/current/reports/sales_morning_report_20260430_122450_MSK.txt` |
| Isolated morning check | OK | `/opt/cloudbot-runtime/current/reports/sales_morning_report_check_20260430_122617_MSK.txt` |

The isolated morning dispatch health report says:

```text
OK: утренняя рассылка 2026-04-30 доставила Фокус РОПа, Риски по продажам, Sales Copilot.
```

The isolated smoke log confirmed:

- Bitrix app OAuth state was readable;
- deals, meetings, briefs, tasks, and communication managers were loaded;
- Sales dispatch sequence included `sales`, `risks`, `focus`;
- follow-up generated `focus`;
- weekly generated `weekly`;
- Telegram route resolved to `lev-petrovich`;
- all delivery attempts were dry-run;
- required format markers were present.

## Expected check caveat

One direct run of `run_sales_morning_report_check_from_runtime_env.sh` against the production `sales_agent.log` returned a duplicate-sequence warning for `2026-04-30`.

Cause:

- staging and post-cutover smoke runs intentionally appended dry-run dispatch events to the existing Sales log for the same calendar day;
- the health checker saw multiple same-day smoke dispatches plus the real morning dispatch and reported order duplication.

Resolution:

- repeated the morning report and morning check against an isolated smoke log:
  `/opt/cloudbot-runtime/current/reports/sales_agent_post_cutover_smoke.log`;
- isolated health check passed;
- no rollback was required.

Next scheduled morning check is for the next business day and will not share the same same-day smoke duplicate set.

## Error checks

Checked post-cutover report files for:

- `Traceback`;
- `ModuleNotFoundError`;
- `ImportError`;
- `ERROR`;
- `FAILED`;
- `Exception`;
- `format_validation`;
- `invalid choice`.

No matching errors were found in the successful post-cutover smoke reports.

## Rollback status

Rollback target remains available:

`/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60`

Rollback was not executed because:

- pointer switch succeeded;
- imports/staging checks passed;
- morning report generated;
- follow-up generated;
- weekly review generated;
- isolated morning dispatch health passed;
- no import/runtime/format errors were found in successful smoke outputs.

## Remaining observation

Observe the next scheduled Sales jobs:

| Job | Expected schedule МСК |
| --- | --- |
| Sales follow-up | `2026-04-30 17:00` |
| Sales morning report | next weekday `09:30` |
| Sales morning check | next weekday `09:40` |
| Sales weekly review | next Friday `18:30` |

Observation must verify:

- report files under `/home/ops/cloudbot-sales-agent/reports`;
- cron logs freshness;
- `sales_agent.log`;
- Telegram delivery status;
- no `invalid choice`;
- no weekly format validation failure;
- no import/runtime errors.

## Gate conclusion

Lev/Sales controlled cutover is complete.

Current runtime state:

- Larisa is on its dedicated app release;
- Lev/Sales generic runtime is now on `dev_0c76cdf`;
- `/opt/openclaw` remains no-touch and still requires a separate server-only audit before any cleanup.
