#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

require_env PRIMARY_HOST VPN_PORT

prepare_node() {
  local host="$1"
  local node_name="$2"
  local cfg_backup="/etc/happ-vpn/backups/${node_name}_$(date '+%Y%m%d_%H%M%S')"

  log "Подготовка узла ${node_name} (${host})"
  run_remote_script "$host" "
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
mkdir -p /etc/happ-vpn/current /etc/happ-vpn/backups /var/log/happ-vpn
if [ -d /etc/sing-box ]; then
  mkdir -p '${cfg_backup}'
  cp -a /etc/sing-box '${cfg_backup}/' || true
fi
apt-get update -y
apt-get install -y ufw fail2ban curl ca-certificates jq nginx uuid-runtime openssl tar certbot python3-certbot-nginx
id happvpn >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin happvpn
mkdir -p /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/99-happ-hardening.conf <<'SSHCFG'
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
SSHCFG
sshd -t
systemctl reload ssh || systemctl reload sshd || true
if ! command -v sing-box >/dev/null 2>&1; then
  arch=\$(uname -m)
  case \"\$arch\" in
    x86_64) sb_arch=amd64 ;;
    aarch64|arm64) sb_arch=arm64 ;;
    *) echo \"Unsupported arch: \$arch\"; exit 1 ;;
  esac
  tag=\$(curl -fsSL https://api.github.com/repos/SagerNet/sing-box/releases/latest | jq -r .tag_name)
  ver=\${tag#v}
  pkg_url=\"https://github.com/SagerNet/sing-box/releases/download/\${tag}/sing-box-\${ver}-linux-\${sb_arch}.tar.gz\"
  tmp_dir=\$(mktemp -d)
  curl -fsSL \"\$pkg_url\" -o \"\$tmp_dir/sing-box.tgz\"
  tar -xzf \"\$tmp_dir/sing-box.tgz\" -C \"\$tmp_dir\"
  install -m 0755 \"\$tmp_dir\"/sing-box-*/sing-box /usr/local/bin/sing-box
  rm -rf \"\$tmp_dir\"
fi
ufw allow ${SSH_PORT:-22}/tcp
ufw allow 80/tcp
ufw allow ${VPN_PORT}/tcp
ufw --force enable
systemctl enable fail2ban
systemctl restart fail2ban
"

  run_remote_script "$host" "
set -euo pipefail
if [ ! -f /etc/happ-vpn/current/secrets.env ]; then
  uuid=\$(cat /proc/sys/kernel/random/uuid)
  keypair=\$(/usr/local/bin/sing-box generate reality-keypair)
  private_key=\$(printf '%s\n' \"\$keypair\" | awk -F': ' '/PrivateKey/{print \$2}')
  public_key=\$(printf '%s\n' \"\$keypair\" | awk -F': ' '/PublicKey/{print \$2}')
  short_id=\$(openssl rand -hex 8)
  cat >/etc/happ-vpn/current/secrets.env <<SEC
UUID=\$uuid
REALITY_PRIVATE_KEY=\$private_key
REALITY_PUBLIC_KEY=\$public_key
SHORT_ID=\$short_id
SEC
  chmod 600 /etc/happ-vpn/current/secrets.env
fi
source /etc/happ-vpn/current/secrets.env
mkdir -p /etc/sing-box
cat >/etc/sing-box/config.json <<JSON
{
  \"log\": {
    \"level\": \"info\",
    \"timestamp\": true
  },
  \"inbounds\": [
    {
      \"type\": \"vless\",
      \"tag\": \"vless-in\",
      \"listen\": \"::\",
      \"listen_port\": ${VPN_PORT},
      \"users\": [
        {
          \"uuid\": \"\${UUID}\",
          \"flow\": \"xtls-rprx-vision\"
        }
      ],
      \"tls\": {
        \"enabled\": true,
        \"server_name\": \"www.cloudflare.com\",
        \"reality\": {
          \"enabled\": true,
          \"handshake\": {
            \"server\": \"www.cloudflare.com\",
            \"server_port\": 443
          },
          \"private_key\": \"\${REALITY_PRIVATE_KEY}\",
          \"short_id\": [\"\${SHORT_ID}\"]
        }
      }
    }
  ],
  \"outbounds\": [
    { \"type\": \"direct\", \"tag\": \"direct\" }
  ]
}
JSON
cat >/etc/systemd/system/sing-box.service <<'UNIT'
$(cat "$ROOT_DIR/infra/templates/sing-box.service")
UNIT
systemctl daemon-reload
systemctl enable sing-box
systemctl restart sing-box
"
}

