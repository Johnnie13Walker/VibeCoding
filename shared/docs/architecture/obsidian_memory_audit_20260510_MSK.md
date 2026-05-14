# Obsidian как AI Memory Layer — архитектурный аудит и рекомендации

Цель документа: честно оценить идею «Obsidian как memory operating system для AI-first engineering OS» и предложить production-grade архитектуру вместо идеализированной картины.

Дата: 2026-05-10 МСК. Автор аудита: Claude (Opus 4.7), внешний review-агент.

---

## Часть 1: Аудит текущей идеи

### 1.1 Что хорошо

- **Принцип «institutional memory» правильный**. Большинство инженерных команд теряют 80% контекста между сессиями (своими и AI). Централизованная память — реальный выигрыш.
- **Obsidian как UI-слой** — отличный выбор: Markdown plain-text, git-friendly, bi-directional links, локальный, работает на Mac и через mobile.
- **Уже есть бэкбон** для memory: vault на сервере (`/srv/cloudbot/obsidian-vault`), private GitHub repo, OpenClaw plugin для записи из бот-сессий, рабочие триггеры (`запомни`, `дневник`, `задача`, `обсидиан`).
- **OpenClaw workspace уже использует Markdown** для AI context (AGENTS.md, SOUL.md, USER.md, MEMORY.md, memory/YYYY-MM-DD.md) — Larisa уже технически в этой парадигме.
- **Понимание провенанса**: backup-файлы с timestamp+reason — это уже engineering culture.

### 1.2 Что критически отсутствует

**Самая большая дыра — отсутствие доктрины Source of Truth.** Один и тот же факт сейчас живёт в 5+ местах:

| Факт | Где живёт сейчас |
|---|---|
| Архитектура runtime | `VibeCoding/STACK.md`, `VibeCoding/AGENTS.md`, `codex-base/shared/docs/architecture/runtime_map.md`, server `AGENTS.md`, runbooks, plugin `openclaw.plugin.json`, chat-история |
| Решения (зачем сделали X) | runbook narrative, commit messages, chat-история (теряется), backup-suffix-ы, мой audit-отчёт (тоже теряется) |
| Agent identity | `codex-base/agents/`, `openclaw/agents/main`, `openclaw/workspaces/commercial-director`, Bitrix users, `.env` файлы |
| Текущий план | `VibeCoding/ROADMAP.md`, todo-integration в Todoist, мой TodoWrite в этой сессии, разговоры в Telegram |
| Процедуры (как сделать X) | runbook'и, Makefile targets, `infra/orchestrator/workflows/*.sh`, AGENTS.md секции, скрипты в `/usr/local/bin/cloudbot-*.sh` |

Когда AI агент читает «архитектуру», он получит **разные ответы из 5 источников**, и они уже расходятся. Через 6 месяцев это превращается в неуправляемый хаос.

**Другие критические пробелы:**

- **Нет ADR (Architecture Decision Records)**. Решения принимаются ежедневно (выбор plugin vs CLI, ветка dev vs main, Obsidian vs Todoist для «задача»), но нигде не фиксируются в стандартизованном виде. Через 3 месяца никто не помнит «почему так».
- **Нет provenance для AI-записи в vault**. Сейчас нота из бота создаётся как «Cloudbot wrote this». А кто такой Cloudbot? Larisa? Какая модель? Какая сессия? Какой prompt привёл к этой ноте? Без provenance невозможно отлаживать «AI-галлюцинации в памяти».
- **Нет lifecycle документов**. Когда заметка в Inbox становится Project? Когда Project архивируется? Когда incident становится postmortem? Без lifecycle vault превращается в кладбище.
- **Семантический поиск отсутствует**. Полнотекстовый grep — это для человека. AI нужен embedding-поиск (vector DB), иначе релевантность будет рандомной при росте vault'а.
- **Нет structured handoff** между AI-агентами. Larisa не знает что делал Codex час назад. Передача контекста идёт через мою память (моего chat-instance) — она исчезает при `/clear`.
- **Нет lock'ов / concurrency-модели для записи в vault несколькими AI**. Сейчас работает один Larisa + один OpenClaw plugin + git-lock. При 3+ агентах будут race-условия.
- **Operational state и semantic memory свалены в одну кучу**. «Какой commit задеплоен сейчас» — operational state, должен жить в state-store (release id файл, БД). «Почему мы выбрали такой деплой-flow» — semantic memory, должно жить в Obsidian. Сваливание создаёт illusion of source-of-truth и ломает обе системы.

### 1.3 Где будут проблемы через 3–6 месяцев

