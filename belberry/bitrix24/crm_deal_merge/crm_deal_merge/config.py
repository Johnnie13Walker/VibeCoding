"""Конфигурация crm_deal_merge."""
from __future__ import annotations

import os
from pathlib import Path

# Bitrix
FUNNEL_LOSER = "38"      # Реанимация — отсюда забираем LOSER
FUNNEL_WINNER = "50"     # Телемаркетинг — WINNER всегда отсюда
LOSE_STAGE_38 = "C38:3"  # «Дубль» — куда закрываем LOSER
LOSE_STAGE_50 = "C50:APOLOGY"  # «ОТВАЛ» — куда закрываем внутри-[50] дубли
OWNER_TYPE_DEAL = "2"

# Smart processes — entityTypeId которые умеют parent-link на сделку
# (15 типов в системе; обновляется автоматически через crm.type.list).
SP_PARENT_FIELD = "parentId2"  # стандартный userfield для parent=deal

# State и пути
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # belberry/bitrix24/.. → repo root
STATE_PATH = Path(os.environ.get(
    "BITRIX_STATE_PATH",
    "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json",
))
SYNC_SCRIPT = Path(os.environ.get(
    "BITRIX_SYNC_SCRIPT",
    "/Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh",
))
SERVICE_ACCOUNT_JSON = Path(
    os.environ.get(
        "GOOGLE_SA_KEY",
        "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json",
    )
)
LOG_DIR = Path(os.environ.get(
    "CRM_DEAL_MERGE_LOG_DIR",
    "/Users/pro2kuror/Desktop/VibeCoding/belberry/bitrix24/logs",
))
LOG_PATH = Path(os.environ.get("CRM_DEAL_MERGE_LOG_PATH", str(LOG_DIR / "crm_deal_merge.csv")))
BACKUP_DIR = Path(os.environ.get(
    "CRM_DEAL_MERGE_BACKUP_DIR",
    "/Users/pro2kuror/Desktop/VibeCoding/belberry/bitrix24/backups/merge",
))

# Google Sheet
SHEET_ID = os.environ.get("CRM_DEAL_MERGE_SHEET_ID", "1WaCtF2BeBorGXkZa0a53Bi6T_lKHeZZwQPEO8qIzmFU")
TAB_GROUPS = "merge_groups"
TAB_INVENTORY = "merge_inventory"
TAB_LOG = "merge_log"
TAB_BACKUP_PREFIX = "merge_backup_"  # + company_id + domain

# Rate-limit поведение
RATE_LIMIT_SLEEP_S = float(os.environ.get("CRM_DEAL_MERGE_RATE_LIMIT_SLEEP_S", "0.55"))
PORTAL_DOMAIN = "belberrycrm.bitrix24.ru"

# Маркеры в комментах
TIMELINE_TRANSFER_MARKER = "[crm_deal_merge: перенесено из сделки"
COMMENT_LOSE_TEMPLATE = (
    "\n---\ncrm_deal_merge {ts}\n"
    "Закрыто как дубль. Актуальная сделка: #{winner_id}\n"
    "https://{portal}/crm/deal/details/{winner_id}/\n"
    "Перенесено: {n_acts} активностей, {n_tl} комментариев, {n_cont} контактов."
)
TIMELINE_WINNER_SUMMARY = (
    "[{ts} crm_deal_merge]\n"
    "К этой сделке привязаны закрытые дубли из воронки [38] Реанимация: {loser_ids}\n"
    "Итого перенесено: {n_acts} активностей, {n_tl} комментариев, {n_cont} контактов."
)
