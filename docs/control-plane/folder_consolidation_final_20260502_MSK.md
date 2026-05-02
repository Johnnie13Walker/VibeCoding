# Folder consolidation final report — 2026-05-02 МСК

## Verdict

Folder consolidation is complete for source-of-truth materials.

Canonical locations:

| Purpose | Path |
| --- | --- |
| Code, tests, runtime migration docs | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` |
| Control-plane docs and migrated architect materials | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane` |
| Control-plane scripts/tools quarantine | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/tools/control-plane` |
| Navigation wrapper | `/Users/pro2kuror/Desktop/Cloudbot` |
| Legacy stub outside wrapper | `/Users/pro2kuror/Desktop/architect` |

## Completed

- Markdown control-plane docs copied from `architect` into `engineer/docs/control-plane`.
- Control-plane scripts/tools copied into `engineer/tools/control-plane`.
- Report artifacts copied into `engineer/docs/control-plane/architect/artifacts`.
- Obsolete `acoola-landing` task files removed.
- Legacy `architect` tracked source files removed and replaced with a pointer `README.md`.
- Ignored/generated leftovers in `architect` removed.
- Wrapper `Cloudbot/README.md` updated to point users at `engineer/docs/control-plane`.
- Legacy `Cloudbot/architect` symlink removed from the wrapper.

## Current legacy architect state

`/Users/pro2kuror/Desktop/architect` intentionally contains only:

- `.git/`
- `.gitignore`
- `README.md`

It is no longer source of truth.

## Runtime safety

This folder cleanup did not change:

- `/opt/cloudbot-runtime`
- `/opt/openclaw`
- env files
- cron
- systemd
- Docker
- Telegram routing
- runtime pointers

## Remaining non-folder migration work

1. Continue runtime cleanup only through explicitly approved, scoped steps.
2. Keep `/opt/openclaw` on a separate server-only audit track.
3. Keep or archive `/Users/pro2kuror/Desktop/architect` as a separate local stub decision, outside the Cloudbot wrapper.
