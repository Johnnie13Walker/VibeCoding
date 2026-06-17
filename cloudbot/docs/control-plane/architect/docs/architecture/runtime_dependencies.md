# Реестр runtime-зависимостей Cloudbot

## 1. Назначение документа

Этот документ фиксирует реальные runtime-зависимости, которые удалось подтвердить по текущему содержимому репозитория `/Users/pro2kuror/Desktop/architect`.

Важно:

- текущий репозиторий является каркасом, а не полноценным исходным кодом Cloudbot/OpenClo;
- большая часть production/runtime-контура пока существует только как правила и чеклисты, а не как исполняемый код;
- поэтому реестр ниже разделяет:
  - подтвержденные зависимости, реально найденные в git;
  - зависимости, которые только задекларированы в документах;
  - критичные runtime-контракты, которые в репозитории вообще не зафиксированы.

Источники аудита:

- `AGENTS.md`
- `README.md`
- `.gitignore`
- `scripts/deploy.sh`
- `scripts/README.md`
- `docs/PLAN.md`
- `docs/STATUS.md`
- `docs/checklists/*.md`
- `docs/prompts/*.md`
- `docs/workflows/codex-github.md`
- `orchestrator/README.md`, `workflows/README.md`, `skills/README.md`, `providers/README.md`, `telegram/README.md`, `devops/README.md`
- внешний инженерный repo `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` как подтвержденный git-контур проекта

Что не найдено в текущем дереве:

- application-код Python/Node;
- `scripts/run_sales_copilot.py`;
- директории `deploy/`, `backup/`, `cron/`, `state/`, `reports/`, `logs/`;
- provider-клиенты;
- bridge-скрипты Node/Python;
- server-only конфиги;
- env-шаблон без секретов;
- описание реальных systemd/docker сервисов;
- реальные логи и runtime state.

## 2. Что считается runtime-зависимостью в этом проекте

В рамках Cloudbot runtime-зависимостью считается любой артефакт, путь, переменная окружения, внешний сервис, state-каталог, shell-инструмент или server-only объект, без которого:

- не запускается Codex/Cloudbot;
- не выполняется deploy;
- не проходят nightly / health-check / manual run контуры;
- не работает Telegram-доставка;
- не отрабатывают cron/scheduler-задачи;
- невозможно воспроизвести локальный запуск или smoke/live-проверку.

Контуры, которые используются в этом реестре:

- `local`
- `github`
- `server`
- `cron`
- `telegram`
- `manual run`
- `deploy`
- `smoke/integration/live checks`

Уровни уверенности:

- `высокая` — зависимость подтверждена конкретным файлом или скриптом;
- `средняя` — зависимость явно задекларирована в документах, но не реализована кодом;
- `низкая` — зависимость ожидается по архитектуре или запросу, но в repo не найдена.

## 3. Карта зависимостей по категориям

| Категория | Статус | Что подтверждено | Комментарий |
| --- | --- | --- | --- |
| Code dependencies | частично найдено | `scripts/deploy.sh` | Другого исполняемого кода нет |
| Config dependencies | найдено | `AGENTS.md`, `docs/PLAN.md`, чеклисты, prompt-файлы, git workflow docs | Это фактический control plane текущего репозитория |
| Runtime state | найдено частично | `docs/STATUS.md` | Runtime state уже живет в git, что рискованно |
| Infra dependencies | найдено частично | `bash`, `git`, `.git`, repo root, `TZ`, `DRY_RUN` | Подтверждено через `scripts/deploy.sh` и workflow docs |
| External services | только задекларировано | OpenAI, Bitrix24, Todo, WHOOP, Web Search | Реальных клиентов и env-контрактов нет |
| Delivery dependencies | только задекларировано | Telegram | Нет wiring, токенов, chat routing и retry-логики |
| Cron/scheduler jobs | только задекларировано | cron, scheduler, queues | Нет cron-файлов, systemd unit или очередей |
| Server paths / state directories | почти не зафиксировано | только `.git`, предполагаемые `tmp/`, `logs/`, `.cache/` из `.gitignore` | Реальных server path/state-контрактов нет |
| Cache/tmp/reports/logs | найдено частично | `tmp/`, `logs/`, `.cache/` в `.gitignore` | `reports/` и реальные лог-источники не найдены |
| Deploy dependencies | найдено частично | `scripts/deploy.sh`, `bash`, `git`, `.git`, `DRY_RUN`, `TZ` | Скрипт безопасный, но пока шаблонный |
| Testing/check dependencies | найдено частично | чеклисты и prompt для health-check | Нет реальных тестовых команд и smoke-сценариев |
| Node/Python bridge dependencies | не найдено | нет | Любые bridge-зависимости сейчас вне репозитория или отсутствуют |
| Shell wrappers | найдено частично | `scripts/deploy.sh` | Других wrapper-скриптов нет |
| Google / RSS / News / Weather / Sales providers | не найдено | нет | Эти зависимости нельзя зафиксировать по текущему repo |

