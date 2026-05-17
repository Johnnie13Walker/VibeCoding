#!/usr/bin/env bash
# Cron-обёртка для cyclic enrich pipeline (каждые 2 часа).
# Workflow:
#   1) sync bitrix state
#   2) generate empty_companies_to_enrich.json (компании без валидного RQ_INN)
#   3) empty-discover (фильтр merge_groups + do_not_touch + already_has_inn)
#   4) empty-enrich --limit N (HTTP/rusprofile lookup)
#   5) empty-upload-plan + empty-manual-site (Sheets витрины)
#   6) [OPTIONAL] empty-apply --live --confirm-apply (запись BP в Bitrix)
#
# Env-флаги для контроля:
#   CCE_LOOP_DRY=1            — только до upload-plan/manual-site, без apply (default)
#   CCE_LOOP_LIMIT=10         — максимум компаний для enrich за один проход
#   CCE_LOOP_APPLY=1          — включить empty-apply --live

set -euo pipefail
export TZ=Europe/Moscow

# Env (по образцу cloudbot-empty-companies-score.sh)
if [[ -f /opt/openclaw/.env ]]; then set -a; source /opt/openclaw/.env; set +a; fi
if [[ -f /etc/openclaw/larisa.env ]]; then set -a; source /etc/openclaw/larisa.env; set +a; fi

WORKTREE=/opt/openclaw/repos/vibecoding-enrich
VENV=/opt/openclaw/venvs/crm_company_enrich
PYTHON="$VENV/bin/python"
DATA_DIR="$WORKTREE/belberry/bitrix24/data"
LOG="/var/log/crm_company_enrich_loop.log"

export CCE_STATE_PATH="${CCE_STATE_PATH:-/opt/openclaw/state/bitrix_app/install.latest.json}"
export CCE_SERVICE_ACCOUNT_JSON="${CCE_SERVICE_ACCOUNT_JSON:-/opt/openclaw/secrets/finance-director-sheets.json}"
export CCE_WORKSPACE_ROOT="$WORKTREE"
export CCE_DATA_DIR="$DATA_DIR"

LIMIT="${CCE_LOOP_LIMIT:-10}"
DO_APPLY="${CCE_LOOP_APPLY:-0}"

mkdir -p "$DATA_DIR"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG"; }

log "=== enrich-loop start (limit=$LIMIT apply=$DO_APPLY) ==="

# 1) Sync Bitrix state (cloudbot is running on VPS — already fresh, but be defensive)
# Skip sync — state managed by openclaw-update-maintenance + bitrix-app

# 2) Compose input.json from existing companies.json + requisites.json snapshot
log "step compose-input"
"$PYTHON" - << 'PY'
import json, os, sys
from pathlib import Path

DATA = Path(os.environ['CCE_DATA_DIR'])
SRC_DIR = Path('/opt/openclaw/data/empty_co')
companies = json.loads((SRC_DIR / 'companies.json').read_text())
requisites = json.loads((SRC_DIR / 'requisites.json').read_text())

# Map company_id → list of (RQ_INN, RQ_OGRN)
inn_by_company = {}
for r in requisites:
    cid = str(r.get('ENTITY_ID'))
    inn = (r.get('RQ_INN') or '').strip()
    ogrn = (r.get('RQ_OGRN') or '').strip() or (r.get('RQ_OGRNIP') or '').strip()
    if inn or ogrn:
        inn_by_company.setdefault(cid, []).append({'inn': inn, 'ogrn': ogrn})

# Filter: companies without ANY requisite with INN or OGRN
empty_pool = []
for c in companies:
    cid = str(c.get('ID'))
    if cid in inn_by_company:
        continue
    empty_pool.append({
        'id': cid,
        'title': c.get('TITLE') or '',
        'phone': [p.get('VALUE') for p in (c.get('PHONE') or []) if p.get('VALUE')],
        'email': [e.get('VALUE') for e in (c.get('EMAIL') or []) if e.get('VALUE')],
        'site_uf': c.get('UF_CRM_5DEF838D882A2') or '',
        'city_uf': c.get('UF_CRM_1584876724') or '',
        'industry': c.get('INDUSTRY') or '',
        'assigned_by': c.get('ASSIGNED_BY_ID') or '',
        'date_create': c.get('DATE_CREATE') or '',
    })

out = DATA / 'empty_companies_to_enrich.json'
out.write_text(json.dumps(empty_pool, ensure_ascii=False, indent=2), encoding='utf-8')
print(f"compose: total_companies={len(companies)} with_requisite={len(inn_by_company)} empty_pool={len(empty_pool)} → {out}")
PY

# 3-5) Run pipeline
log "step empty-discover"
"$PYTHON" -m crm_company_enrich.cli empty-discover --limit "$LIMIT" 2>&1 | tee -a "$LOG"

log "step empty-enrich (HTTP/rusprofile)"
CCE_ENRICH_HTTP_TIMEOUT_S=6 CCE_ENRICH_HTTP_RETRIES=1 CCE_ENRICH_HTTP_DELAY_S=0.2 \
  "$PYTHON" -m crm_company_enrich.cli empty-enrich --limit "$LIMIT" 2>&1 | tee -a "$LOG"

log "step empty-upload-plan"
"$PYTHON" -m crm_company_enrich.cli empty-upload-plan 2>&1 | tee -a "$LOG"

log "step empty-manual-site (записать NOT_FOUND в ручную вкладку)"
"$PYTHON" -m crm_company_enrich.cli empty-manual-site 2>&1 | tee -a "$LOG"

# 6) Apply, только если CCE_LOOP_APPLY=1
if [[ "$DO_APPLY" == "1" ]]; then
  log "step empty-apply --live"
  "$PYTHON" -m crm_company_enrich.cli empty-apply --live --confirm-apply 2>&1 | tee -a "$LOG"
else
  log "step empty-apply SKIPPED (CCE_LOOP_APPLY!=1, dry-only-mode)"
fi

log "=== enrich-loop done ==="
