# Инвентаризация переноса из `main`

## Назначение файла

Файл фиксирует, какие материалы найдены в каноническом runtime `../../assistant/engineer`, относятся ли они к роли `commercial-director` и что именно с ними сделано в рамках controlled extraction.

## Инвентарь

| Что найдено | Где найдено | Относится к `commercial-director` | Что сделано | Куда перенесено | Комментарий |
| --- | --- | --- | --- | --- | --- |
| Правила `Sales Copilot`, alias-команды и структура legacy-отчётов | `../../assistant/engineer/docs/sales_copilot.md` | да | перенесено | `README.md`, `CONTEXT.md`, `TASKS.md`, `templates/`, `prompts/` | основной документ для controlled extraction sales-контракта |
| Ограничения и контур `Bitrix24` для sales | `../../assistant/engineer/docs/bitrix_integration.md` | да | перенесено | `TOOLS.md`, `integrations/bitrix24/README.md`, `fields.md`, `mappings.md` | используется как документированный источник, не как live-подтверждение |
| Форматирование блоков воронки и legacy-денежного среза | `../../assistant/engineer/agents/sales_agent/sales_formatter.py` | да | частично перенесено | `templates/block-funnel.md`, `templates/telegram-report-full.md`; `templates/block-money.md` сохранён как архивный reference | перенесён канонический контракт daily-блока и архивный reference, но не runtime-код |
| Логика сигналов по воронке, `следующего шага`, движению и просрочкам | `../../assistant/engineer/agents/sales_agent/pipeline_analyzer.py` | да | частично перенесено | `playbooks/`, `CONTEXT.md`, `integrations/bitrix24/mappings.md` | перенесены правила и каркас сигналов, не вычислительный слой |
| Эвристики риска и приоритизации | `../../assistant/engineer/agents/sales_agent/risk_detector.py` | да | частично перенесено | `playbooks/analyze-pipeline-risks.md`, `playbooks/analyze-high-probability.md` | перенесены только управленческие правила |
| Логика коммуникаций, sales-фильтр и manager signals | исторический слой sales-agent, сейчас сведённый в docs и runtime `../../assistant/engineer` | да | частично перенесено | `TOOLS.md`, `CONTEXT.md`, `migration/decisions.md` | перенесены границы и ограничения, без отдельного live-коммуникационного файла |
| Основной агент `Sales Copilot` | `../../assistant/engineer/agents/sales_agent/sales_agent.py` | частично | не перенесено | не переносилось | runtime агента живёт в `assistant/engineer` до отдельного решения по роли |
| Snapshot skill для sales-данных | `../../assistant/engineer/cloudbot/skills/bitrix_sales_data.py` | да | частично перенесено | `integrations/bitrix24/entities.md`, `fields.md`, `mappings.md` | полезен как reference по составу snapshot, но не переносится как skill |
| Shared adapter чтения `Bitrix24` | `../../assistant/engineer/cloudbot/providers/bitrix/bitrix_sales_adapter.py` | частично | требует ручного решения | не переносилось | это shared integration-layer, переносить его в роль без архитектурного решения нельзя |
| Workflow `/sales`, `/pipeline`, `/risks`, `/focus-sales` | `../../assistant/engineer/cloudbot/workflows/sales_brief.py` | частично | не перенесено | не переносилось | контур ролей оформлен, но live workflow остаётся в `assistant/engineer` |
| Telegram command bindings | `../../assistant/engineer/cloudbot/bot/telegram/commands.py` | частично | не перенесено | не переносилось | knowledge о командах перенесён в docs, сами bindings не трогались |
| Общий Telegram delivery-layer | `../../assistant/engineer/cloudbot/providers/telegram_provider.py` | нет | не перенесено | не переносилось | вне зоны роли Льва Петровича |
| Ручной smoke-check live-контура | `../../assistant/engineer/checks/smoke_test.py` | да | перенесено | `checks/smoke-checklist.md` | из live smoke взяты только безопасные критерии качества |
| Проверка доступа к задачам `Bitrix24` | исторический smoke-check задач Bitrix24, в текущем runtime отдельного скрипта нет | да | требует ручного решения | не переносилось | live-проверка зависит от scope и runtime-доступов |
| Тесты структуры sales-отчёта | исторический test-layer formatter, в текущем runtime отдельного файла нет | да | перенесено | `templates/`, `checks/smoke-checklist.md`, `migration/decisions.md` | использованы для фиксации канона `Воронка в работе`, детальных риск-списков и антидублей |
| Тесты логики воронки и просрочек | исторический test-layer pipeline, в текущем runtime отдельного файла нет | да | перенесено | `playbooks/`, `integrations/bitrix24/mappings.md` | использованы как reference по сигналам и порогам |
| Тесты сборки и отправки sales-агента | исторический test-layer sales-agent, в текущем runtime отдельного файла нет | частично | перенесено | `TOOLS.md`, `migration/from-main-inventory.md` | полезны для фиксации границ runtime и отправки, но не формируют роль напрямую |
| Fixture-данные CRM для sales | `../../assistant/engineer/tests/fixtures/bitrix_crm_fixtures.json` | да | частично перенесено | `reports/examples/` | сырые fixture не копировались, оставлены только curated examples |
| Идеи расписания sales-отчётов | `../../assistant/engineer/configs/schedules.cron` | да | частично формализовано | `TASKS.md`, `migration/decisions.md`, `README.md`, `CONTEXT.md` | расписание жёстко зафиксировано в knowledge-слое: daily `09:30` за предыдущий рабочий день, weekly пятница `18:30`; cron живёт в runtime `assistant/engineer` и здесь не переносится |
| Shell-обвязка weekly/followup sales-workflows | `../../assistant/engineer/infra/orchestrator/workflows/sales_brief.sh`, `sales_followup.sh`, `sales_weekly_review.sh` | частично | требует ручного решения | `TASKS.md` | относится к runtime и scheduler-слою; содержательный контракт расписания уже зафиксирован, но live-обвязка вне текущего шага |

## Короткий вывод

- найдено `20` релевантных артефактов;
- полностью перенесено в knowledge-слой: `6`;
- частично перенесено и формализовано: `6`;
- оставлено в `main` без переноса: `4`;
- требует ручного решения: `4`.

Что осталось в каноническом runtime `assistant/engineer`:

- runtime агента;
- workflow и Telegram bindings;
- shared integration-layer;
- cron и shell-обвязка.

Что требует ручного решения:

- live `Bitrix24` adapter ownership;
- live-доступ к задачам;
- routing и runtime роли;
- scheduler и production `cron` под уже зафиксированное расписание.