## 4. Структурированный реестр зависимостей

### 4.1 Control plane: кодовые и конфигурационные зависимости

#### `AGENTS.md`

- Тип зависимости: runtime policy / config
- Слой: `config`, `artifact`
- Где находится: `AGENTS.md`
- Кто использует: Codex при любом интерактивном, nightly и health-check запуске
- Критичные контуры: `local`, `github`, `manual run`, `deploy`, `smoke/integration/live checks`
- Должна жить в git: да
- Не должна жить вне git: да, иначе правила работы агента перестанут быть воспроизводимыми
- Должна быть задокументирована отдельно: нет, но ее изменения должны отражаться в архитектурных документах
- Критичность: `critical`
- Если исчезнет или сломается: агент потеряет обязательные правила по языку, таймзоне, безопасности, проверкам и git workflow
- Fallback / workaround: ручное повторение правил из памяти; это ненадежно
- Архитектурная проблема: один файл одновременно хранит policy, workflow и часть runtime-контрактов
- Уверенность: `высокая`

#### `docs/PLAN.md`

- Тип зависимости: backlog / execution config
- Слой: `config`
- Где находится: `docs/PLAN.md`
- Кто использует: nightly-run и любой автономный режим Codex
- Критичные контуры: `local`, `github`, `manual run`
- Должна жить в git: да
- Не должна жить вне git: да
- Должна быть задокументирована отдельно: нет
- Критичность: `high`
- Если исчезнет или сломается: автономный запуск теряет источник задач и становится недетерминированным
- Fallback / workaround: пользователь задает задачу вручную
- Архитектурная проблема: backlog хранится в markdown, без явного статуса ownership, priority и runtime-связи с issue tracker
- Уверенность: `высокая`

#### `docs/STATUS.md`

- Тип зависимости: execution log / mutable runtime state
- Слой: `state`, `artifact`
- Где находится: `docs/STATUS.md`
- Кто использует: nightly-run, health-check, manual run
- Критичные контуры: `local`, `github`, `manual run`, `smoke/integration/live checks`
- Должна жить в git: сейчас да по правилам проекта
- Не должна жить в git: по смыслу это runtime state, поэтому долгосрочно нет
- Должна быть задокументирована отдельно: да, как решение о хранении runtime state в репозитории
- Критичность: `high`
- Если исчезнет или сломается: теряется история последних проверок, блокеров и ручных запусков
- Fallback / workaround: писать статус во внешнюю систему или восстанавливать вручную
- Архитектурная проблема: mutable operational state уже смешан с source tree, что создает шум, merge-конфликты и неочевидный source of truth
- Уверенность: `высокая`

#### Операционные чеклисты