| Риск | Сценарий | Когда |
|---|---|---|
| **Context divergence** | AI-агент A видит архитектуру по `STACK.md` (старая), агент B — по `runtime_map.md` (новая). Они принимают противоречивые решения. | 2–3 мес |
| **Memory rot** | Старые заметки про Bitrix-флоу из марта остались, новые декабрьские добавились — поиск возвращает оба, агент берёт первый. | 3 мес |
| **Decision amnesia** | «А почему мы выбрали OpenClaw plugin вместо AGENTS.md routing?» — никто не помнит, начинают переделывать. | 4–6 мес |
| **Multi-agent collision** | Larisa и Codex параллельно пишут в один и тот же daily note, один push побеждает, второй теряется. Без логирования conflict — потеря данных. | 1–2 мес после второго агента |
| **Trust decay** | AI говорит «runbook говорит X», а runbook 4-месячной давности и врёт. Пользователь перестаёт доверять AI-ответам. | 3–4 мес |
| **Vault inflation** | Каждое сообщение пользователя сохраняется через `запомни:` без фильтрации → 50k нот за полгода → поиск тормозит, релевантность падает. | 6 мес |
| **Knowledge fragmentation** | Vault растёт, появляются дубликаты («auth-flow.md», «authentication.md», «как-работает-логин.md»), graph становится несвязным. | 3 мес |
| **Onboarding boundary** | Новый человек / агент приходит — нет «entry point» в vault, не знает где начинать читать. Onboarding занимает дни. | сразу при добавлении третьего человека/агента |

---

## Часть 2: Принципы — что Obsidian ДОЛЖЕН и НЕ ДОЛЖЕН делать

### 2.1 Obsidian ХОРОШ для (= должно жить здесь)

- **Semantic memory** — почему, контекст, причины, решения, выводы, lessons learned
- **Long-form narrative** — runbook'и, ADR, postmortems, design docs, brainstorms
- **Связи между концептами** — bi-directional links между ADR ↔ incident ↔ postmortem ↔ project
- **Human-AI shared workspace** — место где и человек, и AI читают/пишут одинаково
- **Onboarding entry-point** — первое место куда смотрит новый человек / новый AI агент
- **Slow-changing reference** — архитектура, конвенции, философия проекта

### 2.2 Obsidian ПЛОХ для (= должно жить ВНЕ его)

- **Time-series logs** — события деплоев, request traces, metrics. Это для Loki/ClickHouse/Grafana, а не Markdown.
- **Operational state** — «какой commit задеплоен сейчас», «какой контейнер running», «какой lock держится». Это в state-store (release_id файлы, etcd, redis).
- **High-frequency writes** — каждый Telegram update, каждое API hit. Перегрузит git, sync станет тормозить, vault распухнет.
- **Sensitive data** — токены, ключи, личные переписки. Уже есть `.gitignore`, но как только агенты автоматически начнут писать всё подряд — проблема.
- **Structured data для query** — задачи с дедлайнами, приоритетами, статусами лучше в Todoist/Linear/Bitrix; Obsidian — только narrative о них.
- **Real-time coordination** — координация между параллельными агентами не должна идти через git push (latency секунды). Нужен redis/queue.

### 2.3 Многослойная Memory-модель

Memory — это не один слой. Минимум четыре:

