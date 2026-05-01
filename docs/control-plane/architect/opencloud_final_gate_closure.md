# 1. Larisa smoke checklist

Дата: 2026-04-27, МСК.

Назначение: production-safe owner checklist для Ларисы Ивановны после любых будущих structural changes. Ничего из списка ниже этим пакетом не выполняется.

Контур-опоры, подтвержденные ранее:

- canonical code source: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- live runtime pointer Ларисы: `/opt/cloudbot-runtime/larisa/current`
- active cron file: `/etc/cron.d/cloudbot-larisa-daily-brief`
- system runner: `/usr/local/bin/cloudbot-larisa-daily-brief.sh`
- legacy report/log path: `/home/ops/cloudbot-larisa-agent/reports/larisa_daily_brief_cron.log`

| check_id | what to verify | expected healthy result | where to check | what indicates failure | severity | rollback urgency |
|---|---|---|---|---|---|---|
| LARISA-SMOKE-01 | Telegram delivery alive | Лариса отвечает в правильный Telegram-контур; сообщения уходят тем ботом и в тот чат, который ожидается для Ларисы | live Telegram dialog Ларисы; route/env docs; server env path `/etc/openclaw/larisa.env` [values not checked here] | тишина, ответ не приходит, сообщение уходит не тем ботом или в чужой чат | critical | immediate |
| LARISA-SMOKE-02 | Daily brief delivery | ежедневный brief доставляется полностью, без обрыва и без пустого тела | Telegram thread Ларисы; `larisa_daily_brief_cron.log`; scoped runtime `/opt/cloudbot-runtime/larisa/current` | brief не пришёл, пришёл пустой, пришёл дубликат или с явным stack trace | critical | immediate |
| LARISA-SMOKE-03 | Morning brief timing validation | daily brief приходит в ожидаемое утреннее окно и cron linkage остаётся тем же | `/etc/cron.d/cloudbot-larisa-daily-brief`; timestamp in `larisa_daily_brief_cron.log`; latest Telegram delivery timestamp | доставка ушла мимо окна, cron не соответствует ожидаемой привязке, delivery плавает | high | same day |
| LARISA-SMOKE-04 | Calendar access | блок встреч/календаря в brief заполняется осмысленно; нет признаков полного отсутствия доступа | Telegram brief content; Larisa calendar-related output; supporting code/docs in `agents/larisa_ivanovna/providers/calendar_provider.py` and `docs/api_integrations.md` | блок встреч пустой при наличии встреч, явная ошибка Bitrix/calendar access, fallback text вместо данных | critical | immediate |
| LARISA-SMOKE-05 | Tasks access | блок задач заполняется и выглядит как живой снимок текущих задач | Telegram brief content; task-related output; server-side Todo/Todoist integration evidence [exact file path not confirmed] | блок задач пустой/obsolete, явная ошибка tasks provider, stale snapshot | high | same day |
| LARISA-SMOKE-06 | Weather/news/search response | команды или brief-блоки по погоде, новостям и search дают осмысленный ответ без route mismatch | Telegram commands `/weather`, `/search`, `/web`, `/find` per `agents/larisa_ivanovna/config.py`; Telegram thread; supporting docs in `docs/api_integrations.md` | команда молчит, отвечает не тем workflow, отдает raw error, search/news/weather пусты без объяснения | high | same day |
| LARISA-SMOKE-07 | Command routing | команды `/today`, `/brief`, `/day`, `/meetings`, `/tasks`, `/weather`, `/plan-day`, `/plan` уходят в ожидаемый маршрут Ларисы | Telegram dialog; command map docs in `docs/api_integrations.md`; routing layer in `cloudbot/orchestrator/router.py` [no execution here] | команда попадает в другой агент, неизвестную ветку или возвращает irrelevant response | critical | immediate |
| LARISA-SMOKE-08 | Formatter output sanity | Telegram-формат brief не деградировал: читаемый формат, без битого HTML/Markdown, без дублей ключевых блоков | live Telegram message; formatter references in `agents/larisa_ivanovna/formatters/telegram_brief.py`, `telegram_meetings.py` | поломанная разметка, дубль блоков, unreadable text, missing headings | medium | observe |
| LARISA-SMOKE-09 | Logs generation | при запланированном запуске появляется свежий лог, а лог не застрял на старом timestamp | `/home/ops/cloudbot-larisa-agent/reports/larisa_daily_brief_cron.log`; runtime verify evidence in docs | лог не обновляется, timestamp старый, file missing [not confirmed if rotated elsewhere] | high | same day |
| LARISA-SMOKE-10 | Reports freshness | последний production artifact выглядит свежим относительно расписания | report/log timestamp in legacy report dir; latest Telegram brief timestamp | stale artifact при живом cron или mismatch между cron/log/telegram | high | same day |
| LARISA-SMOKE-11 | Cron linkage awareness | scoped runtime Ларисы остаётся связан с отдельным Larisa cron, а не внезапно с generic current | `/etc/cron.d/cloudbot-larisa-daily-brief`; `/usr/local/bin/cloudbot-larisa-daily-brief.sh`; runtime map docs | runner/cron указывает на неожиданный runtime path, especially generic pointer without explicit decision | critical | immediate |
| LARISA-SMOKE-12 | Wrong bot token / chat fallback detection | Лариса не использует shared fallback так, что доставка уходит в чужой контур | Telegram destination behavior; Larisa env contract; fallback-sensitive code in `agents/larisa_ivanovna/config.py` and deploy docs | сообщение уходит в Sales/generic чат, wrong bot identity, silent fallback to common token/chat | critical | immediate |

