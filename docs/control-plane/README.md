# Control-plane consolidation

## Status

This directory is the canonical landing zone for Cloudbot/OpenCloud control-plane documentation that previously lived in:

`/Users/pro2kuror/Desktop/architect`

The original `architect` directory was not deleted or modified during the first consolidation pass.

## Current source-of-truth rule

- Code, runtime workflows, tests and migration docs: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- Consolidated control-plane docs: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane`
- Navigation wrapper: `/Users/pro2kuror/Desktop/Cloudbot`
- Legacy docs workspace pending cleanup: `/Users/pro2kuror/Desktop/architect`

## First pass copied

Copied from `architect` into `docs/control-plane/architect`:

- root `AGENTS.md`
- root `README.md`
- root `baseline_*.md`
- root `opencloud_*.md`
- `docs/PLAN.md`
- `docs/STATUS.md`
- `docs/architecture/*.md`
- `docs/checklists/*.md`
- `docs/prompts/*.md`
- `docs/workflows/*.md`

Only text Markdown documents were copied.

## Not copied yet

These remain in `/Users/pro2kuror/Desktop/architect` until separate classification:

- `.xlsx`
- `.docx`
- `.png`
- `.pdf`
- `.html`
- `.json`
- `.tsv`
- `.zip`
- `output/`
- `outputs/`
- `tmp/`
- `.playwright-mcp/`
- `.publish-belberry/`
- local app/project folders such as `acoola-landing/`
- scripts under `architect/scripts/`

Reason: these are generated artifacts, binary reports, local tool output, or separate project assets. They should not be bulk-imported into the engineer repo without owner classification.

## Next cleanup steps

1. Review `docs/control-plane/architect` and decide which documents should be promoted to cleaner paths such as:
   - `docs/control-plane/architecture`
   - `docs/control-plane/checklists`
   - `docs/control-plane/prompts`
   - `docs/control-plane/opencloud`
2. Add ignore rules for generated artifacts if they stay in `architect`.
3. Classify `architect/scripts/` into:
   - keep and port;
   - archive;
   - generated/local only.
4. After review, retire duplicated docs from `architect` or replace them with pointers to this canonical location.

## No-touch boundaries

This consolidation does not change:

- production runtime;
- `/opt/cloudbot-runtime`;
- `/opt/openclaw`;
- env files;
- cron;
- systemd;
- Docker;
- Telegram routing.