- Тип зависимости: health/smoke config
- Слой: `config`
- Где находится: `docs/checklists/health-check.md`, `docs/checklists/post-change.md`
- Кто использует: health-check и post-change manual run
- Критичные контуры: `manual run`, `smoke/integration/live checks`, `server`, `cron`
- Должна жить в git: да
- Не должна жить вне git: да
- Должна быть задокументирована отдельно: нет
- Критичность: `high`
- Если исчезнет или сломается: проверки после изменений и утренний контроль станут произвольными
- Fallback / workaround: ручной чек по памяти
- Архитектурная проблема: чеклисты перечисляют внешние зависимости, но не содержат конкретных service names, log paths, cron entries, health endpoints и команд
- Уверенность: `высокая`

#### Prompt-файлы и GitHub workflow для Codex

- Тип зависимости: operational control artifacts
- Слой: `config`, `artifact`
- Где находится: `docs/prompts/daily-health-check.md`, `docs/prompts/nightly-codex.md`, `docs/prompts/feature-branch-task.md`, `docs/workflows/codex-github.md`
- Кто использует: Codex при nightly, feature-branch и health-check сценариях
- Критичные контуры: `local`, `github`, `manual run`, `deploy`
- Должна жить в git: да
- Не должна жить вне git: да
- Должна быть задокументирована отдельно: нет
- Критичность: `high`
- Если исчезнет или сломается: агент потеряет порядок git-проверки, правила безопасной работы и формат итоговых отчетов
- Fallback / workaround: запускать Codex вручную без стандартизированного prompt
- Архитектурная проблема: operational behavior агента зависит от markdown-файлов, но это не оформлено как отдельный config layer
- Уверенность: `высокая`

### 4.2 Deploy и базовая инфраструктура

#### `scripts/deploy.sh`

- Тип зависимости: deploy script / shell wrapper
- Слой: `code`
- Где находится: `scripts/deploy.sh`
- Кто использует: deploy contour
- Критичные контуры: `deploy`, `manual run`
- Должна жить в git: да
- Не должна жить вне git: да
- Должна быть задокументирована отдельно: да, вместе с шагами реального deploy
- Критичность: `high`
- Если исчезнет или сломается: стандартный путь deploy перестанет быть воспроизводимым
- Fallback / workaround: ручной запуск git и restart-команд на сервере
- Архитектурная проблема: скрипт пока только шаблон и не отражает реальные шаги обновления, пересборки и рестарта
- Уверенность: `высокая`

#### Git repository metadata и запуск из корня репозитория

- Тип зависимости: repo artifact / local path / git state
- Слой: `infra`, `artifact`
- Где находится: каталог `.git` и текущий `cwd`; для `architect`-workspace `.git` отсутствует, но подтвержден отдельный инженерный repo `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.git`
- Кто использует: deploy script и GitHub workflow для Codex
- Критичные контуры: `github`, `deploy`, `manual run`
- Должна жить в git: нет, `.git` и `.git/config` вне version control
- Не должна жить в git: да
- Должна быть задокументирована отдельно: да, как внешний runtime contract
- Критичность: `critical`
- Если исчезнет или сломается: `scripts/deploy.sh` завершится ошибкой, feature-branch workflow не сможет проверить ветки и remote
- Fallback / workaround: использовать канонический инженерный repo вместо docs-workspace
- Архитектурная проблема: deploy и workflow завязаны на git-состояние, но `architect` и реальный инженерный repo разделены, из-за чего легко перепутать control-plane и source repo
- Уверенность: `высокая`

#### Веточная модель и git remote

- Тип зависимости: VCS workflow config
- Слой: `config`, `infra`
- Где находится: `docs/workflows/codex-github.md`, `docs/prompts/feature-branch-task.md`, фактически также в `.git/config` и refs
- Кто использует: Codex при работе через GitHub и PR
- Критичные контуры: `github`, `manual run`, `deploy`
- Должна жить в git: документация да; actual remote config нет
- Не должна жить в git: remote URLs и локальный git state
- Должна быть задокументирована отдельно: да
- Критичность: `high`
- Если исчезнет или сломается: невозможно безопасно работать через `dev`/feature-ветки и PR
- Fallback / workaround: ручной выбор ветки и remote
- Архитектурная проблема: workflow описан в docs-workspace, а фактические remote и ветки живут в отдельном инженерном repo, что создает разрыв между документацией и рабочим source tree
- Уверенность: `средняя`

