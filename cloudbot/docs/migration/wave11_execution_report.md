# Wave 11 Execution Report

## Scope

Wave 11 executed one compatibility-preserving shared extraction:

- created `shared/time/moscow.py`;
- converted `agents/larisa_ivanovna/timezone.py` into a compatibility shim;
- kept current Larisa import path working.

## What Changed

Canonical Moscow-time helpers now live in:

- `shared/time/moscow.py`

Current Larisa compatibility path remains:

- `agents/larisa_ivanovna/timezone.py`

The compatibility path still exposes:

- `MOSCOW_TZ`
- `to_moscow_datetime`
- `normalize_to_moscow`
- `extract_moscow_clock`
- `ensure_moscow_datetime`

## What Did Not Change

Wave 11 did not change:

- Larisa business logic;
- `cloudbot/workflows/larisa_runtime.py`;
- calendar provider behavior;
- tasks provider behavior;
- Telegram delivery behavior;
- env files;
- cron files;
- systemd units;
- docker configuration;
- runtime pointers;
- deploy / rollback / verify scripts.

## Compatibility Confirmation

The old import path remains valid:

- `agents.larisa_ivanovna.timezone`

The new shared import path is available:

- `shared.time.moscow`

Existing runtime code can continue using the old path until a separate import migration is approved.

## Validation

Checks completed after the move:

- `py_compile` passed for both old and new modules;
- direct old/new import equivalence check passed;
- Larisa integration test discovery passed;
- unit discovery passed;
- full integration discovery passed.

## Status

Wave 11 Larisa timezone shared extraction completed.
