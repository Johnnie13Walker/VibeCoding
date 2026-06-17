# Wave 12 Business Day Report

## Scope

Wave 12 executed one compatibility-preserving shared extraction:

- created `shared/time/business_day.py`;
- converted `cloudbot/business_day.py` into a compatibility shim;
- preserved all existing imports from `cloudbot.business_day`.

## Current Canonical Path

Canonical business-day helpers now live in:

- `shared/time/business_day.py`

Compatibility path remains:

- `cloudbot/business_day.py`

## Preserved API

The compatibility path still exposes:

- `MOSCOW_TZ`
- `_anchor_business_day`
- `_as_date`
- `_as_moscow_datetime`
- `current_business_week`
- `current_business_week_window`
- `previous_business_day`
- `previous_business_week_window`
- `report_day_flags`

## What Did Not Change

Wave 12 did not change:

- Sales / Lev business behavior;
- Larisa business behavior;
- runtime imports in callers;
- env files;
- cron files;
- systemd units;
- docker configuration;
- deploy / rollback / verify scripts;
- runtime pointers.

## Validation

Checks completed after the move:

- `py_compile` passed for old and new modules;
- direct old/new import compatibility check passed;
- unit discovery passed;
- integration discovery passed.

## Status

Wave 12 business-day shared extraction completed.
