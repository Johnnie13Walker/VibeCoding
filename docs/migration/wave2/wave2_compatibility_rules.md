# Wave 2 Compatibility Rules

Date: 2026-04-27 MSK.

These rules preserve current behavior while Wave 2 prepares structure. They do not authorize code moves or import rewrites.

## 1. `agents/sales_agent`

`agents/sales_agent` remains a temporary compatibility layer.

Rules:

- Do not delete `agents/sales_agent`.
- Do not retire `agents/sales_agent`.
- Do not move `agents/sales_agent` without separate owner approval.
- Do not rewrite Lev/Sales runtime imports in Wave 2.
- Lev/Sales must remain compatible with the existing `agents/sales_agent` layer.
- Any future retirement must be a separate track with tests, smoke checklist, report-contract validation, and rollback expectations.

Reason:

- `agents/lev_petrovich` imports from `agents.sales_agent`.
- `scripts/run_sales_copilot.py` depends on sales report contract paths.
- runtime/health tests and report formatting still reference `agents.sales_agent`.

## 2. Cloudbot Wrapper

`/Users/pro2kuror/Desktop/Cloudbot` is wrapper/symlink only.

Rules:

- It is not source of truth.
- Do not reorganize through the wrapper path.
- Do not treat wrapper layout as canonical.
- Any path reference to the wrapper must be documented as compatibility-only.

## 3. Source of Truth

Canonical code source:

```text
/Users/pro2kuror/Desktop/OpenClo/projects/engineer
```

Docs/control-plane:

```text
/Users/pro2kuror/Desktop/architect
```

Rules:

- Code/source decisions are made against the canonical engineer repo.
- Architecture decision support can live in docs/control-plane.
- Wave 2 docs in the engineer repo are structural preparation artifacts, not runtime config.

## 4. Runtime

No-touch runtime paths:

```text
/opt/cloudbot-runtime/larisa/current
/opt/cloudbot-runtime/current
/opt/openclaw
/etc/openclaw
```

Rules:

- Do not change runtime pointers.
- Do not change files under `/opt`, `/etc`, `/root`, or `/home/ops`.
- Do not update live server wrappers.
- Do not mutate server-only integrations.

## 5. Env, Token, Chat Routing

Rules:

- No shared `TELEGRAM_BOT_TOKEN` fallback changes in Wave 2.
- No env mutation.
- No token routing changes.
- No chat routing changes.
- No bot identity changes.
- Any future env separation must be a separate wave with owner approval and smoke checks for Larisa and Lev/Sales.
