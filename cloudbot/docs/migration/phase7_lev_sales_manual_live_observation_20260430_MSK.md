# Phase 7 Lev/Sales manual live observation — 2026-04-30 МСК

## Status

Manual live observation completed successfully.

This was done to confirm Lev/Sales live Telegram delivery without waiting for the next scheduled cron slots.

## Scope

Executed manually through existing production wrappers:

- `/usr/local/bin/cloudbot-sales-followup.sh`;
- `/usr/local/bin/cloudbot-sales-weekly-review.sh`;
- `/usr/local/bin/cloudbot-sales-daily-brief.sh`.

Not changed:

- `/opt/cloudbot-runtime/current`;
- `/opt/cloudbot-runtime/larisa/current`;
- `/opt/openclaw`;
- env files;
- cron files;
- systemd units;
- Docker runtime;
- Telegram token/chat routing;
- `agents/sales_agent` compatibility layer.

## Runtime baseline

Checked before manual live observation:

| Path | Target |
| --- | --- |
| `/opt/cloudbot-runtime/current` | `/opt/cloudbot-runtime/releases/dev_0c76cdf` |
| `/opt/cloudbot-runtime/larisa/current` | `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635` |

## Live executions

| Wrapper | Start МСК | Finish МСК | Result | Report |
| --- | --- | --- | --- | --- |
| `/usr/local/bin/cloudbot-sales-followup.sh` | `2026-04-30 12:45:17` | `2026-04-30 12:46:28` | OK | `/home/ops/cloudbot-sales-agent/reports/sales_followup_20260430_124517_MSK.txt` |
| `/usr/local/bin/cloudbot-sales-weekly-review.sh` | `2026-04-30 12:46:39` | `2026-04-30 12:48:14` | OK | `/home/ops/cloudbot-sales-agent/reports/sales_weekly_review_20260430_124639_MSK.txt` |
| `/usr/local/bin/cloudbot-sales-daily-brief.sh` | `2026-04-30 12:50:19` | `2026-04-30 12:51:18` | OK | `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_20260430_125019_MSK.txt` |

## Telegram delivery evidence

Sales follow-up:

- route: `lev-petrovich`;
- report type: `focus`;
- event: `telegram_send_ok`;
- chunks: `1`;
- message ids: `438`;
- missing format markers: `[]`.

Sales weekly:

- route: `lev-petrovich`;
- report type: `weekly`;
- event: `telegram_send_ok`;
- chunks: `2`;
- message ids: `439`, `440`;
- missing format markers: `[]`;
- required marker present: `📊 Отчёт Льва Петровича по продажам`.

Sales morning package:

- route: `lev-petrovich`;
- report types delivered: `sales`, `risks`, `focus`;
- events: `telegram_send_ok`;
- message ids:
  - `sales`: `441`, `442`;
  - `risks`: `443`;
  - `focus`: `444`;
- dispatch complete: `ok: true`;
- sent reports: `sales`, `risks`, `focus`;
- missing format markers: `[]`.

Chat id values remained masked in logs and are not recorded in this document.

## Error checks

Checked fresh live reports for:

- `Traceback`;
- `ModuleNotFoundError`;
- `ImportError`;
- `ERROR`;
- `FAILED`;
- `Exception`;
- `format_validation`;
- `invalid choice`.

No matching errors were found in:

- `/home/ops/cloudbot-sales-agent/reports/sales_followup_20260430_124517_MSK.txt`;
- `/home/ops/cloudbot-sales-agent/reports/sales_weekly_review_20260430_124639_MSK.txt`;
- `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_20260430_125019_MSK.txt`.

## Morning check note

The normal morning check wrapper was not used as the live observation signal in this phase.

Reason:

- earlier staging and post-cutover smoke runs on `2026-04-30` intentionally wrote multiple dry-run dispatch records into the same production `sales_agent.log`;
- the checker can report duplicate same-day sequence noise when the same day contains real scheduled dispatch, dry-run smoke dispatches, and manual live observation dispatch.

The morning dispatch contract itself was already verified after cutover with an isolated smoke log:

`/opt/cloudbot-runtime/current/reports/sales_morning_report_check_20260430_122617_MSK.txt`

Live delivery is confirmed directly by `telegram_send_ok` events and message ids in `sales_agent.log`.

## Verdict

Manual live observation confirms that the new Lev/Sales runtime `dev_0c76cdf` can:

- generate and send Sales follow-up;
- generate and send weekly review without format validation failure;
- generate and send the morning package with `sales`, `risks`, and `focus`;
- use the expected `lev-petrovich` Telegram route;
- read live Bitrix app state.

Rollback is not needed.

Remaining scheduled observation:

- next cron-driven Sales follow-up at `2026-04-30 17:00 МСК`;
- next weekday morning report/check at `09:30/09:40 МСК`;
- next Friday weekly review at `18:30 МСК`.
