# Sales Agent Retirement Assessment

Дата фиксации: 2026-04-28 МСК.

Статус: assessment only. Этот документ не разрешает retirement, перенос, удаление или переписывание `agents/sales_agent`.

## 1. Executive summary

`agents/sales_agent` нельзя считать архивом или мусором.

Текущая безопасная классификация:

```text
temporary compatibility layer
```

Решение сейчас:

```text
keep as compatibility layer
begin retirement later only after separate approved track
```

## 2. Подтвержденные зависимости

| Зона | Подтвержденная связь |
| --- | --- |
| `agents/lev_petrovich/agent.py` | импортирует `agents.sales_agent.sales_agent` |
| `scripts/run_sales_copilot.py` | импортирует `agents.sales_agent.report_contract` |
| `cloudbot/devops/sales_dispatch_health.py` | импортирует `agents.sales_agent.report_contract` и `agents.sales_agent.sales_formatter` |
| `tests/test_lev_petrovich_runtime.py` | импортирует несколько модулей из `agents.sales_agent` |
| `tests/test_sales_dispatch_contract.py` | импортирует `agents.sales_agent.report_contract` |
| `agents/sales_agent/sales_agent.py` | пишет события через `cloudbot.devops.sales_dispatch_health` |
| `agents/sales_agent/sales_formatter.py` | фиксирует formatter module как `agents.sales_agent.sales_formatter` |

## 3. Что может сломаться при раннем retirement

Если удалить, перенести или заменить `agents/sales_agent` слишком рано, может сломаться:

- Lev/Sales runtime import path;
- `scripts/run_sales_copilot.py`;
- sales report contract;
- morning sales dispatch validation;
- report formatting markers;
- follow-up report generation;
- postponed/overdue blocks;
- тесты Lev/Sales runtime;
- compatibility с текущими runtime paths.

## 4. Что сломается, если оставить как compatibility layer

Непосредственно ничего не должно сломаться.

Цена решения:

- архитектура остается менее чистой;
- часть логики Льва продолжает жить через старый namespace;
- будущий target layout `apps/lev_petrovich/legacy_sales_agent/` остается placeholder;
- retirement нужно планировать отдельно.

Эта цена ниже, чем риск сломать live Sales/Lev контур.

## 5. Условия перед retirement

Retirement можно обсуждать только после выполнения всех условий:

1. Есть новая canonical Lev/Sales entrypoint.
2. `scripts/run_sales_copilot.py` отвязан от старого path или имеет утвержденный bridge.
3. `report_contract` перенесен или закреплен как shared/contract module.
4. `sales_formatter` compatibility сохранена.
5. `cloudbot/devops/sales_dispatch_health.py` обновлен по approved design.
6. Тесты Lev/Sales проходят.
7. Smoke checklist Lev/Sales утвержден и выполнен.
8. Есть rollback без runtime pointer changes.
9. Owner явно разрешил retirement track.

## 6. Запрещено сейчас

Сейчас запрещено:

- удалять `agents/sales_agent`;
- переносить `agents/sales_agent`;
- считать его archive;
- менять imports на новый path;
- менять `scripts/run_sales_copilot.py`;
- менять report contract handling;
- менять Sales/Lev runtime behavior;
- менять deploy/runtime/env/cron/systemd/docker ради retirement.

## 7. Recommended owner decision

```text
Keep agents/sales_agent as temporary compatibility layer.
Do not retire in current migration wave.
Open separate retirement track only after Wave 5 production candidate gate.
```

## 8. Следующий безопасный шаг

Следующий безопасный шаг по Sales/Lev:

```text
sales_lev_dependency_map.md
```

Он должен быть read-only и ответить:

- какие функции реально используются;
- какие функции устарели;
- какие imports live-critical;
- какие tests покрывают каждый участок;
- какой target module будет replacement.