#### `bash`, `date`, `printf` и shell `PATH`

- Тип зависимости: shell runtime
- Слой: `infra`
- Где находится: shebang `#!/usr/bin/env bash` и вызовы в `scripts/deploy.sh`
- Кто использует: deploy script
- Критичные контуры: `deploy`, `manual run`
- Должна жить в git: нет
- Не должна жить в git: да
- Должна быть задокументирована отдельно: да, в разделе требований к окружению
- Критичность: `high`
- Если исчезнет или сломается: deploy script не запустится или начнет логировать некорректные таймстампы
- Fallback / workaround: запуск через совместимую оболочку после адаптации скрипта
- Архитектурная проблема: есть неявная зависимость от shell-окружения и `PATH`, но минимальная версия/дистрибутив не зафиксированы
- Уверенность: `высокая`

#### `git` CLI

- Тип зависимости: external executable
- Слой: `infra`
- Где находится: вызывается из `scripts/deploy.sh`, явно требуется prompt-ами и workflow docs
- Кто использует: deploy script, feature-branch workflow, GitHub runbook
- Критичные контуры: `github`, `deploy`, `manual run`
- Должна жить в git: нет
- Не должна жить в git: да
- Должна быть задокументирована отдельно: да
- Критичность: `critical`
- Если исчезнет или сломается: невозможно проверить статус ветки, diff, remote и безопасно запускать deploy
- Fallback / workaround: отсутствует, кроме ручной установки `git`
- Архитектурная проблема: системная зависимость есть, но список обязательных CLI-инструментов не оформлен
- Уверенность: `высокая`

#### `TZ=Europe/Moscow`

- Тип зависимости: environment config
- Слой: `config`
- Где находится: `scripts/deploy.sh`; дополнительно правило повторяется в `AGENTS.md`, prompt-файлах и чеклистах
- Кто использует: deploy script и все процессы отчетности/логирования
- Критичные контуры: `local`, `server`, `cron`, `deploy`, `manual run`
- Должна жить в git: правило да; конкретное env-значение на машине нет
- Не должна жить в git: runtime env на сервере
- Должна быть задокументирована отдельно: нет
- Критичность: `medium`
- Если исчезнет или сломается: таймстампы и расписания станут расходиться с обязательным MSK-контрактом
- Fallback / workaround: `scripts/deploy.sh` сам подставляет `Europe/Moscow`, но остальной runtime-контур этого гаранта не имеет
- Архитектурная проблема: одно и то же правило размазано по нескольким markdown-файлам и одному shell-скрипту
- Уверенность: `высокая`

#### `DRY_RUN`

- Тип зависимости: environment flag
- Слой: `config`
- Где находится: `scripts/deploy.sh`
- Кто использует: deploy script
- Критичные контуры: `deploy`, `manual run`
- Должна жить в git: только упоминание в коде скрипта
- Не должна жить в git: runtime-значение переменной
- Должна быть задокументирована отдельно: да, в реальном deploy runbook
- Критичность: `medium`
- Если исчезнет или сломается: у будущего реального deploy-кода может измениться профиль безопасности
- Fallback / workaround: по умолчанию скрипт безопасен и использует `DRY_RUN=1`
- Архитектурная проблема: критическая safety-логика завязана на env-переменную, но реальные deploy-шаги пока не реализованы
- Уверенность: `высокая`

### 4.3 Runtime state, секреты и локальные артефакты

#### `.env`, `.env.*` и секретные файлы

