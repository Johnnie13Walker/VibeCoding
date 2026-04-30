# Sales / Lev Runtime Bridge Map

Дата фиксации: 2026-04-28 МСК.

Статус: read-only bridge map. Этот документ не меняет `scripts/run_sales_copilot.py`, runtime, env или Telegram routing.

## 1. Bridge file

```text
scripts/run_sales_copilot.py
```

## 2. Confirmed imports and calls

| Line area | Confirmed behavior |
| --- | --- |
| `agents.sales_agent.report_contract` | imports `SALES_RUNTIME_REPORT_TYPES` and `sales_followup_report_types` |
| remote token file | has default `/root/.openclaw/telegram/commercial-director.bot_token` |
| subprocess path | calls `python -m agents.lev_petrovich --report <type>` |
| in-process path | imports `build_sales_report_from_env` from `agents.lev_petrovich.agent` |
| Telegram delivery | resolves bot token/chat ids inside bridge |
| followups | builds risks/focus followups through report contract |

## 3. Tests covering bridge

Confirmed tests:

```text
tests/test_lev_petrovich_runtime.py::_build_followup_messages
tests/test_lev_petrovich_runtime.py::_run_sales_agent
```

These tests patch `scripts.run_sales_copilot.subprocess.run`, so they protect bridge behavior without live runtime.

## 4. Migration risk

Bridge is high-risk because it connects:

- `agents.sales_agent.report_contract`;
- `agents.lev_petrovich`;
- Telegram token/chat routing;
- followup report sequence;
- local and possible runtime execution modes.

## 5. Blocked changes

Blocked without separate approval:

- moving `scripts/run_sales_copilot.py`;
- changing imports in the bridge;
- changing `python -m agents.lev_petrovich`;
- changing token file path;
- changing Telegram chat fallback;
- changing followup report order.

## 6. Required before any bridge migration

Required:

1. Explicit replacement entrypoint.
2. Compatibility wrapper strategy.
3. Tests for `_run_sales_agent` and `_build_followup_messages`.
4. Sales smoke checklist.
5. Rollback plan with no runtime pointer changes.

## 7. Verdict

```text
runtime bridge is live-sensitive
do not move
next safe step: report contract map
```
