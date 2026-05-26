#!/usr/bin/env bash
# Cron-обёртка для ежедневного аудита дублей компаний по ИНН.
# Запускается на VPS 3 раза в сутки (08:00 / 14:00 / 20:00 МСК).
#
# Что делает:
#   1. Обновляет OAuth state Bitrix
#   2. Запускает scripts/audit_inn_duplicates.py
#   3. Опционально шлёт TG-уведомление при наличии дублей
#
# Расписание (cron на VPS):
#   0 8 * * *  /opt/openclaw/repos/vibecoding-enrich/belberry/bitrix24/crm_company_enrich/scripts/cloudbot-inn-dup-audit.sh
#   0 14 * * * /opt/openclaw/repos/vibecoding-enrich/belberry/bitrix24/crm_company_enrich/scripts/cloudbot-inn-dup-audit.sh
#   0 20 * * * /opt/openclaw/repos/vibecoding-enrich/belberry/bitrix24/crm_company_enrich/scripts/cloudbot-inn-dup-audit.sh

set -euo pipefail
export TZ=Europe/Moscow

# Env (TG token + service account paths)
if [[ -f /opt/openclaw/.env ]]; then set -a; source /opt/openclaw/.env; set +a; fi
if [[ -f /etc/openclaw/larisa.env ]]; then set -a; source /etc/openclaw/larisa.env; set +a; fi

WORKTREE=/opt/openclaw/repos/vibecoding-enrich
MODULE_DIR="$WORKTREE/belberry/bitrix24/crm_company_enrich"
VENV=/opt/openclaw/venvs/crm_company_enrich
PYTHON="$VENV/bin/python"
LOG_DIR=/opt/openclaw/logs/inn_dup_audit
LOG_FILE="$LOG_DIR/$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$LOG_DIR"

{
    echo "=== START $(date -Iseconds) ==="

    # 1. Обновить OAuth state Bitrix
    if [[ -x /opt/openclaw/bin/bitrix-refresh-token.sh ]]; then
        /opt/openclaw/bin/bitrix-refresh-token.sh || echo "WARN: refresh failed (продолжаем)"
    fi

    # 2. Запустить аудит (с TG-уведомлением если есть LARISA_TG_TOKEN)
    cd "$MODULE_DIR"
    PYTHONPATH="$MODULE_DIR" "$PYTHON" "$MODULE_DIR/scripts/audit_inn_duplicates.py" --tg

    echo "=== END $(date -Iseconds) ==="
} 2>&1 | tee "$LOG_FILE"

# Хранение логов: 30 дней (хвост)
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true
