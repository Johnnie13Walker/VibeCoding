# Apps

`apps/*` is the canonical source tree for Cloudbot application boundaries.

Current canonical apps:

- `apps/larisa_ivanovna`
- `apps/lev_petrovich`
- `apps/lev_petrovich/legacy_sales_agent`
- `apps/finansist`

Compatibility imports remain available through `agents/*`.

Rules:

- new app code goes under `apps/*`;
- do not add new production logic under `agents/*`;
- keep `agents/sales_agent` until a separate approved retirement window;
- runtime pointer, cron, env, systemd, Docker and Telegram routing changes require separate approval.
