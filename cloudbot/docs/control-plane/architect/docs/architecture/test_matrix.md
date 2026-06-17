# Матрица тестов и проверок Cloudbot / OpenClo / Codex

## 1. Назначение документа

Этот документ фиксирует реальные тесты, проверки и health-check контуры проекта, чтобы было понятно:

- какие проверки действительно существуют;
- что каждая из них должна доказывать;
- чего она не доказывает;
- какие проверки детерминированы, а какие трогают live-зависимости;
- какие проверки годятся для локальной приемки, merge, pre-deploy и post-deploy;
- где в проекте смешиваются `smoke`, `dry-run`, `live`, `manual`, `health-check`.

Главный принцип документа:

- каноническим источником project-checks считается инженерный repo:
  `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`;
- текущий repo `/Users/pro2kuror/Desktop/architect` содержит архитектурные документы и runbook-слой, но не является полным источником реальных тестовых контуров Cloudbot.

## 2. Охват: какие контуры покрываются

Матрица покрывает:

- локальные JS/Python/shell проверки в `projects/engineer`;
- dry-run и orchestration проверки через `Makefile`, `checks/`, `infra/orchestrator/`;
- live/integration проверки OpenClaw, Bitrix, Telegram, Wazzup и server-runtime;
- manual/operational health-check и post-change verification;
- дополнительные meta-checks в `architect`, если они реально используются как operator workflow.

Источники, по которым собрана матрица:

- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/README.md`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/Makefile`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/bot/package.json`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/bot/tests/*.js`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/checks/*.py`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/checks/*.sh`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/scripts/*.sh`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/scripts/run_sales_copilot.py`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/infra/orchestrator/run_workflow.sh`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/infra/orchestrator/workflows/*.sh`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/configs/schedules.cron`
- `/Users/pro2kuror/Desktop/architect/docs/checklists/*.md`
- `/Users/pro2kuror/Desktop/architect/docs/prompts/*.md`

Локально подтверждено дополнительно:

- git repo существует в `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.git`;
- `origin`: `https://github.com/Johnnie13Walker/codex-base.git`;
- `npm test` в `bot` проходит;
- `bash -n` для `checks/post_change_verify.sh` и `infra/orchestrator/run_workflow.sh` проходит;
- `python3 checks/smoke_test.py` существует, но в наблюдаемом прогоне не завершился за разумное время, поэтому помечен как существующий, но проблемный по времени выполнения.

## 3. Классы проверок в проекте

### A. Unit tests

Подтвержденных изолированных Python unit-test наборов нет.

Есть локальные JS-тесты в `bot/tests/*.js`, но по факту это не “чистые unit tests”, а локальные сценарные проверки модулей и state-handling с in-memory/temporary state.

### B. Smoke tests

Подтверждены:

- `cd bot && npm test`
- `cd bot && npm run smoke:notifications`
- `python3 checks/smoke_test.py`
Но эти smoke-проверки не равны по природе:

- `bot npm test` и `smoke:notifications` локальные и детерминированные;
- `checks/smoke_test.py` уже шире классического smoke и проверяет несколько контуров сразу;

### C. Dry-run checks

Подтверждены:

- `DRY_RUN=1 ./infra/orchestrator/run_workflow.sh ...`
- `bash checks/post_change_verify.sh`, где `daily_ops` запускается специально в `DRY_RUN=1`;
- `scripts/preflight.sh` и часть `scripts/verify_integrations.sh`, когда live-проблемы смягчаются в `DRY_RUN=1`;
- dry-run поведение у отдельных runtime-отправок, например в Telegram-related smoke сценариях.

### D. Integration / Live checks

Подтверждены:

- `scripts/verify_integrations.sh`
- `bash checks/check_access.sh`
- `python3 scripts/run_sales_copilot.py --report bitrixcheck`
- `infra/orchestrator/workflows/cloudbot_runtime_verify.sh`
- schedule/workflow контуры из `configs/schedules.cron`

### E. Manual operational checks

Подтверждены:

- `docs/checklists/post-change.md`
- `docs/checklists/health-check.md`
- operator prompts из `architect/docs/prompts/*.md`
- manual dry-run runtime verification на сервере внутри `cloudbot_runtime_verify.sh`

### F. Pre-deploy checks

Фактически используются:

- `scripts/preflight.sh`
- `make verify-bot`
- `bash checks/post_change_verify.sh`
- `make verify` или выбранные live-подпроверки
- shell syntax checks

### G. Post-deploy / runtime checks

Фактически существуют:

- `infra/orchestrator/workflows/cloudbot_runtime_verify.sh`
- `docs/checklists/health-check.md`
- `python3 scripts/run_sales_copilot.py --report bitrixcheck`
- runtime-specific scheduled reports через cron/workflows

## 4. Реестр существующих проверок

| ID | Проверка | Класс | Где находится | Как запускается | Какой контур проверяет | Доказывает | Не доказывает | Детерминирована | Внешние API | Нужен server/runtime state | Нужны env/secrets | Локально | CI | Pre-deploy | Post-deploy | Критичность |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | `bot npm test` | локальный smoke / сценарный test | `bot/package.json`, `bot/tests/*.js` | `cd bot && npm test` | bot modules, Telegram routing, Bitrix app-state refresh path | локальная логика `bot` и mocked refresh path работают | не доказывает live Telegram/Bitrix/Wazzup/cron | да | нет | нет | нет | да | да | да | нет | critical |
| T2 | `npm run smoke:notifications` | локальный smoke | `bot/package.json`, `bot/scripts/smoke_notifications.js` | `cd bot && npm run smoke:notifications` | time notifications / dedup / reminder flow | локальный notification pipeline запускается | не доказывает реальную доставку Telegram | да | нет | нет | нет | да | да | да | нет | high |
| T3 | `python3 checks/smoke_test.py` | расширенный smoke / local integration | `checks/smoke_test.py` | `python3 checks/smoke_test.py` | bot npm tests, orchestrator, telegram handler, news digest, `/health` mock | базовые сценарии Cloudbot собираются и маршрутизируются | не доказывает live providers и не является быстрым smoke | частично | нет по дизайну | нет | нет | да | условно, с таймаутом | да | нет | critical |
| T4 | `python3 checks/system_test.py` | агрегированный local system test | `checks/system_test.py` | `python3 checks/system_test.py` | `smoke_test.py` + shell syntax + лог-каталог | локальный системный набор не развален на старте | не доказывает production runtime | частично | нет | частично: смотрит `logs/` | нет | да | условно | да | нет | high |
| T5 | `scripts/preflight.sh` | preflight / dry-run readiness | `scripts/preflight.sh` | `bash scripts/preflight.sh` или `make preflight` | CLI, skill files, базовые env prerequisites | окружение инженера готово для дальнейших проверок | не доказывает работоспособность приложения | частично | нет | нет | частично: проверяет наличие env | да | да | да | нет | medium |
| T6 | `scripts/verify_local_preflight.sh` / `scripts/verify_live_integrations.sh` | local preflight + live integration check | `scripts/verify_integrations.sh`, `scripts/verify_local_preflight.sh`, `scripts/verify_live_integrations.sh` | `bash scripts/verify_local_preflight.sh` или `make verify`; для live `bash scripts/verify_live_integrations.sh` или `make verify-live` | локальный bot smoke/CLI readiness отдельно от live OpenAI/Telegram/Wazzup/Sentry/GitHub contour | локальный ноутбук не краснеет из-за отсутствия боевых секретов, а live contour можно проверять отдельно тем же ядром verify | не доказывает полный live runtime сервера без server-side orchestration | нет | да | частично | да | да | нет | да | частично | critical |
| T7 | `bash checks/post_change_verify.sh` | post-change / dry-run acceptance | `checks/post_change_verify.sh` | `bash checks/post_change_verify.sh` | syntax, context contract, instruction conflicts, `daily_ops` dry-run, `next_week_prep`, `context_snapshot` | change не ломает базовые скрипты и dry-run orchestration | не доказывает live runtime и доставку | частично | частично | частично | частично | да | условно | да | нет | critical |
| T8 | `bash checks/context_contract_verify.sh` | deterministic contract check | `checks/context_contract_verify.sh` | `bash checks/context_contract_verify.sh` | owner operating contract freshness/shape | operator contract присутствует и не устарел | не доказывает runtime | да | нет | нет | нет | да | да | да | нет | medium |
| T9 | `bash checks/instruction_conflicts.sh` | deterministic config/runbook check | `checks/instruction_conflicts.sh` | `bash checks/instruction_conflicts.sh` | SLA/runbook/schedule consistency | базовые инструктивные контракты не конфликтуют | не доказывает, что cron реально применен | да | нет | нет | нет | да | да | да | нет | medium |
| T10 | `bash checks/check_access.sh` | live operational check | `checks/check_access.sh` | `bash checks/check_access.sh` | SSH access to primary/reserve hosts | доступ по SSH и базовый remote shell есть | не доказывает корректность runtime после доступа | нет | да | да | да | да | нет | да | да | high |
| T11 | `./infra/orchestrator/run_workflow.sh post_change_verify` | workflow runner for post-change | `infra/orchestrator/workflows/post_change_verify.sh` | `DRY_RUN=1 ./infra/orchestrator/run_workflow.sh post_change_verify` или `make openclaw.post-change-verify` | orchestration wrapper around post-change bundle | post-change bundle доступен через orchestrator | не доказывает live deploy success | частично | частично | частично | частично | да | условно | да | нет | high |
| T12 | `python3 scripts/run_sales_copilot.py --report bitrixcheck` | live bridge / runtime integration | `scripts/run_sales_copilot.py`, `infra/orchestrator/workflows/bitrix_check.sh` | `python3 scripts/run_sales_copilot.py --report bitrixcheck` или workflow `bitrix_check` | bridge Sales Copilot, remote env/state sync, Bitrix/Wazzup/Telegram readiness | sales runtime способен подтянуть live env/state и пройти Bitrix check | не доказывает локальную детерминированность и не подходит как unit/smoke | нет | да | да | да | ограниченно | нет | да | да | critical |
| T13 | `cloudbot_runtime_verify.sh` | post-deploy / runtime verify | `infra/orchestrator/workflows/cloudbot_runtime_verify.sh` | workflow `cloudbot_runtime_verify` | deployed release, wrappers, cron files, env files, reports, dry-run runtime execution | server runtime version и wiring выглядят корректно после выкладки | не заменяет полную функциональную приемку всех workflows | нет | да | да | да | нет | нет | нет | да | critical |
| T14 | `architect/docs/checklists/health-check.md` | manual operational health-check | `/Users/pro2kuror/Desktop/architect/docs/checklists/health-check.md` | вручную по чеклисту | общий operator health runtime | оператор проверил сервисы, интеграции, cron, логи и доставку | не доказывает локальную корректность кода и не заменяет smoke/unit | нет | да | да | да | ограниченно | нет | нет | да | critical |

## 5. Что каждая проверка доказывает и не доказывает

### Детерминированные и пригодные для локальной приемки

- `T1 bot npm test`
  Доказывает локальную корректность сценариев `bot/tests/smoke.test.js` и `bot/tests/bitrix_app_state.test.js`.
  Не доказывает live Telegram/Bitrix/Wazzup.
- `T2 smoke:notifications`
  Доказывает локальную логику task reminders и dedup.
  Не доказывает реальную доставку уведомлений.
- `T8 context_contract_verify`
  Доказывает, что operator contract существует и формально актуален.
  Не доказывает, что контракт соответствует реальному продакшену.
- `T9 instruction_conflicts`
  Доказывает непротиворечивость части runbook/schedule policy.
  Не доказывает, что расписание реально применено на сервере.

### Пограничные локальные smoke/system checks

- `T3 smoke_test.py`
  По дизайну доказывает, что базовый Cloudbot маршрутится локально без live API:
  `npm test`, orchestrator, telegram handler, news digest по фикстурам, `/health` в mock mode.
  На практике это уже не “быстрый smoke”, а локальный integration bundle.
  В наблюдаемом прогоне не завершился за разумное время, поэтому его нельзя считать быстрым и надежным smoke до стабилизации таймаута.
- `T4 system_test.py`
  Доказывает, что локальный агрегированный набор вообще стартует и что shell-скрипты синтаксически валидны.
  Не доказывает состояние production runtime.

### Dry-run и preflight

- `T5 preflight`
  Доказывает, что у инженера есть базовые CLI, skill-файлы и часть env prerequisites.
  Не доказывает, что интеграции реально работают.
- `T7 post_change_verify`
  Доказывает, что post-change bundle и dry-run orchestration не развалены на базовом уровне.
  Не доказывает live delivery, продовую доставку уведомлений или серверное состояние.
- `T14` и `T15` через `run_workflow.sh`
  Доказывают wiring orchestrator-workflow.
  Не доказывают автоматически корректность каждого live контура без анализа вложенных шагов.

### Live / integration / production-style checks

- `T6 verify_integrations.sh`
  Доказывает доступность части live integrations и readiness env.
  Не доказывает end-to-end боевую работу всего Cloudbot.
- `T10 check_access.sh`
  Доказывает SSH доступ.
  Не доказывает, что после входа сервис исправен.
- `T12 run_sales_copilot.py --report bitrixcheck`
  Доказывает live bridge между локальным runtime и server env/state для sales-контура.
  Не доказывает локальную детерминированность и опасен как критерий архитектурной приемки.
- `T13 cloudbot_runtime_verify.sh`
  Доказывает server-side wiring release/current/cron/wrappers/env files и dry-run runtime paths.
  Не доказывает полностью пользовательский опыт и каждую бизнес-функцию.
- `T14 manual health-check`
  Доказывает operator-level health picture на момент проверки.
  Не доказывает корректность локальных изменений до deploy.

## 6. Проверки, которые сейчас названы некорректно или смешивают роли

Критичные смешения:

1. `checks/smoke_test.py` называется smoke-test, но по содержанию это уже локальный интеграционный bundle.
   Он проверяет сразу `npm test`, orchestrator, telegram routing, news digest и `/health`.
2. `checks/system_test.py` называется system test, но фактически это локальный wrapper:
   `smoke_test.py` + `bash -n` + поверхностная проверка `logs/`.
   Это не production-style system test.
3. Исторически `scripts/verify_integrations.sh` смешивал preflight CLI/env readiness, локальный bot smoke и live Wazzup/GitHub/Sentry/env checks.
   На `2026-03-29` это разделено wrapper-скриптами `scripts/verify_local_preflight.sh` и `scripts/verify_live_integrations.sh`, но старые вызовы нужно дальше вычищать из документации и legacy runbook.
4. `checks/post_change_verify.sh` смешивает:
   - shell syntax;
   - config/runbook checks;
   - orchestration dry-run;
   - operational scripts.
   Это не один smoke и не один test suite.
5. `docs/checklists/health-check.md` и `architect` prompts не являются тестами в инженерном смысле.
   Это operator runbook, и его нельзя подставлять вместо локальной приемки change.

## 7. Минимальный обязательный набор проверок

### Для локальной приемки изменения в коде

Минимум:

1. `bash scripts/preflight.sh`
2. `cd bot && npm test`
3. `cd bot && npm run smoke:notifications`
4. `bash checks/context_contract_verify.sh`
5. `bash checks/instruction_conflicts.sh`
6. `bash checks/post_change_verify.sh`

Примечание:

- `checks/smoke_test.py` пока не стоит делать обязательным быстрым smoke gate, пока не будет добавлен явный timeout и понятный SLA по времени.

### Для архитектурной приемки

Минимум:

1. Все локальные deterministic checks выше.
2. Проверка, что change не меняет семантику `dry-run`/`live` без обновления документации.
3. Если меняется runtime/deploy/test wiring, обновить архитектурные документы.

### Перед merge

Минимум:

1. Локальный набор приемки.
2. `make verify-bot`
3. `bash checks/post_change_verify.sh`
4. Явная фиксация, если change требует live acceptance и не может быть принят только локально.

### Перед deploy

Минимум:

1. Локальный набор приемки.
2. `bash checks/post_change_verify.sh`
3. `make verify-live` или эквивалентный subset live integration checks для затронутого контура.
4. Явная проверка, что deploy не одобряется только на основании manual health-check.

### После deploy

Минимум:

1. `cloudbot_runtime_verify.sh` для runtime-контура.
2. `docs/checklists/health-check.md` или эквивалентный operator health-check.
3. Контурные live checks:
   - `python3 scripts/run_sales_copilot.py --report bitrixcheck` для sales/Bitrix;
   - проверка cron/report delivery для контуров из `configs/schedules.cron`.

## 8. Что должно быть deterministic

Детерминированными уже сейчас можно считать или стремиться считать:

- `T1 bot npm test`
- `T2 npm run smoke:notifications`
- `T8 context_contract_verify`
- `T9 instruction_conflicts`
- shell syntax checks

Погранично детерминированы, но требуют стабилизации:

- `T3 smoke_test.py`
- `T4 system_test.py`
- `T7 post_change_verify`

Не должны считаться deterministic:

- `T6 verify_integrations.sh`
- `T10 check_access.sh`
- `T12 run_sales_copilot.py --report bitrixcheck`
- `T13 cloudbot_runtime_verify.sh`
- `T14 manual health-check`

## 9. Какие проверки требуют live dependencies

Явно требуют live dependencies:

- `scripts/verify_integrations.sh`
- `checks/check_access.sh`
- `scripts/run_sales_copilot.py --report bitrixcheck`
- `cloudbot_runtime_verify.sh`
- manual `health-check`

Их live зависимости включают:

- SSH-доступ;
- server env/state;
- Telegram;
- Bitrix;
- Wazzup;
- OpenAI;
- Sentry;
- GitHub auth;
- cron/runtime wrappers;
- реальные report/log directories.

Вывод:

- прохождение live-check нельзя использовать как замену локальным deterministic tests;
- и наоборот, прохождение локального smoke не означает, что live runtime работает.

## 10. Пробелы в текущей системе тестирования

Главные пробелы:

1. Нет явного отдельного Python unit-test слоя.
2. Названия `smoke_test.py` и `system_test.py` не соответствуют их фактическому весу.
3. Нет жесткого разделения:
   - local deterministic smoke;
   - dry-run orchestration;
   - live integration;
   - post-deploy runtime verify.
4. `make verify` смешивает несколько ролей сразу.
5. `checks/smoke_test.py` в наблюдаемом запуске не уложился в разумное время и требует таймаута/декомпозиции.
6. Manual health-check все еще играет слишком большую роль как универсальный критерий “все работает”.

## 11. Приоритетные улучшения

1. Разделить `checks/smoke_test.py` на:
   - быстрый deterministic smoke;
   - отдельный local integration bundle.
2. Переименовать или переописать `system_test.py`, чтобы название не обещало production-style system verification.
3. Разбить `make verify` на отдельные цели:
   - `verify-local`
   - `verify-dry-run`
   - `verify-live`
4. Добавить time budget и timeout policy для smoke/local integration checks.
5. Явно пометить в README и Makefile, какие команды безопасны для CI, а какие требуют live env/secrets/server.
6. Для каждого live workflow добавить пару:
   - deterministic dry-run check;
   - separate live acceptance check.

## 12. Краткий вывод

После сверки с реальным инженерным repo картина такая:

- в проекте уже есть существенный набор проверок;
- но они смешаны по ролям сильнее, чем казалось из одного только `architect` repo;
- часть “smoke” проверок на деле является локальным integration bundle;
- часть `verify` проверок уже трогает live env, SSH, внешние API и server state;
- manual health-check и runtime verification по-прежнему нельзя путать с локальной инженерной приемкой.

Самые надежные базовые проверки для change acceptance сейчас:

- `cd bot && npm test`
- `cd bot && npm run smoke:notifications`
- `bash checks/context_contract_verify.sh`
- `bash checks/instruction_conflicts.sh`
- `bash checks/post_change_verify.sh`

Самые опасные проверки для неверной интерпретации:

- `checks/smoke_test.py`
- `make verify`
- `manual health-check`
- `scripts/run_sales_copilot.py --report bitrixcheck`

Пока роли не разведены жестче, формула “тесты прошли, значит live работает” для этого проекта неверна.