# 2. Lev/Sales smoke checklist

Назначение: production-safe owner checklist для Льва Петровича / Sales Copilot после любых будущих structural changes. Не выполнять автоматически.

Контур-опоры, подтвержденные ранее:

- generic sales runtime pointer: `/opt/cloudbot-runtime/current`
- active cron file: `/etc/cron.d/cloudbot-sales-reports`
- live bridge script in repo: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/scripts/run_sales_copilot.py`
- token-file reference: `/root/.openclaw/telegram/commercial-director.bot_token`
- Bitrix state reference: `/opt/openclaw/state/bitrix_app`
- report/log directory for sales runtime: `/home/ops/cloudbot-sales-agent/reports/` [exact filenames not confirmed]

| check_id | what to verify | expected healthy result | where to check | what indicates failure | severity | rollback urgency |
|---|---|---|---|---|---|---|
| SALES-SMOKE-01 | Morning sales report delivery | утренний sales report приходит в правильный Telegram-контур в ожидаемое окно | Telegram chat Льва/ Sales; `/etc/cron.d/cloudbot-sales-reports`; sales reports/log timestamps under `/home/ops/cloudbot-sales-agent/reports/` [exact filenames not confirmed] | отчёт не пришёл, пришёл не туда, пришёл пустой или с error text | critical | immediate |
| SALES-SMOKE-02 | Report contract integrity | структура отчёта сохраняет ожидаемые обязательные блоки и порядок delivery | live report text; contract references in `agents/sales_agent/report_contract.py`; health helper `cloudbot/devops/sales_dispatch_health.py` | missing blocks, broken order, follow-up sequence lost, obvious contract drift | critical | immediate |
| SALES-SMOKE-03 | Telegram delivery | delivery uses expected bot identity and target chat for Sales/Lev | live Telegram delivery; token-file contract in `agents/lev_petrovich/telegram_route.py`; bridge logic in `scripts/run_sales_copilot.py` | wrong bot, wrong chat, silent fallback to shared token/chat, message split badly or dropped | critical | immediate |
| SALES-SMOKE-04 | Bitrix data pull sanity | отчёт выглядит основанным на реальном свежем Bitrix snapshot, а не на empty/mock/error state | live report content; Bitrix check output path references; bridge uses `/opt/openclaw/state/bitrix_app` | zero/empty pipeline without explanation, explicit Bitrix auth/state error, stale data symptoms | critical | immediate |
| SALES-SMOKE-05 | Follow-up generation | после daily sales отчёта follow-up блоки/сообщения продолжают генерироваться по контракту | Telegram sequence; `sales_followup_report_types` references in `agents/sales_agent/report_contract.py` and `scripts/run_sales_copilot.py` | нет follow-up при ожидаемом сценарии, duplicate follow-up, wrong order | high | same day |
| SALES-SMOKE-06 | Postponed deals block | блок отложенных/зависших сделок присутствует и выглядит содержательно, если такие сделки есть | live sales report; formatting references in `agents/sales_agent/sales_formatter.py` | block исчез, явно пуст при known live backlog, malformed output | high | same day |
| SALES-SMOKE-07 | Overdue tasks block | блок просроченных задач присутствует и не выглядит вырожденным | live sales report; task/overdue logic references in `agents/sales_agent/sales_agent.py` and pipeline/risk layers | overdue tasks missing, count implausible, block replaced by raw error | high | same day |
| SALES-SMOKE-08 | Weekly review readiness | weekly pathway remains intact even если weekly cron сейчас не исполняется в момент smoke | `/etc/cron.d/cloudbot-sales-reports`; workflow references `infra/orchestrator/workflows/sales_weekly_review.sh`; report contract docs | weekly route unavailable, wrong target chat logic, weekly output contract broken | medium | observe |
| SALES-SMOKE-09 | Logs freshness | sales runtime logs/reports обновляются по расписанию и не висят на старом timestamp | `/home/ops/cloudbot-sales-agent/reports/` [exact filenames not confirmed]; cron timestamps | stale logs, file missing, no fresh artifact after expected run | high | same day |
| SALES-SMOKE-10 | Report formatting sanity | HTML/Telegram formatting remains readable and complete | live Telegram report; `agents/sales_agent/sales_formatter.py`; formatter metadata via `cloudbot/devops/sales_dispatch_health.py` | broken markup, duplicated sections, unreadable chunking, missing headings | medium | observe |
| SALES-SMOKE-11 | Compatibility with `sales_agent` layer | Lev runtime still resolves through current `sales_agent` compatibility layer without import/runtime breakage | practical entrypoints: `python3 -m agents.lev_petrovich`, bridge script, tests/docs references | import errors, broken compatibility path, report logic missing because `sales_agent` treated as gone too early | critical | immediate |
| SALES-SMOKE-12 | Runtime bridge awareness for `scripts/run_sales_copilot.py` | bridge still uses remote env/state/token-file awareness correctly and does not desync from live Sales runtime | bridge references in `scripts/run_sales_copilot.py`, `cloudbot/workflows/sales_brief.py`, `cloudbot/workflows/bitrix_check.py` | bridge points to stale runtime assumptions, token-file mismatch, state sync failure, wrong report type path | high | same day |

# 3. Deleted files disposition

Ниже только decision support. Ничего не восстанавливается и не архивируется этим пакетом.

## 3.1 Critical orchestrator workflows

| path | likely historical purpose | still needed | if deleted silently, what can break | recommended action | blocker for Wave 2 |
|---|---|---|---|---|---|
| `infra/orchestrator/workflows/deploy.sh` | generic deploy entrypoint for orchestrator layer | unclear | если это всё ещё documented fallback entrypoint, можно потерять понятный deploy path и rollback expectations | investigate first | yes |
| `infra/orchestrator/workflows/rollback.sh` | generic rollback entrypoint | unclear | потеря понятного rollback path; owner не сможет быстро понять, как откатывать structural-only changes in future | investigate first | yes |
| `infra/orchestrator/workflows/verify.sh` | generic verification entrypoint | unclear | потеря единой verify command surface; smoke/verify expectations становятся размытыми | investigate first | yes |
| `infra/orchestrator/workflows/audit.sh` | generic audit entrypoint | unclear | потеря общего audit workflow; менее критично, чем deploy/rollback/verify, но operational traceability падает | investigate first | yes |

Вывод по группе: **без подтверждения нельзя считать эти удаления безопасными**. Для условного допуска к Wave 2 достаточно зафиксировать, что группа excluded и требует отдельного disposition; физически восстанавливать файлы сейчас не требуется.

## 3.2 control_plane_snapshots

| path | likely historical purpose | still needed | if deleted silently, what can break | recommended action | blocker for Wave 2 |
|---|---|---|---|---|---|
| `control_plane_snapshots/architect_workspace_20260325_MSK/*` | historical audit snapshot of architect/control-plane workspace | unclear | потеря historical evidence и pre-migration context; broken audit chain | archive | no |

Уточнение: safe outcome для Wave 2 gate — трактовать это как archive/evidence zone, а не live dependency. Exact archival policy not confirmed.

## 3.3 HAPP/VPN legacy layer

| path | likely historical purpose | still needed | if deleted silently, what can break | recommended action | blocker for Wave 2 |
|---|---|---|---|---|---|
| `checks/vpn_smoke_happ.sh` | old HAPP/VPN smoke check | not confirmed | если HAPP/VPN ещё нужен, потеряется smoke path | officially obsolete only after explicit retirement; otherwise investigate first | no |
| `checks/vpn_verify.sh` | old HAPP/VPN verify | not confirmed | аналогично: потеря verify path для legacy VPN contour | officially obsolete only after explicit retirement; otherwise investigate first | no |
| `infra/happ-vpn.env.example` | HAPP/VPN env example | not confirmed | потеря legacy env reference | archive or officially obsolete | no |
| `infra/templates/sing-box.service` | service template for VPN-related layer | not confirmed | потеря service template reference | archive or investigate first | no |
| `ops/architecture_happ_vpn.md` | architecture doc for HAPP/VPN | not confirmed | потеря historical architecture notes | archive | no |
| `ops/runbook_happ_vpn.md` | runbook for HAPP/VPN | not confirmed | потеря recovery notes if contour unexpectedly still needed | archive or investigate first | no |
| `services/vpn/sing-box.server-template.json` | server template for VPN | not confirmed | потеря config template | archive or officially obsolete | no |

Вывод по группе: HAPP/VPN already excluded from Wave 2. Because it is out of scope, unresolved status is **not a remaining Wave 2 blocker** as long as it stays excluded.

## 3.4 Subscription legacy layer

| path | likely historical purpose | still needed | if deleted silently, what can break | recommended action | blocker for Wave 2 |
|---|---|---|---|---|---|
| `services/subscription/README.md` | docs for old subscription service | not confirmed | потеря context about service role | investigate first | no |
| `services/subscription/deploy_subscription.sh` | deploy helper for old subscription service | not confirmed | если service still exists elsewhere, its deploy path becomes undocumented | investigate first | no |

Вывод: separate legacy cleanup track; not a Wave 2 blocker while excluded.

## 3.5 Old health script

| path | likely historical purpose | still needed | if deleted silently, what can break | recommended action | blocker for Wave 2 |
|---|---|---|---|---|---|
| `checks/morning_health_report.sh` | old morning health check/report helper | unclear | если кто-то still references it operationally, morning status expectation may break silently | investigate first | no |

## 3.6 Net disposition summary

- `deploy.sh`, `rollback.sh`, `verify.sh`, `audit.sh`: **remain blocker group** until explicitly dispositioned, but they are already excluded from Wave 2 execution scope.
- `control_plane_snapshots/*`: safe to treat as **archive/evidence**, not live runtime dependency.
- HAPP/VPN group: safe to treat as **legacy excluded**; exact retirement status not confirmed.
- `services/subscription/*`: **legacy excluded**, exact retirement not confirmed.
- `checks/morning_health_report.sh`: **unclear old health helper**, but not a structural blocker if excluded.

# 4. sales_agent compatibility decision

## 4.1 Evidence

Confirmed practical references:

- `agents/lev_petrovich/agent.py:5` imports from `agents.sales_agent.sales_agent`
- `agents/sales_agent/sales_agent.py:25` imports `agents.lev_petrovich.telegram_route`
- `scripts/run_sales_copilot.py:25` imports `agents.sales_agent.report_contract`
- `scripts/run_sales_copilot.py:210` runs `python -m agents.lev_petrovich`
- `scripts/run_sales_copilot.py:252` imports `agents.lev_petrovich.agent.build_sales_report_from_env`
- `cloudbot/devops/sales_dispatch_health.py:14-16` imports `agents.sales_agent.report_contract`, `agents.sales_agent.sales_formatter`, and `agents.lev_petrovich.telegram_route`
- `tests/test_lev_petrovich_runtime.py` imports multiple symbols from both `agents.lev_petrovich` and `agents.sales_agent`
- `tests/test_sales_dispatch_contract.py` imports `agents.sales_agent.report_contract`
- docs explicitly state compatibility status:
  - `docs/architecture/runtime_map.md:62` says `python3 -m agents.sales_agent.sales_agent ...` only as compatibility-path until migration complete
  - `docs/roles/lev_petrovich/README.md:77` says `agents/sales_agent` remains compatibility name until migration complete
  - `docs/roles/lev_petrovich/context.md:156` says legacy name `agents/sales_agent` preserved only as compatibility path on transition period

## 4.2 Decision output

| item | answer |
|---|---|
| current practical role | `agents/sales_agent` is still an active runtime and test dependency, not a dead archive |
| safest current classification | temporary compatibility layer with live business logic still behind it |
| recommended owner decision | keep as compatibility layer now; begin retirement later |
| what breaks if treated as legacy right now | `agents.lev_petrovich` import chain breaks; `scripts/run_sales_copilot.py` contract path breaks; `cloudbot/devops/sales_dispatch_health.py` loses contract/formatter dependencies; tests lose current import surface; docs/runtime assumptions become false |
| what breaks if left as compatibility layer for now | continued dual naming, import ambiguity, slower cleanup; but runtime remains understandable and reversible |
| what must happen before retirement | 1) move practical runtime entry to a single approved Lev module, 2) replace imports in tests/bridge/health tooling, 3) freeze report contract in new canonical path, 4) document replacement command surface, 5) re-run smoke/validation checklist after owner-approved migration |
| blocker for Wave 2 | no, if owner adopts the compatibility-layer decision and keeps `agents/sales_agent` explicitly out of retirement during Wave 2 |

## 4.3 Plain recommendation

The safe decision today is:

- **A)** `agents/sales_agent` is not legacy to retire right now.
- Treat it as a **temporary compatibility layer**.
- Retirement can begin only later, after a dedicated follow-up track, not inside Wave 2.

This closes the compatibility blocker for conditional admission because the current rule becomes explicit: **Wave 2 must preserve the compatibility assumption and must not attempt retirement.**

# 5. Final gate blockers status

After this closure package, Wave 2 becomes: **conditionally ready**.

Why:

1. Larisa smoke checklist is now defined as owner-facing production checklist.
2. Lev/Sales smoke checklist is now defined as owner-facing production checklist.
3. Deleted files disposition is documented well enough to separate:
   - true Wave 2 blocker group: generic orchestrator `deploy.sh` / `rollback.sh` / `verify.sh` / `audit.sh`
   - archive/evidence group: `control_plane_snapshots/*`
   - excluded legacy groups: HAPP/VPN, subscription, old health helper
4. `agents/sales_agent` now has explicit recommended classification:
   - keep as compatibility layer now
   - retire later in a separate track

Why this is only conditional, not full ready:

- no architectural moves are approved by this file
- no runtime changes are approved by this file
- deleted orchestrator workflow group still has `investigate first`
- smoke checklists are defined, but not executed
- owner still must adopt this closure package as the governing gate document

Conservative gate interpretation:

- if owner accepts this document as the authoritative closure of the last four blockers, Wave 2 may be treated as **conditionally ready**
- if owner does not accept the deleted-files or compatibility recommendation, status falls back to **still blocked**

# 6. What to send back to ChatGPT

```text
Final gate closure package prepared.

File:
/Users/pro2kuror/Desktop/architect/opencloud_final_gate_closure.md

Result:
conditionally ready

Meaning:
- Larisa smoke checklist defined
- Lev/Sales smoke checklist defined
- deleted files disposition documented
- sales_agent classified as temporary compatibility layer

Important caveat:
Wave 2 is only conditionally ready if owner accepts this closure package.

Key rule:
agents/sales_agent must stay compatibility layer for now and must not be retired inside Wave 2.
```
