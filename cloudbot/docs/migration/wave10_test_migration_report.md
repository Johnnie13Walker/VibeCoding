# Wave 10 Test Migration Report

## Scope

Wave 10 moved production-facing runtime tests into the integration test area.

Moved files:

- `tests/test_larisa_agent.py` -> `tests/integration/test_larisa_agent.py`
- `tests/test_lev_petrovich_runtime.py` -> `tests/integration/test_lev_petrovich_runtime.py`

## What Changed

Only test layout changed.

One test fixture path was updated after the move:

- `tests/integration/test_lev_petrovich_runtime.py`

Reason:

- before the move, the test resolved `tests/fixtures` through `Path(__file__).with_name("fixtures")`;
- after the move, that expression pointed to `tests/integration/fixtures`;
- the real fixture location remains `tests/fixtures`.

## What Did Not Change

Wave 10 did not change:

- production code;
- runtime imports;
- env files;
- cron files;
- systemd units;
- docker configuration;
- runtime pointers;
- deploy / rollback / verify scripts;
- `agents/sales_agent` compatibility status.

## Validation

Checks completed during the wave:

- `test_larisa_agent` passed before and after the move;
- `test_lev_petrovich_runtime` passed before the move;
- after the move, one fixture-path failure was found and fixed in the moved test file;
- `test_lev_petrovich_runtime` passed after the fixture-path correction;
- unit discovery passed;
- integration discovery passed.

## Current Test Layout

Unit tests:

- `tests/unit/`

Integration tests:

- `tests/integration/`

Shared fixtures:

- `tests/fixtures/`

## Status

Wave 10 test migration completed.