```
┌─────────────────────────────────────────────────────────────────┐
│ L4: Reflective memory (long-term, semantic)                     │
│     Obsidian vault: ADR, runbook, postmortem, architecture      │
│     Update: human или AI после reasoning                        │
│     TTL: годы                                                   │
├─────────────────────────────────────────────────────────────────┤
│ L3: Episodic memory (medium-term, narrative)                    │
│     Obsidian: daily notes, project journals, agent session logs │
│     Update: AI после сессии или crontab digest                  │
│     TTL: месяцы → архив → удаление                              │
├─────────────────────────────────────────────────────────────────┤
│ L2: Working memory (short-term, structured)                     │
│     Redis/SQLite/JSON: pending tasks, active sessions, locks    │
│     Update: каждое действие                                     │
│     TTL: дни                                                    │
├─────────────────────────────────────────────────────────────────┤
│ L1: Operational state (real-time, source-of-truth)              │
│     state files / БД / API: current release, container status   │
│     Update: каждый event                                        │
│     TTL: момент                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Twin doctrine**: каждый L1/L2 факт может иметь narrative-двойника в L4 («почему мы пришли к этой конфигурации»), но L4 НЕ источник истины для L1. Это критически важная разница.

---

## Часть 3: System of Record Matrix

Кто owner какого факта. Если факт есть в нескольких местах — **только одно** считается истиной, остальные — read-only mirrors.

| Факт | Source of Truth | Mirror в Obsidian | Кто пишет в SoT |
|---|---|---|---|
| Архитектура runtime | `Architecture/MAP.md` (Obsidian) | — (это и есть SoT) | Human + AI с ADR |
| Текущая версия деплоя | `/opt/cloudbot-runtime/<agent>/current` symlink | `Operations/deploys/YYYY-MM-DD.md` (changelog после деплоя) | deploy script |
| Текущий план / roadmap | `Roadmap/ROADMAP.md` (Obsidian) | — | Human |
| Список агентов | `Agents/INDEX.md` (Obsidian) | — | Human + agent self-register |
| Open задачи | Todoist (через API) | `Tasks/_index.md` snapshot daily | Human + AI |
| Active incidents | `Incidents/active/` (Obsidian) | — | AI alert + human |
| Resolved incidents | `Incidents/postmortems/` (Obsidian) | — | AI write-up + human review |
| Архитектурные решения | `Decisions/ADR-NNNN-*.md` | — | Human + AI propose |
| Env-переменные (имена) | `Operations/env/REGISTRY.md` (только имена и назначение, не значения) | — | Human |
| Env-переменные (значения) | server `.env` файлы | НЕТ (никогда не коммитить) | Human only |
| Server topology | `Operations/topology.md` + Terraform/Ansible (если будет) | — | Human |
| Integration contracts | `Integrations/<name>.md` | — | Human + AI |
| Prompts | `Prompts/<agent>/<purpose>.md` | — | Human + AI |
| Daily activity | `Daily/YYYY-MM-DD.md` | — | AI (autosummary) + human |
| Agent reasoning chains | `Agents/<name>/sessions/YYYY-MM-DD-<sid>.md` | — | AI после каждой сессии |
| Code | git репозитории | НЕТ (link only) | Human + AI |
| Commits | git history | mention в Daily/ADR/incident | Human + AI |
| Test results | CI artifacts | mention в incident при failure | CI |

**Правило**: если ты не уверен где SoT, спроси «кто это пишет в первую очередь?» Это и есть SoT.

---

## Часть 4: Vault Architecture

### 4.1 Folder tree (production-grade)

```
white-coding/                           # vault root
├── 00-Index/                            # entry points
│   ├── README.md                        # «прочти первым»
│   ├── MAP.md                           # smart links во все области
│   ├── GLOSSARY.md                      # термины проекта
│   └── ONBOARDING.md                    # для нового человека/агента
│
├── 01-Roadmap/                          # планы
│   ├── ROADMAP.md                       # текущий roadmap
│   ├── milestones/                      # M1-..., M2-...
│   └── archive/                         # завершённые milestones
│
├── 02-Architecture/                     # архитектура (slow-changing)
│   ├── MAP.md                           # обзорная карта системы
│   ├── runtime/                         # runtime контуры
│   ├── data-flow/                       # потоки данных
│   ├── integrations/                    # external systems
│   └── ai-systems/                      # multi-agent topology
│
├── 03-Decisions/                        # ADR
│   ├── 0001-use-openclaw-as-runtime.md
│   ├── 0002-obsidian-as-memory-layer.md
│   ├── 0003-tasks-go-to-obsidian-not-todoist.md
│   └── INDEX.md                          # таблица всех ADR
│
├── 04-Agents/                           # AI agents registry
│   ├── INDEX.md                         # все агенты с краткими описаниями
│   ├── larisa/
│   │   ├── IDENTITY.md
│   │   ├── CAPABILITIES.md
│   │   ├── PROMPTS.md
│   │   ├── INTEGRATIONS.md
│   │   └── sessions/                    # episodic memory
│   ├── commercial-director/
│   ├── codex/
│   └── claude-code/
│
├── 05-Integrations/                     # внешние системы
│   ├── INDEX.md
│   ├── telegram.md
│   ├── bitrix24.md
│   ├── todoist.md
│   ├── github.md
│   └── obsidian-vault.md                # сама эта vault как integration
│
├── 06-Operations/                       # operational reference
│   ├── topology.md                      # серверы, сети
│   ├── env/REGISTRY.md                  # имена env vars (без значений)
│   ├── runbooks/                        # «как сделать X»
│   ├── deploys/YYYY-MM-DD-<release>.md  # changelog после каждого деплоя
│   └── access/                          # SSH хосты, deploy keys (имена не значения)
│
├── 07-Workflows/                        # automation
│   ├── INDEX.md
│   ├── cron/                            # все cron jobs
│   ├── orchestration/                   # multi-step flows
│   └── triggers/                        # webhooks, events
│
├── 08-Incidents/                        # инциденты
│   ├── active/                          # сейчас идёт
│   ├── postmortems/YYYY-MM-DD-<title>.md
│   └── INDEX.md
│
├── 09-Projects/                         # текущие проекты
│   ├── obsidian-integration/            # этот проект
│   ├── bitrix-duplicate-merge/          # другой проект
│   └── archive/                         # завершённые
│
├── 10-Research/                         # исследования
│   ├── ai-tooling/
│   ├── infrastructure/
│   └── benchmarks/
│
├── 11-Prompts/                          # библиотека promptов
│   ├── system/                          # системные prompts
│   ├── tasks/                           # task-specific
│   ├── reviewers/                       # для code/audit reviewers
│   └── INDEX.md
│
├── 12-Logs/                             # episodic narrative logs
│   ├── daily/YYYY-MM-DD.md              # daily summary
│   ├── deploys/                         # mirror деплоев
│   └── changes/                         # significant changes log
│
├── 13-Inbox/                            # быстрая запись (требует triage)
│   └── YYYY-MM-DD-HHMM-<slug>.md
│
├── 14-Memory/                           # ИИ-curated long-term knowledge
│   ├── people/                          # про команду, клиентов
│   ├── lessons-learned/
│   └── patterns/                        # повторяющиеся паттерны
│
├── 15-Sandbox/                          # эксперименты, draft-ы
│   └── _README.md                       # «здесь нет SoT, всё временно»
│
├── 99-Archive/                          # на удаление через 90 дней
│   └── _AUTO_DELETE_AFTER.md
│
├── _Templates/                          # Obsidian templates
│   ├── adr.md
│   ├── postmortem.md
│   ├── runbook.md
│   ├── agent.md
│   ├── integration.md
│   ├── daily.md
│   └── project.md
│
└── _Meta/                               # метаданные vault'а
    ├── CONVENTIONS.md                   # naming, tagging, frontmatter
    ├── LIFECYCLE.md                     # как документы переходят между папками
    ├── AUTOMATION.md                    # что автоматически пишется куда
    └── HEALTH.md                        # статус vault: количество нот, ошибки, дубли
