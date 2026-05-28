# Agents import audit — 2026-05-02 МСК

## Purpose

Record remaining `agents/*` references after the `apps/*` cutover.

This audit does not change runtime, env, cron, systemd, Docker or Telegram routing.

## Runtime/code references

| Path | Reference | Classification | Action |
| --- | --- | --- | --- |
| `scripts/run_sales_copilot.py` | `python -m agents.lev_petrovich` | compatibility CLI bridge | keep until wrapper cutover is separately approved |
| `infra/orchestrator/workflows/larisa_daily_brief.sh` | `python3 -m agents.larisa_ivanovna` | server workflow compatibility CLI | keep |
| `infra/orchestrator/workflows/larisa_midday_replan.sh` | `python3 -m agents.larisa_ivanovna` | server workflow compatibility CLI | keep |
| `infra/orchestrator/workflows/larisa_evening_review.sh` | `python3 -m agents.larisa_ivanovna` | server workflow compatibility CLI | keep |
| `infra/orchestrator/workflows/larisa_content_topics.sh` | `python3 -m agents.larisa_ivanovna` | server workflow compatibility CLI | keep |
| `infra/orchestrator/workflows/larisa_send_note.sh` | `agents.larisa_ivanovna.providers.telegram_provider` | compatibility import | candidate for later canonical import rewrite |
| `infra/orchestrator/workflows/sales_morning_report.sh` | `python -m agents.lev_petrovich` | server workflow compatibility CLI | keep |
| `infra/orchestrator/workflows/sales_followup.sh` | `python3 -m agents.lev_petrovich` | server workflow compatibility CLI | keep |
| `infra/orchestrator/workflows/sales_weekly_review.sh` | `python3 -m agents.lev_petrovich` | server workflow compatibility CLI | keep |
| `infra/orchestrator/workflows/sales_agent_deploy.sh` | generated wrapper uses `python3 -m agents.lev_petrovich` | deployed compatibility CLI | keep |
| `shared/contracts/sales_report_format_contract.py` | formatter module string `agents.sales_agent.sales_formatter` | public metadata compatibility | keep until formatter metadata version change |
| `apps/lev_petrovich/legacy_sales_agent/sales_agent.py` | default workflow name `agents.lev_petrovich` | event/log compatibility label | keep until monitoring contract changes |
| `tests/integration/test_app_compatibility_contract.py` | imports `agents.*` | intentional compatibility test | keep |

## Documentation references

Current docs still mention `agents/*` in two different ways:

- historical reports and older wave documents: keep unchanged;
- active docs/runbooks: update to say `apps/*` is canonical and `agents/*` is compatibility.

Active docs to update next:

- `README.md`
- `ARCHITECTURE.md`
- `docs/api_integrations.md`
- `docs/architecture/runtime_map.md`
- `docs/architecture/system_map.md`
- `docs/migration/sales_lev/sales_lev_runtime_bridge_map.md`
- `docs/migration/sales_lev/sales_agent_retirement_assessment.md`
- `docs/migration/sales_lev/sales_lev_report_contract_map.md`

## Verdict

There are no remaining canonical Python imports from production app code into `agents.sales_agent`.

Remaining `agents/*` use is intentional compatibility surface:

- server workflow CLI entrypoints;
- public formatter metadata;
- monitoring/log labels;
- compatibility tests;
- historical docs.

Do not delete `agents/sales_agent`.
