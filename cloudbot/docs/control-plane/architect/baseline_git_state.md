# Baseline git state

Дата фиксации: 2026-04-23 11:34:58 МСК  
Режим: read-only git inventory. Ничего не staged, committed, reset, checkout или изменено.

## 1. Engineer repo

Path:

```text
/Users/pro2kuror/Desktop/OpenClo/projects/engineer
```

Branch:

```text
codex/feature/self-healing
```

HEAD:

```text
dc19495e340a5899ca3451f4f492df65a63789da
```

Remote:

```text
origin  https://github.com/Johnnie13Walker/codex-base.git (fetch)
origin  https://github.com/Johnnie13Walker/codex-base.git (push)
```

Status summary:

```text
## codex/feature/self-healing...origin/codex/feature/self-healing [ahead 3]
modified/tracked changes: 106
deleted paths: 36
untracked paths: 46
```

High-risk dirty areas observed:

```text
.env.integrations.example
.gitignore
AGENTS.md
Makefile
agents/larisa_ivanovna/*
agents/sales_agent/*
cloudbot/bot/telegram/commands.py
cloudbot/orchestrator/*
cloudbot/providers/*
cloudbot/skills/*
cloudbot/workflows/*
configs/*
docs/*
infra/orchestrator/*
ops/*
scripts/*
tests/*
```

Important untracked areas observed:

```text
.github/
agents/finansist/
agents/larisa_ivanovna/commands/get_content_post.py
agents/larisa_ivanovna/commands/get_content_topics.py
agents/larisa_ivanovna/commands/get_web_search.py
agents/larisa_ivanovna/workflows/content_topics.py
agents/larisa_ivanovna/workflows/search.py
agents/sales_agent/report_contract.py
checks/finansist_google_smoke.mjs
checks/sales_morning_dispatch_smoke.py
cloudbot/orchestrator/search_state.py
cloudbot/workflows/finance_*.py
cloudbot/workflows/larisa_content_*.py
cloudbot/workflows/larisa_search.py
infra/orchestrator/workflows/larisa_content_topics.sh
infra/remote-ops.env.example
ios/
scripts/finansist_*.mjs
tests/test_finansist_agent.py
tests/test_larisa_search.py
tests/test_sales_dispatch_contract.py
tests/test_search_provider.py
```

Important deleted areas observed:

```text
checks/morning_health_report.sh
checks/vpn_smoke_happ.sh
checks/vpn_verify.sh
control_plane_snapshots/architect_workspace_20260325_MSK/*
infra/happ-vpn.env.example
infra/orchestrator/workflows/audit.sh
infra/orchestrator/workflows/deploy.sh
infra/orchestrator/workflows/rollback.sh
infra/orchestrator/workflows/verify.sh
infra/templates/sing-box.service
ops/architecture_happ_vpn.md
ops/runbook_happ_vpn.md
services/subscription/*
services/vpn/sing-box.server-template.json
```

Baseline conclusion:

- Engineer repo is dirty and ahead of remote by 3 commits.
- Wave 2 must not start until this dirty state is explicitly frozen and reviewed.
- No cleanup, reset, commit, checkout, stash, or branch operation was performed.

## 2. Architect repo

Path:

```text
/Users/pro2kuror/Desktop/architect
```

Branch:

```text
codex/docs-bootstrap
```

HEAD:

```text
bd7e1b63a457807342283bdd7c80e0164407a399
```

Remote:

```text
not configured / no remote output observed
```

Status summary:

```text
## codex/docs-bootstrap
modified/tracked changes: 10
deleted paths: 0
untracked paths: 63
```

Tracked modified areas observed:

```text
.gitignore
AGENTS.md
docs/PLAN.md
docs/STATUS.md
docs/architecture/test_matrix.md
docs/checklists/health-check.md
docs/checklists/serena-session.md
docs/prompts/daily-health-check.md
docs/workflows/codex-github.md
scripts/README.md
```

Important untracked areas observed:

```text
opencloud_audit_report.md
opencloud_target_reorg_plan.md
docs/architecture/*.md
docs/architecture/*.docx
docs/architecture/*.xlsx
docs/marketing_dashboard_*.md
docs/yandex_direct_*.md
output/
scripts/*dashboard*
scripts/*bitrix*
seo_dashboard_*.pdf
seo_dashboard_*.png
tools/
```

Baseline conclusion:

- Architect repo is dirty and has many generated/reporting artifacts.
- It remains the docs/control-plane source of truth, but needs classification before migration.
- No commit or cleanup was performed.