```

**Numbered prefixes** (00-, 01-…) — навигация. AI агенты будут читать `00-Index/MAP.md` первым делом.

### 4.2 Naming convention

| Тип | Шаблон | Пример |
|---|---|---|
| ADR | `NNNN-kebab-title.md` | `0042-use-redis-for-locks.md` |
| Postmortem | `YYYY-MM-DD-incident-slug.md` | `2026-04-15-bitrix-token-expired.md` |
| Daily | `YYYY-MM-DD.md` | `2026-05-10.md` |
| Project | `kebab-name/_README.md` + sub-files | `obsidian-integration/_README.md` |
| Agent doc | `<agent>/IDENTITY.md`, `<agent>/CAPABILITIES.md` | — |
| Inbox quick note | `YYYY-MM-DD-HHMM-slug.md` | `2026-05-10-1154-claude-audit-smoke.md` |
| Deploy log | `YYYY-MM-DD-HHMM-<service>-<release>.md` | `2026-05-10-0844-larisa-dev_2bb6635.md` |
| Runbook | `<noun>-<verb>-MSK.md` | `obsidian-vault-bootstrap-MSK.md` |

**Правила:**
- Слова: kebab-case в filename, Title Case в `# H1`
- Даты: ISO 8601 (`YYYY-MM-DD`), таймзона МСК фиксируется в frontmatter
- Slug: первые 5–8 значимых слов, без стоп-слов
- Расширение: только `.md` (не `.MD`, не `.markdown`)

### 4.3 Frontmatter schema (универсальный)

Каждая нота **обязана** иметь frontmatter:

```yaml
---
type: adr | postmortem | runbook | daily | agent | integration | project | inbox | research | prompt | deploy
title: <human-readable title>
status: draft | active | deprecated | archived
created: 2026-05-10T11:54:00+03:00
updated: 2026-05-10T11:54:00+03:00
tz: Europe/Moscow

# Provenance
author: human:eshchemelev | ai:larisa@gpt-5.3 | ai:claude-code@opus-4.7 | system:cron
session: <session-id-if-ai>
agent_chain: [larisa, obsidian-router, obsidian_cli]    # цепочка для AI-записей

# Linking
sot: true | false                                       # является ли источником истины
mirrors: ["[[Operations/topology.md#larisa-server]]"]   # если mirror — на что
related: ["[[Decisions/0042-use-redis.md]]", "[[Incidents/postmortems/2026-04-15-...]]"]

# Lifecycle
expires: 2026-08-10                                     # для inbox/sandbox/draft
review_after: 2026-11-10                                # для активных доков
archive_after_days: 90                                  # для inbox

# Discoverability
tags: [agent, runtime, obsidian, openclaw]
projects: ["[[09-Projects/obsidian-integration/_README.md]]"]
agents: ["[[04-Agents/larisa/IDENTITY.md]]"]
---
```

