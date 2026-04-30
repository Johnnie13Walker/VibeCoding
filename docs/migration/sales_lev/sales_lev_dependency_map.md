# Sales / Lev Dependency Map

Дата фиксации: 2026-04-28 МСК.

Статус: read-only dependency map. Этот документ не меняет `agents/*`, imports, runtime, env, cron/systemd/docker или deploy.

## 1. Current practical role

`agents/sales_agent` остается active temporary compatibility layer для Lev/Sales.

Его нельзя удалять, переносить или retire в текущей миграционной волне.

## 2. Confirmed dependencies

| Area | Confirmed dependency | Risk |
| --- | --- | --- |
| `agents/lev_petrovich/agent.py` | imports `agents.sales_agent.sales_agent` | Lev facade is currently backed by SalesAgent |
| `agents/sales_agent/sales_agent.py` | imports `agents.lev_petrovich.telegram_route` | two-way coupling between Sales and Lev route |
| `scripts/run_sales_copilot.py` | imports `agents.sales_agent.report_contract` and calls `agents.lev_petrovich` module | runtime bridge depends on current paths |
| `cloudbot/devops/sales_dispatch_health.py` | imports `agents.sales_agent.report_contract`, `agents.sales_agent.sales_formatter`, `agents.lev_petrovich.telegram_route` | dispatch health depends on Sales/Lev compatibility |
| `tests/test_lev_petrovich_runtime.py` | imports `agents.lev_petrovich`, `agents.sales_agent.*`, `scripts.run_sales_copilot` | tests lock current compatibility paths |
| `tests/test_sales_dispatch_contract.py` | imports `agents.sales_agent.report_contract` | report contract is still under sales_agent |

## 3. Live-critical surfaces

Treat these as live-critical until proven otherwise:

```text
agents/sales_agent/sales_agent.py
agents/sales_agent/report_contract.py
agents/sales_agent/sales_formatter.py
agents/lev_petrovich/agent.py
agents/lev_petrovich/telegram_route.py
scripts/run_sales_copilot.py
cloudbot/devops/sales_dispatch_health.py
```

## 4. Blocked actions

Blocked:

- moving `agents/sales_agent`;
- retiring `agents/sales_agent`;
- rewriting `agents.sales_agent.*` imports;
- moving `report_contract.py`;
- changing `scripts/run_sales_copilot.py`;
- changing Sales Telegram routing;
- changing report formatting contract.

## 5. Required before retirement

Before any retirement track:

1. Replacement Lev/Sales entrypoint.
2. Replacement report contract location.
3. Compatibility shim strategy.
4. `scripts/run_sales_copilot.py` bridge validation.
5. Sales dispatch health validation.
6. Lev/Sales smoke checklist.
7. Rollback plan without runtime pointer changes.

## 6. Verdict

```text
sales_agent remains compatibility layer
retirement blocked
next safe step: runtime bridge map
```
