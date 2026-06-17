# План совместимости импортов перед Wave 4

Дата фиксации: 2026-04-28 МСК.

Статус: planning only. Этот документ не разрешает перенос кода, изменение imports, runtime, env, cron, systemd, docker или deploy-контуров.

## 1. Цель

Цель документа - зафиксировать требования к совместимости импортов перед любым будущим structural move.

До появления явной стратегии совместимости нельзя переносить production code из текущих активных путей в `apps/`, `shared/`, `config/` или другие target-директории.

## 2. Текущие подтвержденные import-couplings

На основании Wave 4 Gate зафиксированы следующие активные связки:

| Зона | Подтвержденная связка | Риск при переносе |
| --- | --- | --- |
| `agents/lev_petrovich` | `agents/lev_petrovich/agent.py` импортирует `agents.sales_agent.sales_agent` | Перенос Льва или `sales_agent` без compatibility layer ломает Lev/Sales runtime |
| `agents/sales_agent` | `agents/sales_agent/sales_agent.py` импортирует `agents.lev_petrovich.telegram_route` | `sales_agent` и `lev_petrovich` связаны двусторонне |
| `scripts/run_sales_copilot.py` | импортирует `agents.sales_agent.report_contract` и `agents.lev_petrovich.agent` | Runtime bridge Sales/Lev зависит от старых путей |
| `cloudbot/devops/sales_dispatch_health.py` | импортирует `agents.sales_agent.*` и `agents.lev_petrovich.*` | Health/dispatch checks могут сломаться при тихом переезде |
| `cloudbot/workflows/larisa_runtime.py` | импортирует `agents.larisa_ivanovna.*` | Перенос Ларисы требует сохранения старого import path |
| `tests/*` | используют `agents.larisa_ivanovna`, `agents.lev_petrovich`, `agents.sales_agent`, `cloudbot.*` | Тесты закрепляют текущие пути и должны быть учтены перед переносом |
| `cloudbot/*` | внутренние импорты между `cloudbot/orchestrator`, `cloudbot/providers`, `cloudbot/skills`, `cloudbot/workflows` | Shared-core перенос имеет высокий blast radius |

## 3. Непереговорные правила совместимости

1. Старые import paths должны оставаться валидными во время миграции.
2. `agents/sales_agent` остается текущим temporary compatibility layer.
3. Нельзя удалять, retire, переименовывать или переносить `agents/sales_agent` без отдельного owner approval.
4. Нельзя молча переписывать imports в production code.
5. Нельзя создавать shims, wrapper modules, package files или `__init__.py` без отдельного owner approval.
6. Нельзя менять runtime pointers, live env, cron, systemd, docker или deploy scripts в рамках import compatibility work.
7. Любой будущий перенос должен иметь заранее описанный rollback path.

## 4. Стратегии, которые можно оценивать позже

| Strategy | Описание | Статус сейчас | Риск |
| --- | --- | --- | --- |
| A | Ничего не переносить, оставить только markers и plans | Разрешено как документация | Низкий |
| B | Держать target folders как пустые placeholders | Уже выполнено в Wave 3B | Низкий |
| C | Добавить compatibility shims на старых путях | Не разрешено сейчас | Средний, потому что это code change |
| D | Перенести модуль и оставить старый import path через shim | Не разрешено сейчас | Высокий без тестов и smoke-check |
| E | Массово переписать imports на target paths | Запрещено для ближайшего шага | Высокий |

## 5. Требования по кандидатам будущего переноса

### 5.1. Larisa

Перед любым переносом `agents/larisa_ivanovna` нужно подтвердить:

- старый путь `agents.larisa_ivanovna.*` остается доступным;
- `cloudbot/workflows/larisa_runtime.py` не ломается;
- smoke checklist Ларисы утвержден и готов к выполнению;
- нет изменений Telegram token/chat routing;
- runtime `/opt/cloudbot-runtime/larisa/current` остается no-touch.

Статус: not confirmed. Code move blocked.

### 5.2. Lev / Sales

