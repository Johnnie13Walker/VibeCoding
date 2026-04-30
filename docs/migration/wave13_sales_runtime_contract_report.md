# Wave 13 Sales Runtime Contract Report

## Scope

Wave 13 executed one small Sales / Lev bridge contract extraction:

- created `shared/contracts/sales_runtime_contract.py`;
- moved bridge `REPORT_TYPES` into the shared contract;
- moved bridge `REMOTE_ENV_KEYS` into the shared contract;
- kept `scripts/run_sales_copilot.py` as the runtime bridge entrypoint.

## What Changed

Canonical Sales bridge contract path:

- `shared/contracts/sales_runtime_contract.py`

Runtime bridge path remains:

- `scripts/run_sales_copilot.py`

The bridge still exposes the same imported globals:

- `REPORT_TYPES`
- `REMOTE_ENV_KEYS`

## What Did Not Change

Wave 13 did not change:

- remote host values;
- remote env file path;
- remote state path;
- token file path;
- Telegram delivery logic;
- report rendering;
- live env files;
- cron files;
- systemd units;
- docker configuration;
- deploy / rollback / verify scripts;
- runtime pointers.

## Validation

Checks completed after the move:

- `py_compile` passed for the shared contract and bridge script;
- direct script/shared contract equivalence check passed;
- Lev / Sales runtime tests passed;
- unit discovery passed;
- integration discovery passed.

## Status

Wave 13 Sales runtime contract extraction completed.
