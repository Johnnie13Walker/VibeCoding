# Sales Agent Retirement Assessment

Дата фиксации: 2026-05-02 МСК.

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
| `apps/lev_petrovich/agent.py` | импортирует canonical `apps.lev_petrovich.legacy_sales_agent.sales_agent` |
| `scripts/run_sales_copilot.py` | in-process path импортирует canonical `apps.lev_petrovich.agent` |
| `scripts/run_sales_copilot.py` | subprocess path всё ещё вызывает compatibility CLI `python -m agents.lev_petrovich` |
| `infra/orchestrator/workflows/sales_*.sh` | server wrappers всё ещё используют compatibility CLI `python3 -m agents.lev_petrovich` |
| `shared/contracts/sales_report_format_contract.py` | formatter metadata всё ещё публикует строку `agents.sales_agent.sales_formatter` |
| `agents/sales_agent/*` | re-export shim для `apps.lev_petrovich.legacy_sales_agent.*` |
| `tests/integration/test_app_compatibility_contract.py` | intentionally validates `agents.sales_agent` imports |

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
- внешние wrapper'ы, которые ещё вызывают `python -m agents.lev_petrovich`;
- потребители formatter metadata, если они ожидают старую строку модуля.

## 4. Что сломается, если оставить как compatibility layer

Непосредственно ничего не должно сломаться.

Цена решения:

- архитектура остается менее чистой;
- старый namespace остаётся видимым рядом с canonical `apps/*`;
- часть runtime wrapper'ов продолжает использовать compatibility CLI;
- retirement нужно планировать отдельно.

Эта цена ниже, чем риск сломать live Sales/Lev контур.

## 5. Условия перед retirement

Retirement можно обсуждать только после выполнения всех условий:

1. Все server wrappers переведены с `python -m agents.lev_petrovich` на approved canonical entrypoint.
2. `scripts/run_sales_copilot.py` subprocess path переведён или имеет утверждённый permanent compatibility bridge.
3. Formatter metadata version сменён так, чтобы `agents.sales_agent.sales_formatter` больше не был public contract.
4. External import audit доказывает отсутствие consumers `agents.sales_agent.*`.
5. `tests.integration.test_app_compatibility_contract` обновлён под retirement plan, а не просто удалён.
6. Lev/Sales tests проходят.
7. Smoke checklist Lev/Sales утвержден и выполнен.
8. Есть rollback без runtime pointer changes.
9. Owner явно разрешил retirement track.

## 6. Запрещено сейчас

Сейчас запрещено:

- удалять `agents/sales_agent`;
- переносить `agents/sales_agent`;
- считать его archive;
- удалять compatibility tests без replacement plan;
- менять `scripts/run_sales_copilot.py` subprocess path без separate approval;
- менять report contract handling;
- менять Sales/Lev runtime behavior;
- менять deploy/runtime/env/cron/systemd/docker ради retirement.

## 7. Recommended owner decision

```text
Keep agents/sales_agent as temporary compatibility layer.
Do not retire in current migration wave.
Open separate retirement track only after wrapper and formatter metadata cutover.
```

## 8. Следующий безопасный шаг

Следующий безопасный шаг по Sales/Lev:

```text
wrapper cutover design for python -m agents.lev_petrovich
```

Он должен быть read-only и ответить:

- какие server wrappers можно перевести на `apps.lev_petrovich`;
- как сохранить rollback;
- какие tests должны покрыть `scripts/run_sales_copilot.py`;
- когда можно менять formatter metadata contract;
- когда можно открыть отдельный retirement approval package.
