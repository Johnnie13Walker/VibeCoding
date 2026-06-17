# Wave 15 Root Tests Review

## Scope

Wave 15 reviewed remaining root-level test files for safe migration into `tests/unit/` or `tests/integration/`.

## Remaining Root Test

- `tests/unit/test_finansist_agent.py`

## Decision

Do not move this test in the current migration wave.

Reason:

- the test belongs to the finance contour;
- finance contour is explicitly excluded from the current OpenCloud / Cloudbot structural migration scope;
- moving this test now would mix the approved migration track with a separate finance track.

## What Was Not Changed

No files were moved in this wave.

No code was changed.

No runtime, env, cron, systemd, docker, deploy, rollback, or verify files were touched.

## Required Separate Track

Before moving `tests/unit/test_finansist_agent.py`, create a separate finance test-layout decision:

- confirm finance contour ownership;
- decide whether finance tests belong in this repo's `tests/integration/`;
- run finance-specific checks;
- approve the move outside the current shared-core migration wave.

## Validation

Required validation after this review:

- unit discovery must pass;
- integration discovery must pass.

## Status

Root test migration reviewed. No safe root test move is available in the current scope.
