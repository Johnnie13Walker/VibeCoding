# 1. Executive summary

Дата пакета: 2026-04-23, МСК.

Назначение: подготовить решения владельца по dirty-state перед Wave 2. Этот документ не применяет изменений и не предлагает считать реорганизацию уже разрешенной.

Исходная точка:

- repo: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- branch: `codex/feature/self-healing`
- HEAD: `dc19495e340a5899ca3451f4f492df65a63789da`
- diff: `106 files changed, 4801 insertions(+), 3951 deletions(-)`
- status: `70 modified`, `36 deleted`, `46 untracked`
- pre-Wave 2 verdict: `not ready for Wave 2`

Короткий вывод:

- **Нельзя начинать Wave 2**, пока владелец явно не решит, что делать с dirty-state.
- Сам dirty-state нельзя принять одной кнопкой: он смешивает боевых агентов, shared-core, deploy/runtime-скрипты, docs, tests, legacy cleanup и новые unrelated contours.
- Для Wave 2 нужно отделить baseline acceptance от execution: сначала решаем судьбу изменений, потом только проектируем перенос файлов.
- Рекомендуемый owner stance: принять как baseline только read-only факты и docs-контекст, production/runtime изменения отправить на manual review, finance/iOS вынести в отдельные треки, legacy deletions не принимать молча.

# 2. Decision buckets

## Bucket A — accept into baseline now

Смысл: можно принять как **описание текущего состояния**, но не как разрешение на перенос или deploy.

| files / zones | why here | risk | owner decision needed |
|---|---|---|---|
| `opencloud_pre_wave2_freeze_audit.md` in `/Users/pro2kuror/Desktop/architect` | это read-only freeze-аудит, не runtime | низкий | принять как текущий audit baseline |
| `opencloud_wave0_wave1_baseline.md` in `/Users/pro2kuror/Desktop/architect` | Wave 0/1 факты уже зафиксированы | низкий | принять как baseline reference |
| `opencloud_target_reorg_plan.md` in `/Users/pro2kuror/Desktop/architect` | approved target concept, не execution | низкий | оставить как проект, не применять автоматически |
| `docs/architecture/system_map.md`, `docs/architecture/runtime_map.md`, `docs/architecture/schedule_contract.md` | документация содержит важные карты структуры и runtime | средний: есть старые absolute paths и противоречия | принять как evidence, но не как финальный контракт без review |
| `docs/sales_copilot.md` | документация sales/Lev runtime behavior | средний: зависит от production changes | принять как reference only |

Рекомендация: **Accept into baseline as evidence only**.

## Bucket B — accept later but exclude from Wave 2

Смысл: изменения могут быть полезными, но не должны смешиваться с apps/shared/config реорганизацией.

| files / zones | why here | risk | owner decision needed |
|---|---|---|---|
| `agents/larisa_ivanovna/*` content/search additions | похоже на расширение функционала Ларисы | высокий: боевой Telegram-контур | принять отдельной feature-инициативой после review |
| `cloudbot/workflows/larisa_content_post.py`, `larisa_content_topics.py`, `larisa_search.py` | workflow additions для Ларисы | высокий: shared runtime routing | exclude from Wave 2 until accepted |
| `cloudbot/orchestrator/search_state.py`, `cloudbot/skills/web_search.py`, `cloudbot/providers/search_provider.py` | shared search feature | высокий: shared-core для нескольких агентов | отдельный search feature review |
| `agents/sales_agent/report_contract.py`, `checks/sales_morning_dispatch_smoke.py`, `tests/test_sales_dispatch_contract.py` | sales contract hardening | средний/высокий: может быть полезно, но меняет runtime contract | принять отдельно от layout migration |
| `.github/workflows/sales-contract-checks.yml` | CI для sales contract | средний: CI может начать блокировать unrelated work | отдельное решение по CI |

Рекомендация: **Accept later, explicitly exclude from Wave 2 scope**.

## Bucket C — manual review required before any acceptance

Смысл: нельзя принимать как baseline без просмотра намерения, влияния и тестов.

