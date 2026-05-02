# Compatibility layers contract — 2026-05-02 МСК

## Purpose

Fix the compatibility rules after the `apps/*` migration so cleanup can continue without breaking live imports.

## Canonical paths

| Runtime contour | Canonical path |
| --- | --- |
| Larisa Ivanovna | `apps/larisa_ivanovna` |
| Finansist | `apps/finansist` |
| Lev Petrovich | `apps/lev_petrovich` |
| Sales legacy runtime layer | `apps/lev_petrovich/legacy_sales_agent` |

## Compatibility paths

| Compatibility path | Status | Rule |
| --- | --- | --- |
| `agents/larisa_ivanovna` | shim | keep until a separate import-retirement window |
| `agents/finansist` | shim | keep until a separate import-retirement window |
| `agents/lev_petrovich` | shim | keep until a separate import-retirement window |
| `agents/sales_agent` | temporary shim | do not delete or retire silently |

## Current cleanup decision

Canonical code may import canonical `apps/*` modules directly.

Compatibility shims remain only for old external imports, old scripts and runtime safety. In particular:

- `apps/lev_petrovich/agent.py` imports Sales runtime from `apps.lev_petrovich.legacy_sales_agent`.
- `agents/sales_agent/*` still re-exports the same canonical implementation.
- `agents/sales_agent` is not an archive and not approved for deletion.

## Required checks

The compatibility contract is covered by:

`python3 -m unittest tests.integration.test_app_compatibility_contract`

Broader safety checks before any future shim cleanup:

- `python3 -m unittest discover -s tests/unit`
- `python3 -m unittest discover -s tests/integration`
- `npm test` in `bot`
- `python3 checks/smoke_test.py`

## No-touch boundaries

This contract does not change:

- runtime pointers
- env files
- cron
- systemd
- Docker
- Telegram routing
- `/opt/openclaw`
