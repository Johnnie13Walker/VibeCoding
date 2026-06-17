# Wave 11 Larisa Time Candidate

## Candidate

Move Larisa Moscow-time normalization helpers into shared time utilities while preserving the current Larisa import path.

Current path:

- `agents/larisa_ivanovna/timezone.py`

Candidate target:

- `shared/time/moscow.py`

## Current Public API

The current Larisa module exposes:

- `MOSCOW_TZ`
- `to_moscow_datetime`
- `normalize_to_moscow`
- `extract_moscow_clock`
- `ensure_moscow_datetime`

The internal helper `_resolve_timezone` is implementation detail.

## Known Current Reference

Confirmed current import:

- `cloudbot/workflows/larisa_runtime.py` imports `ensure_moscow_datetime` from `agents.larisa_ivanovna.timezone`.

## Required Compatibility

The old path must remain import-compatible:

- `agents.larisa_ivanovna.timezone`

The new shared module must not require runtime, env, cron, systemd, docker, or server changes.

## Out Of Scope

Wave 11 must not change:

- Larisa business logic;
- calendar provider behavior;
- tasks provider behavior;
- Telegram routing;
- cron timing;
- runtime pointers;
- live env files.

## Proposed Safe Move

1. Create `shared/time/moscow.py` with the same Moscow-time helpers.
2. Turn `agents/larisa_ivanovna/timezone.py` into a compatibility shim.
3. Keep `cloudbot/workflows/larisa_runtime.py` unchanged.
4. Validate old and new imports return equivalent behavior.

## Safety Reasoning

This is safe only if:

- the old import path continues to work;
- helper behavior remains byte-for-byte equivalent at the API level;
- integration tests for Larisa pass after the move;
- no runtime or deployment files are touched.

## Status

Candidate prepared for owner-approved execution.
