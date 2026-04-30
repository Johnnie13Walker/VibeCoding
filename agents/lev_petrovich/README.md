# agents/lev_petrovich

## Current status

This directory is now a compatibility shim.

Canonical implementation lives in:

`apps/lev_petrovich`

Do not add new production logic here.

## Mandatory rules

Do NOT:

- delete this compatibility layer yet
- break `python -m agents.lev_petrovich`
- retire `agents/sales_agent`
- change Sales / Lev runtime routing here

Existing Sales bridge paths must keep working until a separate runtime cutover is approved.