Перед любым переносом `agents/lev_petrovich` или `agents/sales_agent` нужно подтвердить:

- `agents/sales_agent` остается active compatibility layer;
- `scripts/run_sales_copilot.py` продолжает работать со старым path contract;
- `report_contract.py` и report contract handling не меняют поведение;
- `cloudbot/devops/sales_dispatch_health.py` не теряет текущие импорты;
- Lev/Sales smoke checklist утвержден и готов к выполнению;
- runtime `/opt/cloudbot-runtime/current` остается no-touch.

Статус: not confirmed. Code move blocked.

### 5.3. Shared-core

Перед любым переносом `cloudbot/orchestrator`, `cloudbot/providers`, `cloudbot/skills` или `cloudbot/workflows` нужно подтвердить:

- текущий `cloudbot.*` import surface остается валидным;
- нет изменения shared-core behavior;
- есть отдельная карта зависимостей по каждому provider/skill/workflow;
- есть rollback plan без server/runtime действий.

Статус: not confirmed. Shared-core move blocked.

### 5.4. Config

Перед любым переносом `configs/*` нужно подтвердить:

- реальные env-файлы и secrets не трогаются;
- live env остается вне миграции;
- target `config/env/examples` и `config/env/schemas` используются только после отдельного approval;
- нет fallback на общий `TELEGRAM_BOT_TOKEN`.

Статус: not confirmed. Config move blocked.

### 5.5. Tests

Перед переносом тестов нужно подтвердить:

- test discovery не сломается;
- тесты не требуют live env/server/secrets;
- старые imports остаются валидными до отдельного решения;
- список safe tests утвержден отдельно.

Статус: not confirmed. Tests move blocked.

## 6. Candidate safe checks для будущего approval

Этот список не является разрешением на запуск тестов. Перед выполнением нужен отдельный review, потому что repo остается dirty.

Кандидаты для проверки после будущего approved move:

- `python3 -m unittest tests.test_larisa_agent`
- `python3 -m unittest tests.test_lev_petrovich_runtime`
- `python3 -m unittest tests.test_bitrix_app_auth`
- `python3 -m unittest tests.test_bitrix_sales_adapter`

Статус: not confirmed. Не запускать без отдельного approval.

## 7. Rollback requirements для любого будущего move

До выполнения любого code move должны быть зафиксированы:

1. Точный список файлов, которые будут созданы или изменены.
2. Подтверждение, что старый import path остается рабочим.
3. Подтверждение, что runtime pointers не меняются.
4. Подтверждение, что rollback не требует deploy или server access.
5. Команда read-only проверки git status до и после.
6. Smoke checklist для соответствующего контура.

Если хотя бы один пункт не подтвержден, code move остается blocked.

## 8. Gate checklist перед первым code move

| Check | Requirement | Status | Blocker |
| --- | --- | --- | --- |
| W4-IMPORT-01 | Выбран один конкретный кандидат переноса | fail | yes |
| W4-IMPORT-02 | Описана стратегия сохранения старого import path | not confirmed | yes |
| W4-IMPORT-03 | Утвержден список файлов для изменения | not confirmed | yes |
| W4-IMPORT-04 | Утвержден safe test list | not confirmed | yes |
| W4-IMPORT-05 | Утвержден smoke checklist для затронутого контура | not confirmed | yes |
| W4-IMPORT-06 | Подтвержден no-touch runtime/env/cron/systemd/docker | pass | no |
| W4-IMPORT-07 | Подтверждено, что `agents/sales_agent` не retire и не move | pass | no |
| W4-IMPORT-08 | Есть owner approval на code-adjacent compatibility mechanism | not confirmed | yes |

## 9. Финальный вывод

Import compatibility planning создан.

Первый code move все еще blocked.

Следующий безопасный шаг: подготовить отдельный `wave4_candidate_selection.md` или `candidate_migration_design.md`, где будет выбран ровно один будущий кандидат переноса, описан точный scope и подтверждена стратегия сохранения старых import paths.