Не все поля обязательны для каждого типа — `_Templates/` задаёт минимальный набор для каждого.

### 4.4 Tag taxonomy

Теги — горизонтальная классификация поверх folder-вертикали. Контролируемый словарь.

**Domain tags (что это):**
`#agent` `#integration` `#runtime` `#deploy` `#incident` `#postmortem` `#decision` `#runbook` `#prompt` `#research` `#daily` `#project`

**Status tags (в каком состоянии):**
`#status/draft` `#status/active` `#status/deprecated` `#status/archived` `#status/blocked`

**Severity tags (для incident/risk):**
`#severity/critical` `#severity/high` `#severity/medium` `#severity/low` `#severity/info`

**Provenance tags (кто написал):**
`#by/human` `#by/ai/larisa` `#by/ai/claude-code` `#by/ai/codex` `#by/system`

**Domain area tags (про что):**
`#area/auth` `#area/payments` `#area/sales` `#area/marketing` `#area/devops` `#area/data`

**Lifecycle tags (для автоматики):**
`#lifecycle/needs-triage` `#lifecycle/needs-review` `#lifecycle/expired` `#lifecycle/archive-candidate`

Запрет: ad-hoc теги без префикса. Дублирование тег-folder допускается только для cross-cutting (`#agent` в `04-Agents/`).

### 4.5 Linking rules

- **Wikilinks** `[[file]]` — основная форма. Markdown ссылки `[text](path)` — только когда нужен alias или ссылка вне vault.
- **Каждый ADR** ссылается на: предыдущие связанные ADR, integrations/agents/projects к которым относится.
- **Каждый Postmortem** ссылается на: incident запись, ADR от которого пошёл вред, runbook который надо обновить.
- **Каждый Project** имеет `_README.md` со списком всех связанных нот.
- **MAP.md** в 00-Index/ — кураторский граф главных entry points.
- **Backlinks** Obsidian показывает автоматически — это «free graph».
- **Никаких висячих ссылок**: linter в pre-commit-хуке проверяет что все `[[]]` resolved.

---

## Часть 5: Lifecycle и Governance

### 5.1 Lifecycle states (для всех типов)

```
[draft] ──promote──> [active] ──deprecate──> [deprecated] ──archive──> [archived] ──delete──> ⌫
                          │
                          └─review─► [active]  (loop)
```

- **draft**: написано, не финализировано. В `13-Inbox/` или `15-Sandbox/`. TTL 30 дней по умолчанию.
- **active**: source of truth, поддерживается. Должно иметь `review_after` (год по умолчанию).
- **deprecated**: больше не SoT, но ещё доступен для исторического чтения. Должна быть ссылка на «новую правду».
- **archived**: в `99-Archive/`, не индексируется поиском. Удаляется через 90 дней.

Переход — через изменение `status:` во frontmatter + `git mv` в нужную папку. Автоматизация (см. 7.) делает эти переходы по cron.

### 5.2 Доктрина Source of Truth

**Один факт = один SoT. Mirror'ы помечены `sot: false` + `mirrors:` ссылкой на оригинал.**

Если факт оказался в двух местах с `sot: true` — это **breach**, регулярный health-check ловит и эскалирует.

Когда mirror рассинхронизировался с SoT — он считается несуществующим, AI-агент должен идти к SoT.

### 5.3 ADR (Architecture Decision Records) — обязательны

Шаблон `_Templates/adr.md`:

```markdown
---
type: adr
title: <decision in active voice>
status: proposed | accepted | superseded
created: ...
sot: true
related: [...]
---

# ADR-NNNN: <title>

## Context

<что заставило принять решение, какие constraint'ы>

## Decision

<что решили, в одном предложении>

## Consequences

### Positive
- ...

### Negative
- ...

### Neutral
- ...

## Alternatives considered

- **<alt 1>**: <почему не выбрали>
- **<alt 2>**: <почему не выбрали>

## Supersedes / superseded by

- Supersedes: [[ADR-NNNN]]
- Superseded by: [[ADR-NNNN]]  (заполняется когда заменяется)
```

**Когда писать ADR:** любое решение которое влияет на > 1 модуль / агента, или которое было сложно (рассматривали >1 варианта).

