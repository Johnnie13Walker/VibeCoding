# Wave 5 Production Candidate Gate

Дата фиксации: 2026-04-28 МСК.

Статус: gate only. Этот документ не разрешает production move, deploy, restart, runtime/env/cron/systemd/docker изменения или изменение бизнес-логики.

## 1. Зачем нужен этот gate

Wave 4 подтвердил безопасный migration loop на test layout:

```text
one file -> test -> status check -> next step
```

Wave 5 не должен сразу переносить production code. Сначала нужно выбрать один production-adjacent candidate с минимальным blast radius и доказать, что он не ломает runtime.

## 2. Что уже подтверждено

Успешно перенесены в `tests/unit/` и проверены:

```text
tests/unit/test_search_provider.py
tests/unit/test_bitrix_app_auth.py
tests/unit/test_bitrix_sales_adapter.py
```

Проверка:

```text
python3 -m unittest discover -s tests/unit
Ran 12 tests
OK
```

## 3. Кандидаты Wave 5

| Candidate | Current path | Target idea | Риск | Решение gate |
| --- | --- | --- | --- | --- |
| W5-CAND-01 | `configs/*.env.example` | `config/env/examples/` | Средний: можно спутать examples/live env | investigate first |
| W5-CAND-02 | `configs/schedule_contract.env` | `config/schedules/` | Высокий: contract может быть связан с cron/runtime | blocked |
| W5-CAND-03 | `agents/larisa_ivanovna/*` | `apps/larisa_ivanovna/` | Высокий: active imports/runtime | blocked |
| W5-CAND-04 | `agents/lev_petrovich/*` | `apps/lev_petrovich/` | Высокий: связан с `agents/sales_agent` | blocked |
| W5-CAND-05 | `agents/sales_agent/*` | `apps/lev_petrovich/legacy_sales_agent/` | Критичный: active compatibility layer | prohibited now |
| W5-CAND-06 | `cloudbot/providers/search_provider.py` | `shared/providers/` | Высокий: shared-core import surface | blocked |
| W5-CAND-07 | README/contract docs only | docs under `docs/migration/wave5/` | Низкий | allowed |

## 4. Рекомендация

Первый production-adjacent move пока не разрешать.

Самый безопасный следующий шаг:

```text
W5-CAND-01 design only:
configs examples classification and live-env separation design
```

Но сам перенос `configs/*` не выполнять до отдельного design и approval.

## 5. Почему не трогаем агентов

`agents/larisa_ivanovna`, `agents/lev_petrovich` и `agents/sales_agent` остаются active paths.

Пока не подтверждены:

- старые imports остаются рабочими;
- smoke checklist выбранного контура готов;
- rollback не требует runtime/deploy;
- server runtime не зависит от текущего path напрямую;
- owner approval получен.

## 6. Почему не трогаем shared-core

`cloudbot/orchestrator`, `cloudbot/providers`, `cloudbot/skills`, `cloudbot/workflows` имеют высокий blast radius.

Любой перенос shared-core требует отдельной карты:

- кто импортирует модуль;
- есть ли runtime side effects;
- какие tests покрывают перенос;
- нужен ли compatibility shim;
- как откатить без deploy.

## 7. Preconditions для будущего Wave 5 execution

Перед любым production-adjacent move нужно:

1. Выбрать ровно один candidate.
2. Создать candidate-specific design.
3. Подтвердить старые import paths.
4. Подтвердить safe test list.
5. Подтвердить smoke checklist.
6. Подтвердить rollback без server access.
7. Получить явный owner approval.

## 8. No-touch

В Wave 5 gate запрещено:

- переносить production code;
- менять business logic;
- менять imports;
- менять runtime/env/cron/systemd/docker;
- менять deploy/rollback/verify scripts;
- менять `/opt/*`, `/etc/*`, `/root/*`, `/home/ops/*`;
- удалять, retire или переносить `agents/sales_agent`;
- включать finance/iOS/HAPP/VPN/subscription/server-only integrations.

## 9. Gate verdict

```text
Wave 5 production code move: blocked
Next safe action: configs examples classification design only
```
