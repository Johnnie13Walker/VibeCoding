"""Синхронизация прав доступа: REVOKE-only.

Логика (важно):
- **Доступ выдаёте вы вручную** через Share-кнопку в Google Sheets или
  Looker Studio. Скрипт НИКОГДА не добавляет новые permissions.
- Скрипт только **снимает** доступ у тех, кто:
  1. сейчас имеет reader-доступ к Sheet (или Looker Studio отчёту);
  2. найден в Bitrix24 user.get как ACTIVE=N (уволен / деактивирован).
- Email из whitelist никогда не трогается (даже если в Bitrix он
  деактивирован или отсутствует).
- Email, который вообще не найден в Bitrix (внешние партнёры, ваш
  личный gmail без учётки Belberry) — **не трогается**. Иначе синк
  отрезал бы всех гостевых смотрящих.

Это значит:
- Сотрудника увольняют → ACTIVE=N в Bitrix → user-sync снимает доступ
  в течение ≤15 минут.
- Сотруднику добавляют учётку в Bitrix → НЕ получает автоматический
  доступ. Вы вручную шарите Sheet / Looker Studio на его email.
- Партнёр получил доступ на гостевой gmail → Bitrix его не знает → синк
  не тронет.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config
from .bitrix_client import BitrixClient
from .extractors.users import extract_users, USER_HEADER
from .sheets_client import SheetsClient


@dataclass
class SyncState:
    whitelist_emails: list[str] = field(default_factory=list)
    looker_report_ids: list[str] = field(default_factory=list)
    last_run: str = ""

    @classmethod
    def load(cls, path: Path) -> "SyncState":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(
            whitelist_emails=data.get("whitelist_emails", []),
            looker_report_ids=data.get("looker_report_ids", []),
            last_run=data.get("last_run", ""),
        )

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "whitelist_emails": sorted(set(self.whitelist_emails)),
                    "looker_report_ids": self.looker_report_ids,
                    "last_run": self.last_run,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def run_user_sync(dry_run: bool = False) -> int:
    if not config.SHEET_ID:
        print("ERR: config.SHEET_ID пуст.")
        return 1

    state = SyncState.load(config.USER_SYNC_STATE_PATH)
    bx = BitrixClient(log_path=config.LOG_PATH)
    sh = SheetsClient(config.SHEET_ID, config.SERVICE_ACCOUNT_JSON)

    print(f"== user-sync (REVOKE-only) {'[DRY RUN]' if dry_run else ''} ==")
    print(f"   whitelist ({len(state.whitelist_emails)}): "
          f"{', '.join(state.whitelist_emails) or '(empty)'}")

    # 1) Bitrix → карта email → ACTIVE
    user_rows = extract_users(bx)
    email_idx = USER_HEADER.index("email")
    active_idx = USER_HEADER.index("active")
    full_idx = USER_HEADER.index("full_name")

    bitrix_status: dict[str, tuple[bool, str]] = {}  # email → (active, full_name)
    for row in user_rows:
        email = (row[email_idx] or "").strip().lower()
        if not email:
            continue
        active = row[active_idx] == "Y"
        bitrix_status[email] = (active, row[full_idx])
    print(f"   Bitrix users with email: {len(bitrix_status)} "
          f"({sum(1 for a,_ in bitrix_status.values() if a)} active, "
          f"{sum(1 for a,_ in bitrix_status.values() if not a)} inactive)")

    whitelist = {e.lower() for e in state.whitelist_emails}

    # 2) Ресурсы для синка
    resources: list[tuple[str, str]] = [("sheet", config.SHEET_ID)]
    for rid in state.looker_report_ids:
        resources.append(("looker_report", rid))

    revoked_total = 0
    for kind, fid in resources:
        print(f"\n   → {kind} {fid}")
        try:
            perms = sh.list_permissions(fid)
        except Exception as e:
            print(f"     FAIL list_permissions: {e}")
            continue

        any_action = False
        for p in perms:
            email = (p.get("emailAddress") or "").lower()
            role = p.get("role", "")
            pid = p.get("id")
            if not email or role in ("owner",):
                continue
            if email in whitelist:
                continue
            status = bitrix_status.get(email)
            if status is None:
                # незнакомый email (партнёр / гость) — не трогаем
                continue
            active, full_name = status
            if active:
                # активный сотрудник, доступ оставляем
                continue
            # найден в Bitrix как inactive → revoke
            print(f"     − revoke  {email}  ({full_name})  [Bitrix ACTIVE=N]")
            any_action = True
            if not dry_run and pid:
                try:
                    sh.remove_permission(fid, pid)
                    revoked_total += 1
                except Exception as e:
                    print(f"       FAIL: {e}")

        if not any_action:
            print(f"     (нечего снимать)")

    if not dry_run:
        state.last_run = datetime.now(config.MOSCOW_TZ).isoformat(timespec="seconds")
        state.save(config.USER_SYNC_STATE_PATH)

    print(f"\n   Revoked: {revoked_total}")
    return 0
