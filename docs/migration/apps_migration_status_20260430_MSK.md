# Apps migration status — 2026-04-30 МСК

## Current canonical app paths

| App | Canonical path | Compatibility path | Status |
| --- | --- | --- | --- |
| Larisa Ivanovna | `apps/larisa_ivanovna` | `agents/larisa_ivanovna` | migrated locally with compatibility shims |
| Finansist | `apps/finansist` | `agents/finansist` | migrated locally with compatibility shims |
| Lev Petrovich / Sales Copilot | `apps/lev_petrovich` | `agents/lev_petrovich` | migrated locally with compatibility shims |
| Sales Agent legacy layer | `apps/lev_petrovich/legacy_sales_agent` | `agents/sales_agent` | migrated locally with compatibility shims |

## Runtime note

Local source migration does not change live server runtime pointers.

The following live paths remain separate runtime concerns:

- `/opt/cloudbot-runtime/larisa/current`
- `/opt/cloudbot-runtime/current`
- `/opt/openclaw`
- `/etc/openclaw`

## Compatibility rules

- Old imports through `agents.larisa_ivanovna.*` must keep working.
- Old imports through `agents.finansist.*` must keep working.
- Old imports and CLI entrypoint through `agents.lev_petrovich.*` must keep working.
- Old imports through `agents.sales_agent.*` must keep working.
- CLI wrappers in `scripts/finansist_*.mjs` must keep working.
- `agents/sales_agent` remains a temporary compatibility layer, not an archive.
- Server runtime cutover is not part of these local source commits.

## Tests passed after migration

- `python3 -m unittest tests.integration.test_larisa_agent tests.integration.test_larisa_search`
- `python3 -m unittest discover -s tests/unit`
- `python3 checks/smoke_test.py`
- targeted import compatibility checks for `apps.*` and `agents.*`
- `python3 -m unittest tests.integration.test_lev_petrovich_runtime tests.integration.test_sales_dispatch_contract`

## Next candidates

| Candidate | Risk | Required checks |
| --- | --- | --- |
| shared extraction | high | full import map and broad regression suite |
