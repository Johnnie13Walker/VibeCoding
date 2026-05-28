# Wave 14 Telegram Routing Contract Report

## Scope

Wave 14 executed one minimal Telegram routing helper extraction:

- created `shared/contracts/telegram_routing_contract.py`;
- moved chat id normalization into `normalize_chat_id`;
- kept old local wrapper in `scripts/run_sales_copilot.py`;
- kept Sales runtime chat resolution behavior in `agents/sales_agent/sales_agent.py`.

## What Changed

Canonical helper path:

- `shared/contracts/telegram_routing_contract.py`

The helper normalizes values like:

- `telegram:-123` -> `-123`
- ` 42 ` -> `42`

## What Did Not Change

Wave 14 did not change:

- Telegram token selection;
- Telegram chat fallback order;
- Sales weekly chat behavior;
- Sales daily chat behavior;
- Larisa Telegram routing;
- live env files;
- cron files;
- systemd units;
- docker configuration;
- deploy / rollback / verify scripts;
- runtime pointers.

## Validation

Checks completed after the move:

- `py_compile` passed for shared helper and touched callers;
- direct old/new normalization check passed;
- Lev / Sales runtime tests passed;
- unit discovery passed;
- integration discovery passed.

## Status

Wave 14 Telegram routing helper extraction completed.