- Тип зависимости: env / secret policy
- Слой: `secret`, `config`
- Где находится: политика в `AGENTS.md` и `.gitignore`
- Кто использует: предполагаемо весь production runtime, но в текущем repo конкретные consumers не найдены
- Критичные контуры: `local`, `server`, `cron`, `telegram`, `deploy`, `smoke/integration/live checks`
- Должна жить в git: нет
- Не должна жить в git: да
- Должна быть задокументирована отдельно: да, как env contract без секретов
- Критичность: `critical`
- Если исчезнет или сломается: production runtime с интеграциями Telegram/OpenAI/Bitrix/Todo/WHOOP/Web Search не сможет аутентифицироваться
- Fallback / workaround: отсутствует
- Архитектурная проблема: политика хранения секретов описана, но ни одного реального env-key registry или `.env.example` в репозитории нет
- Уверенность: `средняя`

#### `tmp/`, `logs/`, `.cache/`

- Тип зависимости: local paths / cache / logs
- Слой: `state`, `artifact`
- Где находится: только в `.gitignore`
- Кто использует: конкретный consumer в repo не найден
- Критичные контуры: `local`, `server`, `smoke/integration/live checks`
- Должна жить в git: нет
- Не должна жить в git: да
- Должна быть задокументирована отдельно: да, когда появятся реальные producers
- Критичность: `medium`
- Если исчезнет или сломается: текущий каркас не пострадает, но будущие логи и временные данные окажутся без стандартизированного размещения
- Fallback / workaround: создавать каталоги вручную по месту использования
- Архитектурная проблема: пути под логи и временные файлы уже подразумеваются, но не описано, кто и в каком формате их создает
- Уверенность: `средняя`

#### Server-only state, reports, backup artifacts

- Тип зависимости: server paths / runtime state / artifacts
- Слой: `state`, `infra`, `artifact`
- Где находится: в repo не найдено; backup упомянут только в `devops/README.md` и `docs/PLAN.md`
- Кто использует: предполагаемо health-check, backup, nightly reports, deploy rollback
- Критичные контуры: `server`, `cron`, `deploy`, `smoke/integration/live checks`
- Должна жить в git: state нет; схемы путей и policies да
- Не должна жить в git: реальные backup-данные, runtime state, логи, generated reports
- Должна быть задокументирована отдельно: да, обязательно
- Критичность: `critical`
- Если исчезнет или сломается: live-диагностика, rollback, проверка отчетов и понимание состояния runtime станут невозможными
- Fallback / workaround: ручной поиск по серверу
- Архитектурная проблема: это самый большой текущий пробел; repo не содержит ни одного server-only runtime contract
- Уверенность: `низкая`

### 4.4 Infra, delivery и внешние сервисы

#### Сервисы приложения, scheduler, queues, cron, reverse proxy

- Тип зависимости: infra services
- Слой: `infra`
- Где находится: только в `docs/checklists/health-check.md` и `README.md`
- Кто использует: health-check, daily status, post-change smoke
- Критичные контуры: `server`, `cron`, `deploy`, `smoke/integration/live checks`
- Должна жить в git: service inventory и unit/templates да; actual runtime state нет
- Не должна жить в git: реальные PID, socket state, live queues
- Должна быть задокументирована отдельно: да
- Критичность: `critical`
- Если исчезнет или сломается: невозможно понять, что именно должно быть поднято, что именно проверять и как диагностировать падение
- Fallback / workaround: ручной осмотр сервера
- Архитектурная проблема: health-check уже требует эти зависимости, но их конкретные имена, команды и точки контроля не зафиксированы
- Уверенность: `средняя`

#### Telegram delivery wiring

