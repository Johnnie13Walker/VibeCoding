# Sales / Lev Report Contract Map

Дата фиксации: 2026-04-28 МСК.

Статус: read-only contract map. Этот документ не меняет `agents/sales_agent/report_contract.py`.

## 1. Current contract file

```text
agents/sales_agent/report_contract.py
```

## 2. Confirmed contract values

```text
SALES_PRIMARY_REPORT = "sales"
SALES_FOLLOWUP_REPORTS = ("risks", "focus")
SALES_DISPATCH_SEQUENCE = ("sales", "risks", "focus")
SALES_RUNTIME_REPORT_TYPES = {"sales", "pipeline", "risks", "focus", "weekly"}
```

Functions:

```text
sales_dispatch_sequence(report_type)
sales_followup_report_types(report_type)
```

## 3. Consumers

| Consumer | Use |
| --- | --- |
| `scripts/run_sales_copilot.py` | runtime report types and followup report order |
| `agents/sales_agent/sales_agent.py` | runtime report validation and followup sequence |
| `cloudbot/devops/sales_dispatch_health.py` | required morning dispatch sequence |
| `tests/test_sales_dispatch_contract.py` | validates Telegram delivery sequence length |

## 4. Migration risk

This contract cannot move independently because it defines:

- morning report order;
- followup generation;
- dispatch validation;
- bridge report types;
- test expectations.

## 5. Blocked changes

Blocked:

- moving `report_contract.py`;
- changing `SALES_DISPATCH_SEQUENCE`;
- changing `SALES_RUNTIME_REPORT_TYPES`;
- changing followup order;
- changing consumer imports.

## 6. Required before future move

Required:

1. New canonical contract location.
2. Old import path compatibility.
3. Consumer map update.
4. Tests for `test_sales_dispatch_contract.py` and Lev/Sales runtime.
5. Smoke validation for morning sales report.

## 7. Verdict

```text
report contract remains under agents/sales_agent
move blocked
next safe step: Sales/Lev smoke checklist refinement
```
