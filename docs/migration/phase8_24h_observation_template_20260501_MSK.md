# Phase 8 24h observation template — 2026-05-01 МСК

## Status

Template prepared before scheduled cron observations.

Do not mark this document as completed until the scheduled production runs below have actually happened.

## Scope

Observe both cutover contours for scheduled production execution:

- Larisa Ivanovna runtime;
- Lev/Sales generic runtime.

No changes are allowed during observation unless an explicit rollback is approved or required by a failed smoke gate.

## Runtime pointers

| Path | Expected target | Observed target | Status |
| --- | --- | --- | --- |
| `/opt/cloudbot-runtime/larisa/current` | `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635` | `TBD` | `TBD` |
| `/opt/cloudbot-runtime/current` | `/opt/cloudbot-runtime/releases/dev_0c76cdf` | `TBD` | `TBD` |

## Scheduled run evidence

### Sales follow-up

- Expected time: `2026-04-30 17:00 МСК`
- Wrapper: `/usr/local/bin/cloudbot-sales-followup.sh`
- Expected report pattern: `/home/ops/cloudbot-sales-agent/reports/sales_followup_20260430_1700*_MSK.txt`
- Observed report: `TBD`
- Telegram delivery: `TBD`
- Error scan: `TBD`
- Verdict: `TBD`

### Larisa daily brief

- Expected time: `2026-05-01 08:00 МСК`
- Wrapper: `/usr/local/bin/cloudbot-larisa-daily-brief.sh`
- Expected report pattern: `/opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260501_0800*_MSK.txt`
- Cron log: `/home/ops/cloudbot-larisa-agent/reports/larisa_daily_brief_cron.log`
- Observed report: `TBD`
- Cron log timestamp: `TBD`
- Telegram delivery: `TBD`
- Error scan: `TBD`
- Verdict: `TBD`

### Sales morning report

- Expected time: `2026-05-01 09:30 МСК`
- Wrapper: `/usr/local/bin/cloudbot-sales-daily-brief.sh`
- Expected report pattern: `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_20260501_0930*_MSK.txt`
- Observed report: `TBD`
- Delivered report types: `TBD`
- Telegram delivery: `TBD`
- Error scan: `TBD`
- Verdict: `TBD`

### Sales morning delivery check

- Expected time: `2026-05-01 09:40 МСК`
- Wrapper: `/usr/local/bin/cloudbot-sales-morning-check.sh`
- Expected report pattern: `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_check_20260501_0940*_MSK.txt`
- Observed report: `TBD`
- Check result: `TBD`
- Error scan: `TBD`
- Verdict: `TBD`

### Sales weekly review

- Expected time: `2026-05-01 18:30 МСК`
- Wrapper: `/usr/local/bin/cloudbot-sales-weekly-review.sh`
- Expected report pattern: `/home/ops/cloudbot-sales-agent/reports/sales_weekly_review_20260501_1830*_MSK.txt`
- Observed report: `TBD`
- Required marker: `📊 Отчёт Льва Петровича по продажам`
- Telegram delivery: `TBD`
- Error scan: `TBD`
- Verdict: `TBD`

## Error scan checklist

Search fresh observation artifacts for:

- `Traceback`
- `ModuleNotFoundError`
- `ImportError`
- `ERROR`
- `FAILED`
- `Exception`
- `format_validation`
- `invalid choice`
- token/chat route errors

Record whether each match is a true failure, historical noise, or expected dry-run/manual-smoke residue.

## Delivery evidence rules

- Record Telegram delivery status and message ids if available.
- Redact chat ids and tokens.
- Do not paste secret-bearing env lines.
- Prefer report/log paths and event names over copied payloads.

## Verdict options

Use one:

- `stable` — all scheduled facts are present and fresh, no runtime/import/format/token/chat errors.
- `observe more` — scheduled facts are mostly green but there is ambiguous duplicate-log or external API noise.
- `rollback needed` — report generation, Telegram delivery, import path, format contract, or token/chat routing failed.

## Final verdict

`TBD`

## Follow-up after completion

If verdict is `stable`:

- update `docs/migration/migration_closure_package_20260430_MSK.md` checklist or create a final closure note;
- keep compatibility shims in place;
- do not start legacy cleanup without separate approval.

If verdict is `observe more`:

- document the ambiguous signal;
- schedule the next concrete observation slot in МСК.

If verdict is `rollback needed`:

- stop cleanup;
- use the relevant rollback target from `docs/migration/migration_closure_package_20260430_MSK.md`;
- document rollback and post-rollback smoke.
