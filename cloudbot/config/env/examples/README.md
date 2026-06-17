# Env Examples Target Boundary

This directory is a target skeleton for future env examples only.

It is not an active runtime path.

Do not store real env files here.
Do not store secrets here.
Do not store token values here.
Do not use this directory as live config.

Live env remains no-touch.

Future example files may be moved here only by separate owner approval.

Allowed later by approval:

- redacted `.env.example` files
- documented placeholder variables
- schema-linked examples

Not allowed:

- `.env`
- `.env.local`
- `.env.production`
- token files
- private keys
- runtime-generated config
- cron/systemd/docker config

Wave 5 does not allow changing imports, runtime behavior, env loading, cron, systemd, docker or deploy scripts.