prepare_subscription() {
  local host="$1"
  log "Настройка subscription endpoint на ${host}"
  run_remote_script "$host" "
set -euo pipefail
sub_host='${SUBSCRIPTION_HOST:-$PRIMARY_HOST}'
sub_port='${SUBSCRIPTION_PORT:-8443}'
tls_mode='${SUBSCRIPTION_TLS_MODE:-selfsigned}'
source /etc/happ-vpn/current/secrets.env
mkdir -p /var/www/happ-subscription/subscription
cat >/var/www/happ-subscription/subscription/happ.txt <<SUB
vless://\${UUID}@${PRIMARY_HOST}:${VPN_PORT}?type=tcp&security=reality&sni=www.cloudflare.com&fp=chrome&pbk=\${REALITY_PUBLIC_KEY}&sid=\${SHORT_ID}&flow=xtls-rprx-vision&encryption=none#${PRIMARY_NODE_NAME:-happ-main}
SUB
cat >/etc/nginx/sites-available/happ-subscription.conf <<NGINX
server {
  listen 80;
  server_name \${sub_host};
  location ^~ /.well-known/acme-challenge/ {
    root /var/www/happ-subscription;
  }
  location = /subscription/happ.txt {
    default_type text/plain;
    alias /var/www/happ-subscription/subscription/happ.txt;
  }
  location = /healthz {
    return 200 'ok';
  }
}
NGINX
ln -sf /etc/nginx/sites-available/happ-subscription.conf /etc/nginx/sites-enabled/happ-subscription.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx
if [[ \"\${tls_mode}\" == \"letsencrypt\" ]]; then
  certbot certonly --webroot -w /var/www/happ-subscription -d \"\${sub_host}\" \
    --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring
  if [[ ! -f \"/etc/letsencrypt/live/\${sub_host}/fullchain.pem\" || ! -f \"/etc/letsencrypt/live/\${sub_host}/privkey.pem\" ]]; then
    echo \"LE сертификат не получен для \${sub_host}\" >&2
    exit 1
  fi
  systemctl enable certbot.timer
  systemctl start certbot.timer
  cat >>/etc/nginx/sites-available/happ-subscription.conf <<SSL
server {
  listen \${sub_port} ssl;
  server_name \${sub_host};
  ssl_certificate /etc/letsencrypt/live/\${sub_host}/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/\${sub_host}/privkey.pem;
  location = /subscription/happ.txt {
    default_type text/plain;
    alias /var/www/happ-subscription/subscription/happ.txt;
  }
  location = /healthz {
    return 200 'ok';
  }
}
SSL
elif [[ \"\${tls_mode}\" == \"selfsigned\" ]]; then
  if [[ ! -f /etc/happ-vpn/current/subscription.crt || ! -f /etc/happ-vpn/current/subscription.key ]]; then
    openssl req -x509 -nodes -newkey rsa:2048 -sha256 -days 365 \
      -keyout /etc/happ-vpn/current/subscription.key \
      -out /etc/happ-vpn/current/subscription.crt \
      -subj \"/CN=\${sub_host}\" \
      -addext \"subjectAltName=DNS:\${sub_host},IP:${PRIMARY_HOST}\"
    chmod 600 /etc/happ-vpn/current/subscription.key
  fi
  cat >>/etc/nginx/sites-available/happ-subscription.conf <<SSL
server {
  listen \${sub_port} ssl;
  server_name \${sub_host};
  ssl_certificate /etc/happ-vpn/current/subscription.crt;
  ssl_certificate_key /etc/happ-vpn/current/subscription.key;
  location = /subscription/happ.txt {
    default_type text/plain;
    alias /var/www/happ-subscription/subscription/happ.txt;
  }
  location = /healthz {
    return 200 'ok';
  }
}
SSL
fi
nginx -t
systemctl restart nginx
ufw allow \"\${sub_port}\"/tcp
"
}

prepare_node "$PRIMARY_HOST" "${PRIMARY_NODE_NAME:-happ-main}"
if [[ -n "${RESERVE_HOST:-}" ]]; then
  prepare_node "$RESERVE_HOST" "${RESERVE_NODE_NAME:-happ-backup}"
fi
prepare_subscription "$PRIMARY_HOST"

log "Deploy workflow завершен"
