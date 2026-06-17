# Wave 9 Formatter Metadata Candidate

Дата фиксации: 2026-04-29 МСК.

Статус: candidate selection. Этот документ не меняет formatter behavior.

## 1. Candidate

Production-adjacent contract-like metadata:

```text
agents/sales_agent/sales_formatter.py
```

Candidate symbols:

```text
SALES_REPORT_FORMAT_VERSION
FORMATTER_MODULE
REPORT_FORMATS
REPORT_REQUIRED_MARKERS
report_format_metadata()
report_required_markers()
```

## 2. Target

```text
shared/contracts/sales_report_format_contract.py
```

## 3. Why this is acceptable

The candidate is metadata/contract-like, not formatter body logic.

It is used by:

```text
cloudbot/devops/sales_dispatch_health.py
tests/test_lev_petrovich_runtime.py
agents/sales_agent/sales_formatter.py
```

## 4. Required compatibility

Old imports must keep working:

```text
from agents.sales_agent.sales_formatter import SALES_REPORT_FORMAT_VERSION
from agents.sales_agent.sales_formatter import report_format_metadata
from agents.sales_agent.sales_formatter import report_required_markers
```

`agents/sales_agent/sales_formatter.py` must remain active formatter module.

## 5. Anti-scope

Do not move:

- formatter rendering functions;
- sales report body logic;
- Telegram formatting behavior;
- `agents/sales_agent/sales_agent.py`;
- `scripts/run_sales_copilot.py`;
- runtime/env/cron/deploy.

## 6. Verification

Required after move:

```bash
python3 -m unittest discover -s tests/unit
python3 -m unittest discover -s tests/integration
python3 -m unittest tests.test_lev_petrovich_runtime
python3 -m py_compile shared/contracts/sales_report_format_contract.py agents/sales_agent/sales_formatter.py
```

## 7. Verdict

```text
candidate approved for controlled metadata extraction
compatibility must be preserved
```
