# apps/lev_petrovich/legacy_sales_agent

## Current status

This is the canonical local source path for the legacy Sales Agent compatibility layer.

Legacy imports remain available through:

`agents/sales_agent`

## Boundary

This directory owns the existing Sales Agent report contract and formatter logic while Lev Petrovich runtime remains compatible with it.

## Runtime note

Moving local source here does not retire the compatibility layer and does not change live runtime pointers, cron, env, systemd, Docker, or deploy scripts.
