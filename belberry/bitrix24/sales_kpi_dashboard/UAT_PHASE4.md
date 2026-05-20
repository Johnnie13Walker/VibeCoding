# UAT Phase 4 — VPS cron deploy + TG alerts

## Context

- Branch: `feat/sales-kpi-cron-deploy`
- VPS: `cloudbot-ssh-proxy` (`ams-1-vm-76ds`)
- Deploy path: `/opt/cloudbot-runtime/larisa/sales-kpi-dashboard/`
- Wrapper: `/usr/local/bin/cloudbot-larisa-sales-kpi.sh`
- Cron: `/etc/cron.d/cloudbot-larisa-sales-kpi`
- Log: `/var/log/cloudbot-larisa-sales-kpi.log`
- Output Sheet: `1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE`

## Live deploy steps

1. Created `/opt/cloudbot-runtime/larisa/sales-kpi-dashboard/`.
2. Copied modules:
   - `sales_dashboard/`
   - `sales_kpi_dashboard/`
3. Copied service-account JSON to `/opt/openclaw/secrets/finance-director-sheets-903611b799c3.json` and set `chmod 600`.
4. Created venv with VPS `python3` (`Python 3.12.3`).
5. Installed editable packages:
   - `.venv/bin/pip install -e ./sales_dashboard -e ./sales_kpi_dashboard`
6. Installed wrapper and cron:
   - `/usr/local/bin/cloudbot-larisa-sales-kpi.sh`
   - `/etc/cron.d/cloudbot-larisa-sales-kpi`

## Cron schedule

```cron
0 3,7,11,15 * * * root /usr/local/bin/cloudbot-larisa-sales-kpi.sh >> /var/log/cloudbot-larisa-sales-kpi.log 2>&1
```

VPS `/etc/cron.d` runs in UTC. This maps to `06:00`, `10:00`, `14:00`, `18:00` MSK.

## Manual smoke

Wrapper was run twice manually.

```text
[2026-05-20T19:43:46+03:00] === sales_kpi refresh start ===
Refresh: OK
[2026-05-20T19:44:34+03:00] refresh OK
[2026-05-20T19:44:50+03:00] === sales_kpi refresh start ===
Refresh: OK
[2026-05-20T19:45:37+03:00] refresh OK
[2026-05-20T19:45:37+03:00] === alert-check ===
{"consecutive_failures": 0, "threshold": 2}
```

## Output Sheet verification

`sync_log` after VPS smoke:

```text
sync_rows_total 6
['2026-05-20T17:56:45+03:00', 'ok', 'phase 3', 56400, 30]
['2026-05-20T17:58:06+03:00', 'ok', 'phase 3', 56405, 30]
['2026-05-20T18:01:35+03:00', 'ok', 'phase 3', 53095, 30]
['2026-05-20T19:44:26+03:00', 'ok', 'phase 3', 40204, 30]
['2026-05-20T19:45:30+03:00', 'ok', 'phase 3', 39651, 30]
plan_rows 30
```

Result:

- `sync_log` received 2 new ok rows from VPS manual runs.
- `Plan` remained 30 rows.
- Alert check returned `consecutive_failures=0`.

## Notes

- VPS system timezone is `Etc/UTC`; wrapper exports `TZ=Europe/Moscow` so logs use MSK.
- Bitrix sync script used by wrapper: `/opt/openclaw/repos/vibecoding/shared/scripts/bitrix-sync-state.sh`.
- No Bitrix write methods were used.

## Freshness health-check

After syncing the final Phase 4 code to VPS:

```bash
GOOGLE_SA_KEY=/opt/openclaw/secrets/finance-director-sheets-903611b799c3.json \
BITRIX_STATE_PATH=/opt/openclaw/state/bitrix_app/install.latest.json \
BITRIX_SYNC_SCRIPT=/opt/openclaw/repos/vibecoding/shared/scripts/bitrix-sync-state.sh \
PYTHONPATH=/opt/cloudbot-runtime/larisa/sales-kpi-dashboard/sales_dashboard \
.venv/bin/python -m sales_kpi_dashboard.cli health-check
```

Output:

```json
{"ok": true, "status": "ok", "ts": "2026-05-20T19:45:30+03:00", "message": "sales_kpi: OK, последний refresh 2026-05-20T19:45:30+03:00"}
```
