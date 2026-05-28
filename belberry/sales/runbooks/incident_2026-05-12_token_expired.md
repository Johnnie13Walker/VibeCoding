# Инцидент 2026-05-12 — Bitrix OAuth `EXPIRED_TOKEN`, утренний dispatch не доставлен

## Симптом

09:30 МСК cron запустился, python упал на сборе Bitrix snapshot:

```
event=sales_error error="The access token provided has expired."
```

`sales_dispatch_start` в лог не записан → 09:40 health-check
ушёл в alert «утренняя рассылка sales за 2026-05-12 неполная».

## Что НЕ сработало автоматически

Refresh-flow в `cloudbot/providers/bitrix/bitrix_app_auth.py:565-585`
обрабатывает `EXPIRED_TOKEN` сам:

```python
should_refresh = error.http_status == 401 or upper_code == "EXPIRED_TOKEN"
if not should_refresh:
    raise
state = self.refresh_access_token()
payload = self._call_payload_with_state(state, method, params=params)
```

Раз retry не помог, варианты:

1. `refresh_access_token()` тоже упал, и в логе должен быть `REFRESH_FAILED`/
   `REFRESH_INVALID_PAYLOAD`/`URL_ERROR`. Чаще всего — refresh_token
   revoked (Bitrix-приложение переустановили на портале).
2. State-файл указывает на старый `install.*.json`, у которого
   refresh_token уже неактуален. Загрузчик берёт самый свежий по
   `saved_at`, но если последний install не дошёл до диска или
   `saved_at` старый — выбирается невалидный.
3. `client_id`/`client_secret` в `/opt/openclaw/.env` или
   `/etc/openclaw/sales_agent.env` не совпадают с тем, что прописан
   у app на портале (после reinstall ключи могли поменяться).
4. Сетевой блок до `oauth.bitrix.info` / `oauth.bitrix24.tech` /
   домена клиента.

## Диагностика (server-runnable)

См. `scripts/diagnose_oauth.sh` в этой папке. Запуск:

```bash
ssh cloudbot-ssh-proxy
sudo -i
bash /tmp/diagnose_oauth.sh
```

Скрипт выводит:

- `saved_at` и `auth_refreshed_at` всех `install.*.json` и `handler.*.json`
- какой файл выбрал бы loader (последний по `saved_at`)
- маскированные access/refresh присутствие
- проверку доступности OAuth refresh endpoint
- последние 20 событий `sales_agent.log`

## Восстановление

### Путь A — refresh всё ещё рабочий, нужен только триггер

```bash
ssh cloudbot-ssh-proxy
cd /opt/cloudbot-runtime/current
source /opt/openclaw/.env
source /etc/openclaw/sales_agent.env
python3 - <<'PY'
from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAppAuth
auth = BitrixAppAuth()
state = auth.refresh_access_token()
print("refreshed; saved_at =", state.record.get("saved_at"))
PY
```

После успеха — повторный manual dispatch (см. ниже).

### Путь B — refresh_token revoked, нужен reinstall app

1. На портале `belberrycrm.bitrix24.ru` → Приложения → Локальные →
   приложение CloudBot/OpenClaw → **Переустановить**.
2. Bitrix дёрнет install-handler приложения, который запишет новый
   `install.*.json` в `/opt/openclaw/state/bitrix_app/`.
3. Убедиться, что `install.latest.json` (или новый файл с большим
   `saved_at`) появился: `ls -lt /opt/openclaw/state/bitrix_app/install*.json | head`.
4. Запустить путь A для проверки или сразу manual dispatch.

### Путь C — state-файл повреждён, нужен ручной fix

Если `install.latest.json` ссылается на старую инсталляцию:

```bash
cd /opt/openclaw/state/bitrix_app
ls -lt install.*.json | head -5
# выбрать самый свежий валидный и подменить:
cp install.<свежий>.json install.latest.json
```

Затем путь A.

## Manual test dispatch

См. `scripts/send_test_message.sh`. Шлёт **в личный тестовый чат**,
не в боевой owner-чат:

```bash
ssh cloudbot-ssh-proxy
SALES_CHAT_ID=<ваш_test_chat_id> bash /tmp/send_test_message.sh
```

## Боевое восстановление dispatch

После того как путь A показал успех и тестовое сообщение пришло:

```bash
cd /opt/cloudbot-runtime/current
source /opt/openclaw/.env
source /etc/openclaw/sales_agent.env
export TZ=Europe/Moscow
export SALES_TRIGGER=manual_recovery
export SALES_JOB_NAME=morning_sales_dispatch
python3 -m agents.lev_petrovich --report sales --send
```

`SALES_JOB_NAME=morning_sales_dispatch` важно, чтобы health-check
увидел trio в окне «сегодня МСК ≥ 09:30» и закрыл alert.

## Post-mortem TODO

См. секцию 17 первоначального аудита. Ключевые точки:

- [ ] Раннее событие `sales_job_process_start` в начале
  `SalesAgent.run()` — чтобы 09:40 check умел отличать «cron не
  стартовал» от «cron стартовал и упал до snapshot».
- [ ] Точнее форматировать `sales_error` — отдельный `error.code`
  поле (а не только текст), чтобы health-check показывал причину.
- [ ] Логировать сам факт `refresh_access_token()` (success/fail) в
  `sales_agent.log`, а не только в внутренние state-комментарии.
- [ ] Алерт от Bitrix install-webhook — если приходит новый
  `install.*.json`, кидать уведомление, что произошла переустановка.