| files / zones | why here | risk | owner decision needed |
|---|---|---|---|
| `agents/larisa_ivanovna/agent.py`, `config.py`, providers, workflows, formatters | production-critical Larisa logic | высокий | review with Larisa smoke plan |
| `agents/sales_agent/pipeline_analyzer.py`, `risk_detector.py`, `sales_agent.py`, `sales_formatter.py` | production-critical Lev/Sales reports | высокий | review with sales report contract |
| `scripts/run_sales_copilot.py` | bridge to remote env/state and Telegram delivery | высокий | review before any acceptance |
| `cloudbot/orchestrator/orchestrator.py`, `cloudbot/orchestrator/router.py` | shared routing | высокий | review because it can affect all contours |
| `cloudbot/providers/bitrix/*`, `cloudbot/skills/bitrix_sales_data.py` | Bitrix integration and sales data | высокий | review with Bitrix runtime assumptions |
| `cloudbot/devops/sales_dispatch_health.py`, `cloudbot/workflows/system_health.py` | monitoring/health behavior | средний/высокий | review because alerts can mislead production status |
| `infra/orchestrator/*` modified scripts | deploy/runtime/server operations | критический | review before Wave 2; no execution |
| `configs/*`, `.env.integrations.example` | env/cron contracts and absolute paths | высокий | review before accepting any env contract |
| `tests/test_larisa_agent.py`, `tests/test_lev_petrovich_runtime.py`, Bitrix tests | tests lock runtime/import behavior | средний | review together with code they validate |

Рекомендация: **Manual review required; block Wave 2 until owner disposition is explicit**.

## Bucket D — likely legacy/stale cleanup

Смысл: похоже на удаление старого слоя, но deletion нельзя принимать молча.

