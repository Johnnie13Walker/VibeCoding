#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0 <absolute_project_path>" >&2
  exit 1
fi

PROJECT_DIR="${1:-}"
if [[ -z "$PROJECT_DIR" || ! -d "$PROJECT_DIR/devops-sre/systemd" ]]; then
  echo "Usage: sudo $0 <absolute_project_path>" >&2
  exit 1
fi

SYSTEMD_DIR="/etc/systemd/system"
SRC_DIR="$PROJECT_DIR/devops-sre/systemd"
CHECKS_DIR="$PROJECT_DIR/devops-sre/checks"

chmod +x "$CHECKS_DIR/health_check.sh"
chmod +x "$CHECKS_DIR/daily_check.sh"
chmod +x "$CHECKS_DIR/weekly_check.sh"
chmod +x "$CHECKS_DIR/pobeda_promocode_watch.py"

cp "$SRC_DIR/devops-healthcheck.service" "$SYSTEMD_DIR/devops-healthcheck.service"
cp "$SRC_DIR/devops-healthcheck.timer" "$SYSTEMD_DIR/devops-healthcheck.timer"
cp "$SRC_DIR/devops-weekly-audit.service" "$SYSTEMD_DIR/devops-weekly-audit.service"
cp "$SRC_DIR/devops-weekly-audit.timer" "$SYSTEMD_DIR/devops-weekly-audit.timer"
cp "$SRC_DIR/pobeda-promocode-watch.service" "$SYSTEMD_DIR/pobeda-promocode-watch.service"
cp "$SRC_DIR/pobeda-promocode-watch.timer" "$SYSTEMD_DIR/pobeda-promocode-watch.timer"

sed -i.bak "s|/opt/devops-sre|$PROJECT_DIR/devops-sre|g" "$SYSTEMD_DIR/devops-healthcheck.service"
sed -i.bak "s|/opt/devops-sre|$PROJECT_DIR/devops-sre|g" "$SYSTEMD_DIR/devops-weekly-audit.service"
sed -i.bak "s|/opt/devops-sre|$PROJECT_DIR/devops-sre|g" "$SYSTEMD_DIR/pobeda-promocode-watch.service"

systemctl daemon-reload
systemctl enable --now devops-healthcheck.timer
systemctl enable --now devops-weekly-audit.timer
systemctl enable --now pobeda-promocode-watch.timer

echo "Installed and enabled:"
echo "- devops-healthcheck.timer"
echo "- devops-weekly-audit.timer"
echo "- pobeda-promocode-watch.timer"
