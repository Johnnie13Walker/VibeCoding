# Phase 8 24h observation — 2026-05-01 МСК

## Status

Scheduled production observation completed successfully.

This document records the real cron-driven runs after Larisa and Lev/Sales production cutover. Observation was read-only: no runtime pointer, env, cron, systemd, Docker, Telegram routing, `/opt/openclaw`, or compatibility layer was changed by this observation.

## Runtime pointers

| Path | Observed target | Status |
| --- | --- | --- |
| `/opt/cloudbot-runtime/larisa/current` | `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635` | OK |
| `/opt/cloudbot-runtime/current` | `/opt/cloudbot-runtime/releases/dev_01eeee5` | OK with note |

Pointer note:

- Lev/Sales cutover was originally performed to `/opt/cloudbot-runtime/releases/dev_0c76cdf`.
- At final observation time, the generic runtime pointer resolved to `/opt/cloudbot-runtime/releases/dev_01eeee5`.
- Commits after `0c76cdf` through `01eeee5` are documentation-only migration records:
  - `c3ce5e5 docs: add lev sales cutover approval package`
  - `555d4db docs: record lev sales cutover`
  - `828b5a5 docs: record lev sales live observation`
  - `41d95a0 docs: record openclaw server audit`
  - `01eeee5 docs: prepare migration closure package`
- The scheduled Sales runs below completed successfully on the observed `dev_01eeee5` runtime.

## Scheduled run evidence

### Sales follow-up

- Expected time: `2026-04-30 17:00 МСК`
- Wrapper: `/usr/local/bin/cloudbot-sales-followup.sh`
- Observed report: `/home/ops/cloudbot-sales-agent/reports/sales_followup_20260430_170001_MSK.txt`
- Report timestamp: `2026-04-30 17:00:53 МСК`
- Runtime pointer at observation: `/opt/cloudbot-runtime/releases/dev_0c76cdf`
- Telegram delivery: OK
- Route: `lev-petrovich`
- Report type: `focus`
- Message id: `445`
- Error scan: no `Traceback`, `ModuleNotFoundError`, `ImportError`, `ERROR`, `FAILED`, `Exception`, `format_validation`, or `invalid choice`
- Verdict: OK

### Larisa daily brief

- Expected time: `2026-05-01 08:00 МСК`
- Wrapper: `/usr/local/bin/cloudbot-larisa-daily-brief.sh`
- Observed report: `/opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260501_080001_MSK.txt`
- Report timestamp: `2026-05-01 08:00:19 МСК`
- Cron log: `/home/ops/cloudbot-larisa-agent/reports/larisa_daily_brief_cron.log`
- Cron log timestamp: `2026-05-01 08:00:19 МСК`
- Runtime pointer: `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635`
- Telegram delivery: `delivered: true`
- Route: `larisa-ivanovna`
- Error scan: no import/runtime/token/chat errors in the fresh report or cron log
- Verdict: OK

### Sales morning report

- Expected time: `2026-05-01 09:30 МСК`
- Wrapper: `/usr/local/bin/cloudbot-sales-daily-brief.sh`
- Observed report: `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_20260501_093001_MSK.txt`
- Report timestamp: `2026-05-01 09:30:48 МСК`
- Runtime pointer: `/opt/cloudbot-runtime/releases/dev_0c76cdf` at morning observation
- Delivered report types:
  - `sales`: message ids `446`, `447`
  - `risks`: message id `448`
  - `focus`: message id `449`
- Route: `lev-petrovich`
- Dispatch complete: `ok: true`
- Sent reports: `sales`, `risks`, `focus`
- Missing format markers: `[]`
- Error scan: no import/runtime/format errors
- Verdict: OK

### Sales morning delivery check

- Expected time: `2026-05-01 09:40 МСК`
- Wrapper: `/usr/local/bin/cloudbot-sales-morning-check.sh`
- Observed report: `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_check_20260501_094001_MSK.txt`
- Report timestamp: `2026-05-01 09:40:01 МСК`
- Check result: `OK: утренняя рассылка 2026-05-01 доставила Фокус РОПа, Риски по продажам, Sales Copilot.`
- Error scan: no import/runtime/format errors
- Verdict: OK

### Sales weekly review

- Expected time: `2026-05-01 18:30 МСК`
- Wrapper: `/usr/local/bin/cloudbot-sales-weekly-review.sh`
- Observed report: `/home/ops/cloudbot-sales-agent/reports/sales_weekly_review_20260501_183001_MSK.txt`
- Report timestamp: `2026-05-01 18:31:17 МСК`
- Runtime pointer at observation: `/opt/cloudbot-runtime/releases/dev_01eeee5`
- Required marker: `📊 Отчёт Льва Петровича по продажам`
- Marker status: present
- Telegram delivery: OK
- Route: `lev-petrovich`
- Message ids: `455`, `456`
- Dispatch complete: `ok: true`
- Sent reports: `weekly`
- Missing format markers: `[]`
- Error scan: no `Traceback`, `ModuleNotFoundError`, `ImportError`, `ERROR`, `FAILED`, `Exception`, `format_validation`, or `invalid choice`
- Verdict: OK

## Error scan summary

Fresh scheduled artifacts were checked for:

- `Traceback`
- `ModuleNotFoundError`
- `ImportError`
- `ERROR`
- `FAILED`
- `Exception`
- `format_validation`
- `invalid choice`
- token/chat routing errors

No active failure was found in the observed scheduled reports.

Historical `format_validation` failures remain visible in older logs from before the Lev/Sales dry-run fix. They are not part of the fresh scheduled observation.

## Boundary checks

Confirmed not changed by this observation:

- `/opt/openclaw`
- env files
- cron files
- systemd units
- Docker runtime
- Telegram token/chat routing
- `agents/sales_agent` compatibility layer

## Verdict

`stable`

Cloudbot apps migration is complete for Larisa and Lev/Sales production runtime observation. Canonical source is `apps/*`, compatibility shims remain in place, `agents/sales_agent` remains active as a temporary compatibility layer, and OpenClaw remains a separate server-only contour.

## Remaining follow-up tracks

Do not perform these as part of this observation document:

1. Legacy compatibility cleanup planning for `agents/*`.
2. Separate approval package before any `agents/sales_agent` retirement track.
3. OpenClaw server-only cleanup/extraction based on `openclaw_server_only_audit_20260430_MSK.md`.
4. Daily health report classification cleanup so Bitrix/Todo/WHOOP are not incorrectly marked as unconfigured when runtime evidence shows active use.
