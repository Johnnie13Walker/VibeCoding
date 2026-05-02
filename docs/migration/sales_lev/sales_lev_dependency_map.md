# Sales / Lev Dependency Map

Дата фиксации: 2026-05-02 МСК.

Статус: dependency map after `apps/*` cutover. Этот документ не меняет runtime, env, cron/systemd/docker или deploy.

## 1. Current practical role

`apps/lev_petrovich` является canonical Lev/Sales entrypoint.

`apps/lev_petrovich/legacy_sales_agent` является canonical implementation path для Sales legacy runtime layer.

`agents/sales_agent` остается active temporary compatibility layer для старых импортов. Его нельзя удалять или retire без отдельного approval.

## 2. Confirmed dependencies

| Area | Confirmed dependency | Risk |
| --- | --- | --- |
| `apps/lev_petrovich/agent.py` | imports `apps.lev_petrovich.legacy_sales_agent.sales_agent` | canonical Lev facade is backed by canonical SalesAgent |
| `apps/lev_petrovich/legacy_sales_agent/sales_agent.py` | imports `apps.lev_petrovich.telegram_route` | Sales route dependency is now canonical, not shim-based |
| `agents/lev_petrovich/*` | re-exports `apps.lev_petrovich.*` | old imports and `python -m agents.lev_petrovich` remain compatible |
| `agents/sales_agent/*` | re-exports `apps.lev_petrovich.legacy_sales_agent.*` | old Sales imports remain compatible |
| `scripts/run_sales_copilot.py` | imports canonical report contract from `apps.lev_petrovich.legacy_sales_agent.report_contract` | script is on canonical path |
| `cloudbot/devops/sales_dispatch_health.py` | uses shared contracts and formatter metadata | dispatch health no longer requires old Sales import paths |
| `tests/integration/test_app_compatibility_contract.py` | imports both canonical paths and shims | tests lock compatibility behavior |
| `tests/integration/test_sales_dispatch_contract.py` | imports canonical report contract | report contract is no longer pinned to `agents/sales_agent` |

## 3. Live-critical surfaces

Treat these as live-critical until proven otherwise:

```text
apps/lev_petrovich/agent.py
apps/lev_petrovich/telegram_route.py
apps/lev_petrovich/legacy_sales_agent/sales_agent.py
apps/lev_petrovich/legacy_sales_agent/report_contract.py
apps/lev_petrovich/legacy_sales_agent/sales_formatter.py
scripts/run_sales_copilot.py
cloudbot/devops/sales_dispatch_health.py
agents/sales_agent/*
agents/lev_petrovich/*
```

## 4. Blocked actions

Blocked:

- retiring `agents/sales_agent`;
- deleting `agents/sales_agent`;
- changing Sales runtime event/report semantics without approval;
- changing Sales Telegram routing;
- changing report formatting contract.

## 5. Required before retirement

Before any retirement track:

1. Prove no live/runtime import still requires `agents.sales_agent.*`.
2. Prove no external script still invokes `python -m agents.lev_petrovich`.
3. Keep a compatibility shim strategy for one release window.
4. Validate `scripts/run_sales_copilot.py`.
5. Validate Sales dispatch health.
6. Run Lev/Sales smoke checklist.
7. Document rollback plan without runtime pointer changes.

## 6. Verdict

```text
apps/lev_petrovich is canonical
apps/lev_petrovich/legacy_sales_agent is canonical Sales legacy implementation
agents/sales_agent remains compatibility layer
retirement still blocked
```
