# apps/lev_petrovich

## Current status

This is the canonical local source path for Lev Petrovich / Sales Copilot code.

Legacy compatibility imports remain available through:

`agents/lev_petrovich`

## Compatibility boundary

`agents/sales_agent` remains a separate temporary compatibility layer.

Do not retire or move `agents/sales_agent` as part of this app move.

## Runtime note

Moving local source here does not change live runtime pointers, cron, env, systemd, Docker, or deploy scripts.