Эта сессия должна была родить минимум 4 ADR:
- `ADR: использовать OpenClaw plugin вместо AGENTS.md routing`
- `ADR: bind-mount /srv/cloudbot/obsidian-vault в контейнер вместо клона внутрь workspace`
- `ADR: «задача ...» направляется в Obsidian, не в Todoist`
- `ADR: vault git repo separate from project repos`

Без ADR через 3 месяца ты будешь спорить с самим собой.

### 5.4 Incident → Postmortem flow

```
detect ──► 08-Incidents/active/<slug>.md (status: active)
   │       └── минимальные поля: time, symptoms, impact
   ▼
respond ──► обновляется тот же файл (timeline append-only)
   │       └── каждое действие — line `HH:MM МСК | actor | action`
   ▼
resolve ──► status → resolved, добавляется resolution
   │
   ▼
postmortem ──► move в 08-Incidents/postmortems/YYYY-MM-DD-<slug>.md
              + ссылки на ADR (если меняется архитектура)
              + ссылки на runbook updates
              + lessons learned → 14-Memory/lessons-learned/
```

---

## Часть 6: AI Collaboration Layer

### 6.1 Agent identity и provenance

Каждое AI-действие в vault должно быть **идентифицируемым**.

**Минимальные поля в frontmatter AI-генерируемой ноты:**
```yaml
author: ai:larisa@gpt-5.3-codex          # agent_id @ model
session: tg-msg-19473829                  # provider session id
agent_chain: [larisa, obsidian-router, obsidian_cli]
prompt_hash: sha256:abcd1234              # hash промпта для дедупликации
human_initiator: 81681699                 # кто инициировал
```

Это даёт:
- Audit trail (кто, что, когда, из какого prompt)
- Дедупликацию (один и тот же prompt от одного агента не генерит две ноты)
- Conflict resolution (если два агента спорят — видно кто из какой сессии писал)

### 6.2 Handoff structures

Для multi-agent работы нужен **explicit handoff format** (новый тип в vault):

`14-Memory/handoffs/YYYY-MM-DD-HHMM-<from>-to-<to>.md`:

```yaml
---
type: handoff
from: ai:claude-code@opus-4.7
to: ai:larisa@gpt-5.3
created: ...
session_from: <id>
session_to: <id-or-empty-if-async>
context_window_full: true | false
expires: <12h по умолчанию>
---

# Handoff

## Что я делал
...

## Что я понял
...

## Что я НЕ доделал
...

## Открытые вопросы
...

## Зависимости (что должно случиться до того как ты начнёшь)
...
```

Это формализует то что ты сегодня просил (`handoff_obsidian_integration.md`) — но как **системную практику**.

### 6.3 Read/write rules для AI

**Read rules:**
- Любой агент **обязан** читать `00-Index/MAP.md` в начале сессии (entry point).
- Перед действием в области — читать `<area>/_README.md` (если есть).
- При неопределённости — backlinks через graph + semantic search (см. 7.3).

**Write rules:**
- AI-агент пишет только в свой `04-Agents/<name>/` + в `13-Inbox/` + в `12-Logs/`.
- Запись в `02-Architecture/`, `03-Decisions/`, `06-Operations/runbooks/` — только через **proposal flow**: AI пишет в `13-Inbox/proposals/`, человек одобряет → `git mv`.
- Запись в `08-Incidents/active/` — разрешена для AI alert-агентов.
- Никогда: запись в `_Meta/`, `_Templates/`, `99-Archive/`.

### 6.4 Conflict resolution

При параллельной записи в один файл (пример: два агента в `daily/2026-05-10.md`):

1. **Append-only journal** для daily/incident — новый блок добавляется в конец, не перезаписывает существующее.
2. **CRDT не нужен** — git merge handles 90% случаев на уровне строк.
3. **Lock на vault не масштабируется** при росте агентов — лучше per-file lock через redis (короткий TTL).
4. **Конфликт = incident** автоматически (`08-Incidents/active/`) с детектированием через git hook.

---

## Часть 7: Automation Architecture

### 7.1 Ingestion pipelines (что → vault)

