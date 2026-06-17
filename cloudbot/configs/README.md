# configs

## Current status

This directory is the current config examples and schedule contract area.

It is not a live env directory.

It has not been migrated to `config/`.

This README is a documentation marker only.

---

## Mandatory rules

Do NOT:

- store secrets here
- create real env files here
- change live env
- change live cron
- rewrite schedule behavior
- treat examples as deployed config
- use this marker as approval for config migration

Live env and live cron remain no-touch during current migration waves.

---

## Future migration rule

Any future config migration requires separate owner approval.

That track must define:

- env example policy
- env schema policy
- schedule contract policy
- secret handling rules
- validation and rollback expectations

No such migration is approved by this README.
