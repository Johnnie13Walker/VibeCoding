# Wave 8 Execution Report

Дата фиксации: 2026-04-29 МСК.

Статус: completed for the first production-adjacent structural move.

## 1. Выполненный move

Canonical contract moved to:

```text
shared/contracts/sales_report_contract.py
```

Compatibility shim preserved at:

```text
agents/sales_agent/report_contract.py
```

## 2. Что изменилось

`shared/contracts/sales_report_contract.py` теперь содержит canonical definitions:

```text
SALES_PRIMARY_REPORT
SALES_FOLLOWUP_REPORTS
SALES_DISPATCH_SEQUENCE
SALES_RUNTIME_REPORT_TYPES
sales_dispatch_sequence()
sales_followup_report_types()
```

`agents/sales_agent/report_contract.py` теперь re-export shim для старого import path:

```text
from shared.contracts.sales_report_contract import ...
```

## 3. Что не менялось

Не менялись:

- `agents/sales_agent/sales_agent.py`;
- `agents/lev_petrovich/*`;
- `scripts/run_sales_copilot.py`;
- `cloudbot/devops/sales_dispatch_health.py`;
- Telegram routing;
- report contract values;
- runtime/env/cron/systemd/docker;
- deploy/rollback/verify scripts.

## 4. Проверки

Unit tests:

```bash
python3 -m unittest discover -s tests/unit
```

Result:

```text
Ran 12 tests
OK
```

Integration tests:

```bash
python3 -m unittest discover -s tests/integration
```

Result:

```text
Ran 26 tests
OK
```

Shim check:

```text
contract shim OK
```

Lev/Sales runtime tests:

```bash
python3 -m unittest tests.test_lev_petrovich_runtime
```

Result:

```text
Ran 47 tests
OK
```

## 5. Risk status

Old import path remains valid:

```text
agents.sales_agent.report_contract
```

New canonical path is available:

```text
shared.contracts.sales_report_contract
```

`agents/sales_agent` remains active compatibility layer.

## 6. Verdict

```text
Wave 8 sales report contract move completed
compatibility shim preserved
runtime remains no-touch
next production move still requires separate candidate gate
```