| Источник | Триггер | Куда пишет | Формат | Кто |
|---|---|---|---|---|
| Telegram сообщение пользователя `запомни:` | message_received | `13-Inbox/` | quick note | OpenClaw plugin |
| Telegram `создай задачу:` | message_received | Obsidian `Tasks/` | task | OpenClaw plugin |
| Деплой завершён | deploy webhook | `06-Operations/deploys/` + `12-Logs/deploys/` | deploy log | deploy script |
| Git commit в codex-base | post-commit hook | `12-Logs/changes/YYYY-MM-DD.md` (append) | one-liner | git hook → vault sync script |
| Larisa session завершена | session_end | `04-Agents/larisa/sessions/<sid>.md` | session summary (Larisa сама пишет) | Larisa |
| Incident detected (alert) | alert webhook | `08-Incidents/active/<slug>.md` | incident skeleton | alert агент |
| ADR создан в proposal flow | manual | `03-Decisions/` после approve | ADR | human approve + script |
| Cron job выполнен | post-run | `12-Logs/daily/<date>.md` (append) | one-liner | cron wrapper |
| Github PR opened/merged | webhook | `12-Logs/changes/` + ссылка из project | PR record | github webhook |
| Server restart | systemd hook | `12-Logs/daily/<date>.md` + если incident → `08-Incidents/active/` | event line | systemd ExecStart wrapper |

**Ключевой паттерн:** lightweight events идут в `12-Logs/` (append-only, daily rotation), heavyweight artifacts (ADR, postmortem) — через explicit flow.

### 7.2 Read pipelines (vault → AI агенты)

| Потребитель | Что читает | Когда |
|---|---|---|
| Любой AI агент | `00-Index/MAP.md`, `00-Index/GLOSSARY.md` | start of session |
| Larisa (в OpenClaw) | `04-Agents/larisa/*` + workspace AGENTS.md | каждый prompt build |
| Code review агент | `02-Architecture/`, `03-Decisions/`, `_Meta/CONVENTIONS.md` | при code review |
| Incident response агент | `08-Incidents/active/`, related runbooks | при alert |
| Onboarding агент | `00-Index/ONBOARDING.md`, `04-Agents/INDEX.md`, `09-Projects/INDEX.md` | при «что у нас есть?» |
| MCP-сервер для vault | весь vault (search) | per query |

### 7.3 Search infrastructure

Полнотекстовый grep — недостаточен. Нужен **vector index**:

```
vault (markdown files)
   │
   ├──► [chunker] (по headings + ~500 token windows)
   │
   ├──► [embedder] (text-embedding-3-large или local)
   │
   ├──► [vector DB] (qdrant / weaviate / sqlite-vec)
   │
   └──► [MCP server] (выдаёт top-k results AI агенту)
```

Reindex при каждом git push в vault (через webhook или cron каждые 5 минут).

Метаданные из frontmatter (`type`, `status`, `tags`) → дополнительный фильтр в search query (например «search ADR active about openclaw»).

### 7.4 MCP server для vault

Для AI агентов: единый MCP-сервер `vault://` который отдаёт:
- `vault://list?type=adr&status=active` — все active ADR
- `vault://search?q=openclaw+routing&top_k=10` — semantic search
- `vault://read?path=03-Decisions/0042-...` — конкретная нота
- `vault://propose?path=...&content=...` — записать в `13-Inbox/proposals/`
- `vault://link?from=...&to=...` — добавить связь

Это унифицирует как **все** AI-агенты ходят в память — независимо от того ChatGPT, Claude, локальная модель или Codex.

### 7.5 Health check (cron daily)

Скрипт, который каждый день в 09:00 МСК пишет `_Meta/HEALTH.md`:

```yaml
notes_total: 1247
notes_by_type: {adr: 42, postmortem: 18, runbook: 56, daily: 410, ...}
notes_active: 891
notes_archived: 209
notes_inbox_old: 12     # > 30 дней без triage — alert
broken_links: 0         # цель
duplicate_titles: 0     # цель
sot_breaches: 0         # два файла с sot:true на один факт
expired_drafts: 3       # требуют решения
agent_provenance_missing: 7  # AI ноты без полного frontmatter
last_index_at: 2026-05-10T09:00+03:00
last_git_push: 2026-05-10T08:43+03:00
sync_lag_minutes: 17
```

Всё что != 0 в «целевых» полях → alert через бот.

---

## Часть 8: Implementation Roadmap

Не пытайся сделать всё сразу. Поэтапно.

### Phase 0 (this week) — фундамент без нового кода

- [ ] Создать `00-Index/`, `_Templates/`, `_Meta/CONVENTIONS.md`, `_Meta/LIFECYCLE.md` — это **константы**, кодить не надо
- [ ] Перенести существующие runbook'и из `VibeCoding/shared/docs/runbooks/` → `06-Operations/runbooks/`
- [ ] Перенести `VibeCoding/shared/docs/integrations/*.md` → `05-Integrations/`
- [ ] Написать **первые 5 ADR** ретроактивно (включая «зачем OpenClaw plugin», «зачем Obsidian как memory», «задача в Obsidian»)
- [ ] Создать `04-Agents/larisa/IDENTITY.md`, `04-Agents/claude-code/IDENTITY.md` — start small
- [ ] Поставить frontmatter linter (pre-commit-хук, отказывает push если frontmatter неправильный)

