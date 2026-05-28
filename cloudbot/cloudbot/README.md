# cloudbot

## Current status

This directory is the current active shared-core path.

It has not been migrated to `shared/`.

This README is a documentation marker only.

---

## Active paths

Current active shared-core paths include:

- `cloudbot/orchestrator`
- `cloudbot/providers`
- `cloudbot/skills`
- `cloudbot/workflows`
- `cloudbot/bot`
- `cloudbot/devops`

These paths remain active until a separate owner-approved migration changes them.

---

## Mandatory rules

Do NOT:

- move shared-core code
- rewrite imports silently
- change command routing
- change provider behavior
- change skill behavior
- change workflow behavior
- use this marker as approval for shared-core extraction

Any shared-core extraction requires a separate approved track with import compatibility, tests, smoke validation, and rollback expectations.

---

## Working principle

Behavior stability first.
Shared extraction later.