- Тип зависимости: delivery dependency
- Слой: `external service`, `infra`, `config`
- Где находится: только архитектурные упоминания в `AGENTS.md`, `telegram/README.md`, `docs/checklists/health-check.md`
- Кто использует: весь user-facing runtime Cloudbot
- Критичные контуры: `telegram`, `server`, `cron`, `smoke/integration/live checks`
- Должна жить в git: клиентский код и retry-policy да; токены нет
- Не должна жить в git: bot token, chat secrets, session data
- Должна быть задокументирована отдельно: да, как внешний runtime contract
- Критичность: `critical`
- Если исчезнет или сломается: пользователь перестанет получать ответы, отчеты и уведомления
- Fallback / workaround: отсутствует
- Архитектурная проблема: критичный delivery-layer задекларирован, но не зафиксированы transport path, retries, fallback и проверка фактической доставки
- Уверенность: `средняя`

#### OpenAI / Bitrix24 / Todo / WHOOP / Web Search

- Тип зависимости: external APIs
- Слой: `external service`, `config`, `secret`
- Где находится: упоминания в `AGENTS.md`, `docs/checklists/health-check.md`, `docs/PLAN.md`, `providers/README.md`
- Кто использует: предполагаемые providers, workflows и orchestrator
- Критичные контуры: `server`, `cron`, `telegram`, `manual run`, `smoke/integration/live checks`
- Должна жить в git: provider code, env schema, timeout/retry policy, health checks
- Не должна жить в git: API keys, tokens, webhook secrets
- Должна быть задокументирована отдельно: да, по каждому провайдеру
- Критичность: `critical`
- Если исчезнет или сломается: не будут работать интеллект агента, календарь, задачи, health-данные и web search сценарии
- Fallback / workaround: частично возможен только ручной режим без интеграций
- Архитектурная проблема: интеграции перечислены, но отсутствуют env-контракты, API endpoints, state wiring, лимиты, retries и правила degraded mode
- Уверенность: `средняя`

## 5. Критичные зависимости

К текущему моменту наиболее критичны:

1. `AGENTS.md` как главный runtime policy contract для Codex.
2. `.git` + `git` CLI + корректный запуск из корня репозитория.
3. `docs/STATUS.md`, потому что он уже используется как mutable runtime state.
4. `scripts/deploy.sh`, пусть пока и шаблонный, как единственная формализованная точка deploy-контура.
5. Неоформленные server-only контракты: сервисы, cron, очереди, логи, state, backup.
6. Неоформленные внешние контракты Telegram/OpenAI/Bitrix24/Todo/WHOOP/Web Search.

## 6. Скрытые и опасные зависимости

### Подтвержденные скрытые зависимости

- `scripts/deploy.sh` зависит от запуска именно из корня репозитория и от наличия каталога `.git`.
- `scripts/deploy.sh` неявно зависит от `bash`, `date`, `printf`, `git` и корректного `PATH`.
- `docs/STATUS.md` является runtime state, хотя хранится в versioned source tree.
- Вся operational логика Codex сейчас зависит от markdown-документов, а не от отдельного config layer.

### Опасные зависимости, которые в repo не оформлены

- Конкретные server path и server state.
- Реальные cron/scheduler jobs.
- Имена сервисов backend, bot, queues, ingress.
- Источники логов за последние 24 часа.
- Фактическая доставка Telegram-сообщений.
- Provider state для Bitrix24 и других интеграций.
- Backup location и rollback artifacts.

### Что специально искалось, но не найдено

- `scripts/run_sales_copilot.py`
- `deploy/` и `backup/` как отдельные runtime-контуры
- bridge-скрипты Node/Python
- hardcoded host/path значения вида `/srv/...`, `/opt/...`, `/var/...`, `/root/...`
- Google integrations
- RSS / News / Weather / Sales providers
- Larisa runtime provider
- state directories кроме намеков в `.gitignore`

Вывод: самый опасный класс зависимостей сейчас не захардкожен в коде, а вообще отсутствует в git как formalized contract.

## 7. Зависимости, которые не должны жить в коде

В текущем repo немного явных hardcoded runtime-значений, но следующие вещи нельзя оставлять только в коде или prose:

- имена systemd/docker сервисов;
- cron entries и расписания;
- server path для логов, state, reports, backups;
- env-ключи и секреты интеграций;
- Telegram delivery routing и retry policy;
- provider-specific state wiring для Bitrix24 и других API;
- health-check команды и источники логов.

