# Workflow Boundary Map

Дата фиксации: 2026-04-28 МСК.

Статус: read-only workflow boundary map. Этот документ не меняет workflows or routing.

## 1. Current workflow area

```text
cloudbot/workflows/
```

## 2. Boundary groups

| Group | Files | Risk |
| --- | --- | --- |
| Larisa workflows | `day_briefing.py`, `tasks_summary.py`, `meetings_summary.py`, `larisa_*` | high |
| Finance workflows | `finance_*`, `cashflow_*`, `pnl_*`, etc. | excluded contour |
| Health/devops workflows | `system_health.py`, `self_healing.py` | high |
| Legacy JS wrappers | `*/index.js` | legacy compatibility |
| WHOOP workflow | `whoop_report.py` via node bridge | excluded/server-sensitive |
| Sales brief | `sales_brief.py` | Sales/Lev adjacent |

## 3. Confirmed routing surface

Routing is tied to:

```text
cloudbot/orchestrator/router.py
cloudbot/orchestrator/orchestrator.py
cloudbot/workflows/larisa_runtime.py
cloudbot/workflows/finance_runtime.py
```

Tests currently lock route names for Larisa and finance.

## 4. Blocked changes

Blocked:

- moving workflows;
- changing workflow names;
- changing router mappings;
- changing legacy JS wrapper behavior;
- moving finance workflows into active migration;
- changing Larisa workflow commands.

## 5. Required before workflow migration

Required:

1. One workflow candidate only.
2. Route compatibility plan.
3. Old import path compatibility.
4. Tests for route selection.
5. Smoke checklist for affected agent.
6. Rollback plan.

## 6. Verdict

```text
workflow move blocked
boundary map completed
next safe step: runtime no-touch register
```
