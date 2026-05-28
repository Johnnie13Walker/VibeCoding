# Next Production Move Gate

## Current State

Completed safe structural moves:

- Sales report dispatch contract extracted to `shared/contracts/sales_report_contract.py`;
- Sales formatter metadata contract extracted to `shared/contracts/sales_report_format_contract.py`;
- Larisa Moscow-time helpers extracted to `shared/time/moscow.py`;
- production-facing tests moved into `tests/integration/`;
- old import paths remain compatibility shims.

## Required Gate Before Next Move

The next production-adjacent move is allowed only if all checks are true:

- unit tests pass;
- integration tests pass;
- old and new compatibility import paths pass direct equivalence checks;
- no runtime, env, cron, systemd, docker, deploy, rollback, or verify files are touched;
- `agents/sales_agent` remains a temporary compatibility layer;
- no finance, iOS, HAPP/VPN, subscription, or server-only integration work is mixed into the move.

## Recommended Next Candidate

Candidate:

- consolidate a small, read-only shared constant/helper already proven by tests.

Preferred zones:

- one small Sales / Lev contract helper;
- one small Larisa helper;
- one small test-only layout cleanup.

Do not start with:

- moving `agents/*`;
- moving `cloudbot/orchestrator`;
- moving `cloudbot/providers`;
- changing runtime imports;
- changing cron/env/systemd/docker;
- deleting or retiring `agents/sales_agent`.

## Execution Rule

Every next move must be:

- single-purpose;
- reversible;
- compatibility-preserving;
- covered by a before/after test;
- documented in `docs/migration/`.

## Stop Conditions

Stop the wave immediately if:

- any test fails and cannot be fixed without touching runtime or business logic;
- a move requires live env or server access;
- a hidden import dependency appears;
- a change would require deleting or retiring `agents/sales_agent`;
- a change affects deploy / rollback / verify scripts.

## Status

Next production move is gated. Do not execute it without explicit approval.