### Phase 1 (this month) — automation MVP

- [ ] Скрипт `vault-ingest deploy` — деплой пишет в `06-Operations/deploys/`
- [ ] Cron `vault-health.sh` — daily report в `_Meta/HEALTH.md`
- [ ] Cron `vault-archive.sh` — переносит inbox > 30 дней в archive
- [ ] Linter `vault-lint.sh` — проверяет broken links, missing frontmatter, duplicate sot
- [ ] Расширить obsidian-router триггерами: `ADR: ...`, `incident: ...`, `decision: ...`
- [ ] Написать `00-Index/MAP.md` — первый кураторский MAP
- [ ] Каждое утро Larisa пишет `12-Logs/daily/<date>.md` (digest)

### Phase 2 (next 3 months) — AI memory infrastructure

- [ ] Vector index (qdrant локально на сервере)
- [ ] MCP server `vault://` (на node, в OpenClaw extension format)
- [ ] Все агенты переключены на чтение через MCP
- [ ] Handoff system формализован (template + automated handoff cron)
- [ ] Provenance enforce'ится для всех AI-записей
- [ ] Conflict detection через git hook → автоматический incident

### Phase 3 (6+ months) — production-grade

- [ ] Vault shard'ируется по доменам (если > 5000 нот) — sub-vault per agent
- [ ] Multi-vault federation (если несколько проектов)
- [ ] Dashboards (Obsidian dataview plugin или внешний Grafana с MD-source)
- [ ] AI-powered triage агент: разгребает inbox, предлагает promote/archive
- [ ] Knowledge gap detection: AI находит «о чём мы давно не писали» и спрашивает

---

## Часть 9: Что НЕ делать

| Соблазн | Почему плохо |
|---|---|
| «Всё в Obsidian, сразу» | Обвал из-за смешения L1/L2/L4 памяти. Obsidian не БД. |
| AI пишет всё что видит | Vault забьётся мусором за неделю. Нужен фильтр / triage. |
| Один большой ROADMAP.md | Не масштабируется. Используй `01-Roadmap/milestones/`. |
| Свободные теги без taxonomy | Через 2 месяца — 200 семантически близких тегов. |
| Folders без numbered prefix | AI не знает в каком порядке читать. Numbers = порядок onboarding. |
| Vault содержит секреты | Один git push в публичный — катастрофа. **Никогда.** |
| Sync через rsync/Dropbox | Нужен git. Только git даёт history + atomic commits + conflict detection. |
| MCP server на бэкэнд напрямую | Делает Obsidian SoT для operational state. Это L1, не L4. |

---

## Часть 10: TL;DR — что делать сегодня

Если у тебя есть один день — сделай **только три вещи**, всё остальное может подождать:

1. **Создай `_Templates/adr.md`** и напиши 5 ADR ретроактивно. Это самая большая ROI-инвестиция; через месяц спасёт тебя от «почему мы это сделали?».

2. **Создай `_Meta/CONVENTIONS.md`** с frontmatter schema, naming, tag taxonomy. Это **constitutional document** — без него AI агенты не смогут писать консистентно.

3. **Напиши `00-Index/MAP.md`** — кураторская карта vault'а. Это будет первый файл, который читает любой новый AI агент в начале сессии.

Остальное (vector search, MCP server, automation pipelines) — это уже инфраструктура. Без 1-2-3 эта инфраструктура построится поверх хаоса и закрепит хаос.

---

## Заключение

**Главная мысль:** Obsidian — это **L4 (reflective memory)** в многослойной модели. Не пытайся затащить в него L1-L3. Используй каждый слой по назначению.

**Главный риск:** превратить vault в файловый dump через `запомни:` без архитектуры. Inbox без triage = свалка.

**Главный win:** ADR + frontmatter + provenance дают AI-агентам общую почву для рассуждения, без них multi-agent setup будет генерить противоречия.

**Главное упущение в текущем подходе:** нет System of Record matrix — каждый факт в 5 местах, и эти 5 уже расходятся (видно по этой сессии: `STACK.md`, `runtime_map.md`, server `AGENTS.md`, runbook'и, plugin manifest).

**Что бы я сделал первым делом**, будь это моя система: написал бы `00-Index/MAP.md` + `_Meta/CONVENTIONS.md` + 5 ADR ретроактивно. После этого всё остальное (структура папок, automation, MCP) выстроится естественно — потому что появится язык на котором это можно описать.
