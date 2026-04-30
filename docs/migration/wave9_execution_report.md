# Wave 9 Execution Report

## Scope

Wave 9 executed one production-adjacent structural move:

- created `shared/contracts/sales_report_format_contract.py`;
- kept `agents/sales_agent/sales_formatter.py` as the compatibility import path for formatter metadata;
- preserved the public names used by existing Sales / Lev code:
  - `SALES_REPORT_FORMAT_VERSION`
  - `FORMATTER_MODULE`
  - `REPORT_FORMATS`
  - `REPORT_REQUIRED_MARKERS`
  - `report_format_metadata`
  - `report_required_markers`

## What Changed

The canonical formatter metadata contract now lives in:

- `shared/contracts/sales_report_format_contract.py`

The existing formatter path still exposes the same names through imports:

- `agents/sales_agent/sales_formatter.py`

## Compatibility Rules

- Existing imports from `agents.sales_agent.sales_formatter` must continue to work.
- `agents/sales_agent` remains the current temporary compatibility layer.
- This wave does not retire, move, or delete `agents/sales_agent`.
- This wave does not change rendering behavior.
- This wave does not change report contract dispatch behavior.

## Explicit No-Touch Confirmation

The following areas were not changed in Wave 9:

- live runtime paths;
- env files;
- cron files;
- systemd units;
- docker configuration;
- deploy / rollback / verify scripts;
- Telegram token or chat routing;
- Larisa business logic;
- Lev / Sales runtime behavior.

## Validation

Required validation after this move:

- unit test discovery must pass;
- integration test discovery must pass;
- Lev / Sales runtime tests must pass;
- the new shared contract and compatibility import path must compile;
- old and new formatter metadata imports must return equivalent values.

## Status

Wave 9 formatter metadata move completed.
