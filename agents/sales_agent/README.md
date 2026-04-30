# agents/sales_agent

## Current status

This directory is now a compatibility shim.

Canonical implementation lives in:

`apps/lev_petrovich/legacy_sales_agent`

This layer is still required for legacy imports and runtime compatibility.

## Mandatory rules

Do NOT:

- delete this directory yet
- retire this compatibility layer silently
- break report contract imports
- break `scripts/run_sales_copilot.py`
- change live Sales / Lev runtime routing here

Retirement requires a separate approved runtime cutover and Sales smoke validation.
