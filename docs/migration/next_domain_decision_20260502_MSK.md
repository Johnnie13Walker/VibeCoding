# Next domain decision — 2026-05-02 МСК

## Decision

Next migration domain:

`wrapper cutover design for python -m agents.*`

## Why this domain

The source tree is now canonical under `apps/*`, and production app code no longer needs `agents.sales_agent` imports.

Remaining `agents/*` usage is mostly compatibility CLI surface:

- `python3 -m agents.larisa_ivanovna`
- `python3 -m agents.lev_petrovich`
- `python3 -m agents.finansist`
- formatter metadata string `agents.sales_agent.sales_formatter`

This is a narrower and safer next domain than broad shared extraction.

## Scope

In scope:

- design canonical CLI equivalents for `python -m apps.larisa_ivanovna`;
- design canonical CLI equivalents for `python -m apps.lev_petrovich`;
- map server wrappers that still call `python -m agents.*`;
- add tests for canonical CLI entrypoints;
- keep compatibility wrappers for one release window;
- document rollback.

Out of scope:

- deleting `agents/sales_agent`;
- deleting any `agents/*` shim;
- changing env, cron, systemd, Docker or Telegram routing;
- changing runtime pointers;
- touching `/opt/openclaw`;
- broad shared extraction.

## Entry criteria

- `tests.integration.test_app_compatibility_contract` green.
- `tests.integration.test_agents_import_guard` green.
- `tests.integration.test_release_packaging_contract` green.
- `python3 checks/smoke_test.py` green.

## Exit criteria

- Canonical CLI checks exist for `apps.larisa_ivanovna` and `apps.lev_petrovich`.
- Server wrapper call sites are mapped.
- Compatibility CLI `python -m agents.*` remains working.
- No production imports are reintroduced through `agents.*`.
- No runtime pointer/env/cron/systemd/Docker changes are made without separate approval.

## Verdict

Proceed next with design and tests for wrapper cutover.

Do not start `agents/sales_agent` retirement yet.
