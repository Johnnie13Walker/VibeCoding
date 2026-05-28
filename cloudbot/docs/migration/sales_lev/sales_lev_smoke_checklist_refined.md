# Sales / Lev Smoke Checklist Refined

Дата фиксации: 2026-04-28 МСК.

Статус: checklist only. Этот документ не запускает live Telegram, Bitrix или runtime checks.

## 1. Purpose

Production-safe smoke checklist for future approved Sales/Lev structural changes.

## 2. Owner checks after future approved move

| Check ID | What to verify | Expected healthy result | Where to check | Failure signal | Severity |
| --- | --- | --- | --- | --- | --- |
| SL-SMOKE-01 | Morning sales report delivery | report delivered to expected Sales chat | Telegram owner view / report logs | no report or wrong chat | critical |
| SL-SMOKE-02 | Report contract sequence | `sales`, `risks`, `focus` sequence preserved | report output / dispatch health | missing followup block | critical |
| SL-SMOKE-03 | `scripts/run_sales_copilot.py` bridge | bridge can produce expected report type | approved dry/mock run only | bridge command fails | critical |
| SL-SMOKE-04 | Bitrix data pull sanity | report includes expected CRM sections | report content | empty pipeline unexpectedly | high |
| SL-SMOKE-05 | Followup generation | risks/focus followups generated for sales report | report output | missing followups | high |
| SL-SMOKE-06 | Postponed deals block | postponed block appears when data exists | report output | block absent/incorrect | medium |
| SL-SMOKE-07 | Overdue tasks block | overdue block appears when data exists | report output | block absent/incorrect | medium |
| SL-SMOKE-08 | Weekly readiness | weekly target routing remains defined | env contract / dry routing | wrong target | high |
| SL-SMOKE-09 | Logs freshness | new dispatch events written | logs/reports | stale logs | high |
| SL-SMOKE-10 | Compatibility with `agents/sales_agent` | old imports still work | tests / dry run | import error | critical |

## 3. Mandatory local tests before smoke

Before any owner smoke:

```bash
python3 -m unittest discover -s tests/unit
python3 -m unittest tests.test_lev_petrovich_runtime
python3 -m unittest tests.test_sales_dispatch_contract
```

Do not run live checks unless owner approved runtime access.

## 4. Rollback urgency

Immediate rollback if:

- Telegram report goes to wrong chat;
- report contract sequence changes;
- `agents.sales_agent` import breaks;
- `scripts/run_sales_copilot.py` bridge fails;
- morning dispatch disappears.

## 5. Verdict

```text
Sales/Lev smoke checklist refined
live smoke not executed
runtime remains no-touch
```