| files / zones | why here | risk | owner decision needed |
|---|---|---|---|
| `checks/vpn_smoke_happ.sh`, `checks/vpn_verify.sh`, `infra/happ-vpn.env.example`, `infra/templates/sing-box.service`, `ops/architecture_happ_vpn.md`, `ops/runbook_happ_vpn.md`, `services/vpn/sing-box.server-template.json` | HAPP/VPN выглядит legacy | средний: может быть забытый recovery path | accept deletion only after confirming HAPP/VPN retired |
| `services/subscription/*` | subscription service выглядит отдельным legacy контуром | средний: может быть external service | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/*` | historical snapshot deletion | средний: потеря audit evidence | either restore before Wave 2 or archive decision |
| `infra/orchestrator/workflows/audit.sh`, `deploy.sh`, `rollback.sh`, `verify.sh` | generic operational scripts deleted | высокий: названия критичные | investigate first; do not accept silently |
| `checks/morning_health_report.sh` | old health check script | средний: может быть заменён `daily_ops` | investigate first |

Рекомендация: **Likely cleanup, but not accepted until owner confirms obsolete**.

## Bucket E — unrelated/new contour, treat separately

Смысл: новые контуры не должны входить в Wave 2, пока не классифицированы.

| files / zones | why here | risk | owner decision needed |
|---|---|---|---|
| `agents/finansist/*` | новый агент/финансовый контур | высокий: не часть утвержденной Larisa/Lev reorg | отдельная initiative: finance app |
| `cloudbot/workflows/finance_*.py`, `cashflow_analysis.py`, `pnl_analysis.py`, etc. | finance workflows | высокий: shared router/workflow expansion | separate track |
| `scripts/finansist_*.mjs`, `checks/finansist_google_smoke.mjs`, `tests/test_finansist_agent.py` | finance scripts/checks/tests | средний/высокий | separate finance review |
| `ios/FormaNutrition/*` | отдельное iOS-приложение | высокий: не Cloudbot runtime | classify as external/product repo candidate |
| `infra/remote-ops.env.example` | новый remote ops env contract | средний: infra/env scope | review separately |

Рекомендация: **Treat separately; exclude from Wave 2**.

# 3. Production-critical decision table

| zone | current state | likely purpose | accept now? | include in Wave 2? | why | owner question to answer |
|---|---|---|---|---|---|---|
| `agents/larisa_ivanovna` | modified + untracked | Larisa core, Telegram delivery, calendar/tasks, content/search additions | no; conditionally after review | no | боевой контур, есть env fallback and new workflows | Принимаем ли текущие изменения Ларисы как рабочую функциональную feature, или замораживаем их вне Wave 2? |
| `agents/sales_agent` | modified + untracked `report_contract.py` | compatibility/business logic for Lev/Sales reports | no; conditionally after review | no | compatibility layer связан с `agents/lev_petrovich` | Оставляем ли `sales_agent` compatibility layer текущим source for Lev until migration complete? |
| `agents/lev_petrovich` | not directly dirty, but coupled through imports/tests/scripts | Lev/Sales agent facade and Telegram route | conditionally, as dependency baseline only | no | изменения вокруг него могут менять behavior без прямой правки файлов | Считать ли Lev source of truth связанным с `sales_agent` до отдельной migration? |
| `cloudbot/orchestrator` | modified + untracked `search_state.py` | command routing, shared state | no | no | shared-core affects Larisa, Lev, finance/search | Принимаем ли search/router changes как отдельную feature before reorg? |
| `cloudbot/providers` | modified | Bitrix/search/shared providers | no | no | provider changes affect multiple agents and server state paths | Какие provider changes являются required baseline, а какие feature work? |
| `cloudbot/skills` | modified | Bitrix sales data and web search skills | no | no | shared tools can break both agents | Принимать ли web_search и Bitrix sales skill changes до Wave 2? |
| `cloudbot/workflows` | modified + many untracked | Larisa runtime, system health, finance and search workflows | no | no | mixes production runtime and new contours | Какие workflows относятся к current production, а какие к new initiatives? |
| `infra/orchestrator` | modified + deleted + untracked | deploy, verify, repair, runtime scripts | no | no | operational scripts; absolute server paths | Какие infra changes approved, and are deleted deploy/rollback/verify obsolete? |
| `configs` | modified | env examples, schedule contracts, cron examples | no | no | contains old local path and env contracts | Какой canonical local path должен быть в config docs: OpenClo/projects/engineer or Cloudbot/engineer compatibility? |
| `scripts/run_sales_copilot.py` | modified | sales runtime bridge, remote env/state reader, Telegram delivery | no | no | production bridge to server paths and token-file path | Принимаем ли текущий sales bridge as baseline after review? |
| `tests` | modified + untracked | lock current behavior/imports/contracts | conditionally after code review | no | tests can be useful, but will break if layout changes without compatibility | Какие tests must pass before Wave 2 entry? |
| `docs` | modified | architecture/runbook/current map | yes as evidence only | docs can be referenced, not moved in Wave 2 without separate docs wave | documentation has stale and current paths | Принимаем ли docs as evidence while marking stale path sections for later cleanup? |

# 4. Deleted files decision pack

| path | likely role | likely obsolete or not | danger if accepted silently | recommended decision |
|---|---|---|---|---|
| `checks/morning_health_report.sh` | old morning health check | maybe obsolete | daily health reporting could lose fallback script | investigate first |
| `checks/vpn_smoke_happ.sh` | HAPP/VPN smoke check | likely obsolete | hidden VPN dependency could be lost | investigate first |
| `checks/vpn_verify.sh` | HAPP/VPN verify | likely obsolete | same; could remove recovery diagnostics | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/AGENTS.md` | historical control-plane snapshot | archive/evidence | loss of historical instructions evidence | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/README.md` | historical snapshot docs | archive/evidence | loss of historical evidence | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/devops/README.md` | historical devops docs | archive/evidence | loss of audit trail | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/.DS_Store` | generated macOS artifact | obsolete | low | accept deletion |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/PLAN.md` | historical plan snapshot | archive/evidence | loss of migration context | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/STATUS.md` | historical status snapshot | archive/evidence | loss of migration context | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/architecture/deploy_release_contract.md` | historical deploy contract | archive/evidence | loss of deployment reference | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/architecture/runtime_dependencies.md` | historical runtime deps | archive/evidence | hidden dependency may be forgotten | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/architecture/test_matrix.md` | historical test matrix | archive/evidence | loss of test reference | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/checklists/health-check.md` | historical checklist | archive/evidence | loss of operating checklist | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/checklists/post-change.md` | historical checklist | archive/evidence | loss of verification checklist | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/prompts/daily-health-check.md` | historical prompt | archive/evidence | loss of daily ops instruction | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/prompts/feature-branch-task.md` | historical prompt | archive/evidence | loss of workflow instruction | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/prompts/nightly-codex.md` | historical prompt | archive/evidence | loss of automation prompt | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/docs/workflows/codex-github.md` | historical workflow doc | archive/evidence | loss of GitHub workflow context | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/orchestrator/README.md` | historical module doc | archive/evidence | low/medium | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/providers/README.md` | historical module doc | archive/evidence | low/medium | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/scripts/README.md` | historical scripts doc | archive/evidence | low/medium | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/scripts/deploy.sh` | historical deploy script | archive/evidence | could be confused with active deploy reference | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/skills/README.md` | historical module doc | archive/evidence | low/medium | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/telegram/README.md` | historical module doc | archive/evidence | low/medium | investigate first |
| `control_plane_snapshots/architect_workspace_20260325_MSK/workflows/README.md` | historical module doc | archive/evidence | low/medium | investigate first |
| `infra/happ-vpn.env.example` | HAPP/VPN env example | likely obsolete | may remove old access/integration knowledge | investigate first |
| `infra/orchestrator/workflows/audit.sh` | generic audit workflow | unclear | audit command disappears | investigate first |
| `infra/orchestrator/workflows/deploy.sh` | generic deploy workflow | unclear / dangerous | deploy path disappears or changes silently | restore before Wave 2 unless proven obsolete |
| `infra/orchestrator/workflows/rollback.sh` | generic rollback workflow | unclear / dangerous | rollback path disappears | restore before Wave 2 unless proven obsolete |
| `infra/orchestrator/workflows/verify.sh` | generic verify workflow | unclear / dangerous | verification path disappears | restore before Wave 2 unless proven obsolete |
| `infra/templates/sing-box.service` | VPN service template | likely obsolete | old VPN recovery lost | investigate first |
| `ops/architecture_happ_vpn.md` | HAPP/VPN architecture doc | likely obsolete | old architecture context lost | investigate first |
| `ops/runbook_happ_vpn.md` | HAPP/VPN runbook | likely obsolete | recovery instructions lost | investigate first |
| `services/subscription/README.md` | subscription service docs | unclear | unknown service context lost | investigate first |
| `services/subscription/deploy_subscription.sh` | subscription deploy script | unclear | deploy ability lost if service live somewhere | investigate first |
| `services/vpn/sing-box.server-template.json` | VPN server config template | likely obsolete | old VPN config lost | investigate first |

# 5. Untracked files decision pack

## 5.1 Finance contour

| files / zones | in scope for OpenCloud reorg? | include in baseline? | include in Wave 2? | recommended classification |
|---|---|---|---|---|
| `agents/finansist/*` | maybe, not confirmed | no; conditionally after separate review | no | unrelated/new contour, separate finance initiative |
| `cloudbot/workflows/cashflow_analysis.py`, `client_profitability_analysis.py`, `expense_structure_analysis.py`, `finance_anomaly_scan.py`, `finance_runtime.py`, `finance_summary.py`, `payables_analysis.py`, `pnl_analysis.py`, `receivables_analysis.py` | maybe, not confirmed | no | no | finance workflow expansion, separate track |
| `scripts/finansist_*.mjs` | maybe external tooling | no | no | external/finance tooling until classified |
| `checks/finansist_google_smoke.mjs` | maybe finance verification | no | no | finance check, separate track |
| `tests/test_finansist_agent.py` | maybe test for new contour | no | no | finance test, separate track |

## 5.2 iOS contour

| files / zones | in scope for OpenCloud reorg? | include in baseline? | include in Wave 2? | recommended classification |
|---|---|---|---|---|
| `ios/FormaNutrition/*` | no for Cloudbot runtime; maybe separate product | no | no | external/new product contour |

Reason: iOS app includes Swift/Xcode project, architecture docs, shared core package, tests. It is not part of the approved Larisa/Lev/apps/shared/config/infra Cloudbot reorg unless owner explicitly adds it.

## 5.3 Larisa new content/search files

| files / zones | in scope for OpenCloud reorg? | include in baseline? | include in Wave 2? | recommended classification |
|---|---|---|---|---|
| `agents/larisa_ivanovna/commands/get_content_post.py`, `get_content_topics.py`, `get_web_search.py` | yes for Larisa feature, not for structural Wave 2 | conditionally after review | no | Larisa feature track |
| `agents/larisa_ivanovna/formatters/telegram_content_post.py`, `telegram_content_topics.py` | yes for Larisa feature | conditionally after review | no | Larisa feature track |
| `agents/larisa_ivanovna/schemas/content.py`, `timezone.py`, `workflows/content_topics.py`, `workflows/search.py` | yes for Larisa feature | conditionally after review | no | Larisa feature track |
| `cloudbot/workflows/larisa_content_post.py`, `larisa_content_topics.py`, `larisa_search.py` | yes for Larisa runtime bridge | conditionally after review | no | Larisa feature/runtime bridge |
| `infra/orchestrator/workflows/larisa_content_topics.sh` | yes, but runtime script | no until infra review | no | deploy/runtime-sensitive |
| `tests/test_larisa_search.py` | yes as validation | conditionally with feature | no | feature test |

## 5.4 Sales/Lev new files

| files / zones | in scope for OpenCloud reorg? | include in baseline? | include in Wave 2? | recommended classification |
|---|---|---|---|---|
| `agents/sales_agent/report_contract.py` | yes for compatibility layer | conditionally after review | no | sales contract feature |
| `checks/sales_morning_dispatch_smoke.py` | yes as validation | conditionally after review | no | sales verification |
| `tests/test_sales_dispatch_contract.py` | yes as validation | conditionally after review | no | sales contract test |
| `.github/workflows/sales-contract-checks.yml` | maybe CI | conditionally after review | no | CI track |

## 5.5 Shared search/core files

| files / zones | in scope for OpenCloud reorg? | include in baseline? | include in Wave 2? | recommended classification |
|---|---|---|---|---|
| `cloudbot/orchestrator/search_state.py` | yes if search feature accepted | conditionally after review | no | shared-core feature |
| `tests/test_search_provider.py` | yes if search feature accepted | conditionally after review | no | shared-core test |

## 5.6 Infra/env

| files / zones | in scope for OpenCloud reorg? | include in baseline? | include in Wave 2? | recommended classification |
|---|---|---|---|---|
| `infra/remote-ops.env.example` | maybe | no until infra review | no | infra/env contract review |

# 6. Minimal owner decisions

| decision id | question | options | recommended option | consequence |
|---|---|---|---|---|
| OD-01 | Принимаем ли текущий freeze audit как baseline evidence? | accept / reject / regenerate | accept | можно ссылаться на audit package как на стартовую точку, без разрешения на Wave 2 |
| OD-02 | Принимаем ли production changes в `agents/larisa_ivanovna` сейчас? | accept / review first / exclude | review first | Larisa не двигается в Wave 2 до ручного review |
| OD-03 | Принимаем ли production changes в `agents/sales_agent` and Lev/Sales bridge? | accept / review first / exclude | review first | Lev/Sales compatibility remains frozen until review |
| OD-04 | Что делать с `cloudbot/orchestrator`, providers, skills, workflows changes? | accept / review first / exclude | review first | shared-core не участвует в Wave 2 без compatibility plan |
| OD-05 | Что делать с infra/deploy changes under `infra/orchestrator`? | accept / review first / exclude | review first | никакие deploy/runtime scripts не меняются в рамках Wave 2 |
| OD-06 | Что делать с deleted `deploy.sh`, `rollback.sh`, `verify.sh`? | accept deletion / restore before Wave 2 / investigate first | investigate first, likely restore before Wave 2 if unclear | Wave 2 не стартует, если rollback/verify status unclear |
| OD-07 | Что делать с deleted `control_plane_snapshots/*`? | accept deletion / restore / archive decision first | archive decision first | audit evidence не теряется молча |
| OD-08 | Что делать с HAPP/VPN/subscription deletions? | accept deletion / restore / investigate first | investigate first | legacy cleanup не смешивается с structural reorg |
| OD-09 | Включать ли finance contour в OpenCloud reorg? | yes / no / separate track | separate track | `agents/finansist` and finance workflows excluded from Wave 2 |
| OD-10 | Включать ли `ios/FormaNutrition` в OpenCloud reorg? | yes / no / separate product track | separate product track | iOS не участвует в Wave 2 |
| OD-11 | Какой path считать canonical in docs/config examples? | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` / `/Users/pro2kuror/Desktop/Cloudbot/engineer` / both with compatibility note | OpenClo path canonical, Cloudbot path compatibility wrapper | hidden local path coupling becomes explicit |
| OD-12 | Когда разрешён вход в Wave 2? | now / after review / after clean acceptance checklist | after review and explicit exclusion list | Wave 2 starts only with approved included/excluded scope |

# 7. Approval draft

Ниже черновик решения владельца. Его можно утвердить только вручную; этот документ ничего не применяет.

```text
OWNER APPROVAL — Pre-Wave 2 Dirty-State Disposition

Дата: 2026-04-23 МСК
Repo: /Users/pro2kuror/Desktop/OpenClo/projects/engineer
Branch: codex/feature/self-healing
HEAD: dc19495e340a5899ca3451f4f492df65a63789da

1. Что принимаем

Принимаем pre-Wave 2 freeze audit как baseline evidence:
- opencloud_pre_wave2_freeze_audit.md
- opencloud_wave0_wave1_baseline.md
- opencloud_target_reorg_plan.md

Принимаем docs/architecture как evidence/reference only, не как финальный runtime contract.

2. Что не трогаем

До отдельного review не трогаем:
- runtime pointers
- symlink Cloudbot
- env-файлы
- cron
- systemd
- docker
- deploy/rollback/verify scripts
- server-only paths under /opt, /etc, /root, /home/node, /home/ops

3. Что исключаем из Wave 2

Из Wave 2 исключаем:
- all dirty production changes in agents/larisa_ivanovna
- all dirty production changes in agents/sales_agent
- agents/lev_petrovich compatibility behavior
- cloudbot/orchestrator, providers, skills, workflows functional changes
- infra/orchestrator deploy/runtime changes
- configs and env/cron contract changes
- scripts/run_sales_copilot.py
- deleted deploy/rollback/verify files until investigated
- deleted control_plane_snapshots until archive decision

4. Что переносим на отдельный трек

Отдельные треки:
- Larisa content/search feature
- Sales/Lev report contract hardening
- Shared search provider/orchestrator feature
- Finance contour: agents/finansist + finance workflows/scripts/tests
- iOS contour: ios/FormaNutrition
- HAPP/VPN/subscription legacy cleanup
- CI workflow .github/workflows/sales-contract-checks.yml

5. Когда вход в Wave 2 разрешён

Wave 2 разрешён только после:
- owner review of production-critical dirty changes
- explicit decision for deleted tracked files
- explicit exclusion list for unrelated/new contours
- written compatibility decision for Cloudbot symlink wrapper
- written compatibility decision for agents/sales_agent vs agents/lev_petrovich
- accepted test/smoke checklist for Larisa and Lev/Sales

До выполнения этих условий Wave 2 remains NOT APPROVED.
```

# 8. What to send back to ChatGPT

```text
Owner decision package prepared.

File:
/Users/pro2kuror/Desktop/architect/opencloud_owner_decision_package.md

Current verdict:
Wave 2 remains not approved.

Dirty-state disposition:
- Bucket A: accept baseline evidence only.
- Bucket B: accept later, exclude from Wave 2.
- Bucket C: manual review required before acceptance.
- Bucket D: likely legacy/stale cleanup, do not accept silently.
- Bucket E: unrelated/new contours, separate tracks.

Main owner decisions required:
1. Accept freeze audit as evidence baseline.
2. Review Larisa production changes.
3. Review Sales/Lev production changes.
4. Review shared-core changes.
5. Review infra/deploy changes.
6. Decide deleted deploy/rollback/verify files.
7. Decide deleted control_plane_snapshots.
8. Decide HAPP/VPN/subscription legacy cleanup.
9. Exclude finance contour from Wave 2 or make it separate track.
10. Exclude iOS contour from Wave 2 or make it separate product track.
11. Confirm canonical local source path: /Users/pro2kuror/Desktop/OpenClo/projects/engineer.
12. Allow Wave 2 only after explicit included/excluded scope and smoke checklist are approved.
```