Из реально найденного в коде стоит вынести или централизовать:

- проверку repo root и `.git` из `scripts/deploy.sh` в явный deploy runbook;
- повторяющееся правило `Europe/Moscow` в единый config contract;
- safety semantics `DRY_RUN` в отдельную документацию deploy-контура.

## 8. Внешние runtime-контракты

Следующие контракты должны быть зафиксированы отдельно, иначе runtime останется невоспроизводимым:

1. Git contract:
   - где расположен реальный репозиторий;
   - какие ветки обязательны;
   - какие remote используются.
2. Server contract:
   - список сервисов;
   - имена unit/container;
   - команды проверки и перезапуска;
   - точные log paths.
3. Scheduler contract:
   - cron/systemd timers/очереди;
   - расписания в МСК;
   - expected outputs и last-success markers.
4. Delivery contract:
   - Telegram bot token storage;
   - chat/channel routing;
   - retries;
   - факт доставки и fallback.
5. Provider contracts:
   - OpenAI;
   - Bitrix24;
   - Todo;
   - WHOOP;
   - Web Search;
   - для каждого нужны env keys, endpoint/base URL, таймауты, retries, rate-limit стратегия, degraded mode.
6. State contract:
   - где живут reports, logs, cache, tmp, backups;
   - что является source of truth;
   - что versioned, а что server-only.

## 9. Основные архитектурные риски

### Что оформлено правильно

- Базовые правила агента, таймзона и безопасность формализованы в `AGENTS.md`.
- Deploy-контур хотя бы начат безопасным dry-run скриптом.
- Секреты и локальные артефакты не предполагается хранить в git.
- Есть отдельные файлы для plan/status/checklists/prompts, то есть control plane уже разложен по смысловым зонам.

### Что допустимо, но плохо задокументировано

- GitHub workflow и веточная модель.
- Правила post-change и daily health-check.
- Таймзона `Europe/Moscow` как сквозной runtime policy.
- Локальные каталоги `tmp/`, `logs/`, `.cache/` как предполагаемые runtime-артефакты.

### Что архитектурно опасно

- Практически все production-зависимости находятся вне git и не описаны как внешний контракт.
- `docs/STATUS.md` смешивает runtime state и versioned source.
- Текущий docs-workspace не инициализирован как git, хотя канонический инженерный repo существует отдельно; это создает опасную двусмысленность, из какого дерева читать “истину”.
- Нет env schema и нет привязки секретов к конкретным интеграциям.
- Нет различения между code, config, state и infra на уровне реальных файлов и директорий.

## 10. Что нужно исправить в первую очередь

1. Добавить `docs/runtime_contracts/server.md` или аналог с реальными service names, cron jobs, log paths, state paths, backup paths и health-check командами.
2. Добавить `.env.example` без секретов и отдельный registry env-переменных по интеграциям Telegram/OpenAI/Bitrix24/Todo/WHOOP/Web Search.
3. Зафиксировать, где должен жить runtime state: `docs/STATUS.md` оставить как операторский журнал или вынести во внешний state/log store.
4. Превратить `scripts/deploy.sh` из шаблона в реальный runbook/script с явными шагами, prereqs и проверками после deploy.
5. Добавить реестр external providers и delivery contracts: Telegram wiring, Bitrix state wiring, правила degraded mode, retries и фактическую проверку доставки.

## 11. Краткий вывод

По текущему репозиторию можно надежно подтвердить только control plane Codex и базовый deploy/git/shell-контур.

Все жизненно важные зависимости production runtime — сервисы, cron, state, Telegram delivery, provider env/secrets, server paths, logs, reports, backups и bridge-слой — либо только задекларированы в markdown, либо полностью отсутствуют в git. Главная архитектурная проблема не в количестве hardcode, а в отсутствии явных внешних runtime-контрактов и в смешении source/config/state.
