# Baseline server runtime

Дата фиксации: 2026-04-23 11:34:36 МСК  
Host: `ams-1-vm-76ds`  
Mode: direct read-only SSH with existing key. No restart, deploy, edit, env read, symlink change, cron change, systemd change, or docker change was performed.

## 1. Runtime symlinks

### Larisa

```text
/opt/cloudbot-runtime/larisa/current
-> /opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326
```

Metadata:

```text
RELEASE_ID=codex_feature_self-healing_067d326
RELEASE_BRANCH=codex/feature/self-healing
RELEASE_COMMIT=067d326c5c23e4486efbef87741012211af1adaf
RELEASED_AT_MSK=2026-04-18 07:13:11 MSK
```

### Lev / Sales

```text
/opt/cloudbot-runtime/current
-> /opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60
```

Metadata:

```text
RELEASE_ID=codex_feature_self-healing_c329f60
RELEASE_BRANCH=codex/feature/self-healing
RELEASE_COMMIT=c329f6077b87dc332703d043dc82a41b9f131edd
RELEASED_AT_MSK=2026-04-10 15:49:11 MSK
```

## 2. Relevant active cron files

### `/etc/cron.d/cloudbot-larisa-daily-brief`

File:

```text
-rw-r--r-- 1 root root 334 Apr 23 06:24 /etc/cron.d/cloudbot-larisa-daily-brief
```

Active schedule:

```text
0 5 * * * root /usr/local/bin/cloudbot-larisa-daily-brief.sh >> /home/ops/cloudbot-larisa-agent/reports/larisa_daily_brief_cron.log 2>&1
```

Commented contract: `05:00 UTC = 08:00 МСК`.

### `/etc/cron.d/cloudbot-sales-reports`

File:

```text
-rw-r--r-- 1 root root 961 Apr 10 12:49 /etc/cron.d/cloudbot-sales-reports
```

Active schedules:

```text
30 6 * * 1-5 root /usr/local/bin/cloudbot-sales-daily-brief.sh >> /home/ops/cloudbot-sales-agent/reports/sales_daily_cron.log 2>&1
40 6 * * 1-5 root /usr/local/bin/cloudbot-sales-morning-check.sh >> /home/ops/cloudbot-sales-agent/reports/sales_morning_check_cron.log 2>&1
0 14 * * * root /usr/local/bin/cloudbot-sales-followup.sh >> /home/ops/cloudbot-sales-agent/reports/sales_followup_cron.log 2>&1
30 15 * * 5 root /usr/local/bin/cloudbot-sales-weekly-review.sh >> /home/ops/cloudbot-sales-agent/reports/sales_weekly_cron.log 2>&1
```

Commented contract:

- `06:30 UTC = 09:30 МСК`
- `06:40 UTC = 09:40 МСК`
- `14:00 UTC = 17:00 МСК`
- `15:30 UTC = 18:30 МСК`

### `/etc/cron.d/openclaw-todo-digest`

File:

```text
-rw-r--r-- 1 root root 3183 Apr 18 04:22 /etc/cron.d/openclaw-todo-digest
```

Active jobs:

```text
*/30 * * * * root docker exec openclaw-openclaw-gateway-1 ... npm run sync
55 4 * * * root docker exec openclaw-openclaw-gateway-1 ... npm run sync
55 15 * * * root docker exec openclaw-openclaw-gateway-1 ... npm run sync
55 10 * * * root docker exec openclaw-openclaw-gateway-1 ... npm run sync
* * * * * root docker exec openclaw-openclaw-gateway-1 ... npm run reminders:tick
*/15 * * * * root docker exec openclaw-openclaw-gateway-1 ... npm run execution:tick
```

Disabled by comments:

```text
digest:morning
digest:midday
digest:evening
focus:tick
```

### `/etc/cron.d/openclaw-whoop-report`

File:

```text
-rw-r--r-- 1 root root 217 Mar 4 13:44 /etc/cron.d/openclaw-whoop-report
```

Active schedule:

```text
1 5 * * * root /usr/bin/env WHOOP_ENV_FILE=/etc/openclaw/whoop.env /usr/local/bin/send_whoop_report.py send-report >> /var/log/openclaw-whoop-report.log 2>&1
```

Commented contract: `05:01 UTC = 08:01 МСК`.

## 3. Relevant services

### `cloudbot-bitrix-app.service`

