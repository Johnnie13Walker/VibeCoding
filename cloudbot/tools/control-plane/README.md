# Control-plane tools

This directory contains non-runtime tools consolidated from the legacy control-plane workspace:

`/Users/pro2kuror/Desktop/architect`

## Current contents

- `architect-scripts/scripts/*`
- `architect-scripts/tools/*`

These files were copied for preservation and review. They are not part of production Cloudbot runtime packaging and must not be used as deploy entrypoints without a separate review.

## Rules

- Do not store secrets here.
- Keep env values outside git.
- Treat scripts as quarantined until each one has an owner and a documented use case.
- Do not wire these scripts into cron/systemd/runtime during folder consolidation.

## Next review

Classify each script as one of:

- keep and port into a maintained workflow;
- keep as one-off audit tooling;
- archive;
- delete from the legacy workspace after approval.
