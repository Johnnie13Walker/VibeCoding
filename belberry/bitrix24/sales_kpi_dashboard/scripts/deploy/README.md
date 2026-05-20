# VPS deployment instructions

## Один раз

```bash
ssh root@cloudbot-ssh-proxy
mkdir -p /opt/cloudbot-runtime/larisa/sales-kpi-dashboard
cd /opt/cloudbot-runtime/larisa/sales-kpi-dashboard

# Скопировать из repo модули:
# - sales_dashboard/
# - sales_kpi_dashboard/

python3 -m venv .venv
.venv/bin/pip install -e ./sales_dashboard
.venv/bin/pip install -e ./sales_kpi_dashboard

mkdir -p /opt/openclaw/secrets
# Скопировать service-account JSON вне git:
# /opt/openclaw/secrets/finance-director-sheets-903611b799c3.json
chmod 600 /opt/openclaw/secrets/finance-director-sheets-903611b799c3.json

# Bitrix OAuth refresh script уже есть на VPS:
# /opt/openclaw/repos/vibecoding/shared/scripts/bitrix-sync-state.sh

cp sales_kpi_dashboard/scripts/deploy/cloudbot-larisa-sales-kpi.sh /usr/local/bin/
chmod +x /usr/local/bin/cloudbot-larisa-sales-kpi.sh

cp sales_kpi_dashboard/scripts/deploy/cloudbot-larisa-sales-kpi.cron /etc/cron.d/cloudbot-larisa-sales-kpi
chmod 644 /etc/cron.d/cloudbot-larisa-sales-kpi

# Проверка
/usr/local/bin/cloudbot-larisa-sales-kpi.sh
tail -50 /var/log/cloudbot-larisa-sales-kpi.log
```

## После каждого обновления кода

```bash
ssh root@cloudbot-ssh-proxy
cd /opt/cloudbot-runtime/larisa/sales-kpi-dashboard
git pull
.venv/bin/pip install -e ./sales_dashboard
.venv/bin/pip install -e ./sales_kpi_dashboard
```

Cron подхватит новую версию на следующем тике автоматически.