```text
enabled
active
LoadState=loaded
ActiveState=active
SubState=running
FragmentPath=/etc/systemd/system/cloudbot-bitrix-app.service
WorkingDirectory=/opt/openclaw
EnvironmentFiles=/opt/openclaw/.env (ignore_errors=no)
ExecStart=/usr/bin/python3 /opt/openclaw/local/bitrix_app_server.py
PID at check time: 721
Start time: Sat 2026-04-18 15:41:24 UTC
```

### `docker.service`

```text
enabled
active
LoadState=loaded
ActiveState=active
SubState=running
FragmentPath=/usr/lib/systemd/system/docker.service
ExecStart=/usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
PID at check time: 937
Start time: Sat 2026-04-18 15:41:26 UTC
```

## 4. Relevant containers

```text
openclaw-openclaw-gateway-1 | openclaw:ddg-searxng-20260412 | Up 26 hours (healthy) | 127.0.0.1:18789-18790->18789-18790/tcp
searxng                     | searxng/searxng:latest          | Up 4 days            | 0.0.0.0:8088->8080/tcp, [::]:8088->8080/tcp
searxng-redis               | valkey/valkey:8-alpine          | Up 4 days            | 6379/tcp
```

Compose projects:

```text
openclaw  running(1)  /opt/openclaw/docker-compose.yml
searxng   running(2)  /opt/searxng/docker-compose.yml
```

## 5. Env file paths only

Secret values were not read or printed.

```text
/opt/openclaw/.env
/opt/openclaw/.env.security_profile
/etc/openclaw/larisa.env
/etc/openclaw/sales_agent.env
/etc/openclaw/todo.env
/etc/openclaw/whoop.env
/root/.openclaw/workspace/todo-integration/.env.runtime
```

Observed file metadata:

```text
-rw------- root root /opt/openclaw/.env
-rw------- root root /opt/openclaw/.env.security_profile
-rw------- root root /etc/openclaw/larisa.env
-rw-r----- root root /etc/openclaw/sales_agent.env
-rw------- root root /etc/openclaw/todo.env
-rw------- root root /etc/openclaw/whoop.env
-rw------- ops  ops  /root/.openclaw/workspace/todo-integration/.env.runtime
```

## 6. Report/log freshness by timestamp only

```text
2026-04-22 08:00:15 UTC | 7061 bytes  | /home/ops/cloudbot-larisa-agent/reports/larisa_daily_brief_cron.log
2026-04-23 06:31:09 UTC | 5852 bytes  | /home/ops/cloudbot-sales-agent/reports/sales_daily_cron.log
2026-04-23 06:40:01 UTC | 5972 bytes  | /home/ops/cloudbot-sales-agent/reports/sales_morning_check_cron.log
2026-04-22 14:00:02 UTC | 10095 bytes | /home/ops/cloudbot-sales-agent/reports/sales_followup_cron.log
2026-04-17 15:31:16 UTC | 1856 bytes  | /home/ops/cloudbot-sales-agent/reports/sales_weekly_cron.log
2026-04-23 05:05:35 UTC | 121127 bytes | /var/log/openclaw-whoop-report.log
2026-04-23 08:30:09 UTC | 479 bytes   | /var/log/openclaw-todo-sync.log
2026-04-23 08:34:04 UTC | 320 bytes   | /var/log/openclaw-todo-reminders.log
2026-04-23 08:30:09 UTC | 327 bytes   | /var/log/openclaw-execution-tick.log
2026-04-23 07:15:11 UTC | 29893 bytes | /var/log/openclaw-backup.log
2026-04-23 07:30:17 UTC | 1449 bytes  | /var/log/host-security-check.log
```

Recent Larisa runtime reports:

```text
2026-04-20 08:00 МСК | /opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260420_080001_MSK.txt
2026-04-21 08:00 МСК | /opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260421_080001_MSK.txt
2026-04-22 08:00 МСК | /opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260422_080001_MSK.txt
2026-04-23 09:11 МСК | /opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260423_091102_MSK.txt
2026-04-23 09:25 МСК | /opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260423_092513_MSK.txt
```

## 7. Server baseline conclusion

- Larisa runtime is scoped and live-confirmed at `/opt/cloudbot-runtime/larisa/current`.
- Lev/Sales runtime is live-confirmed at generic `/opt/cloudbot-runtime/current`.
- OpenClaw gateway and Docker are active.
- Bitrix app service is active.
- Todo legacy contour still actively runs sync/reminders/execution through Docker.
- WHOOP report cron is active.
- No runtime mutation was performed.

