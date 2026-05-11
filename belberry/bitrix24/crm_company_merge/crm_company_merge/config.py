from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Ошибка конфигурации окружения."""


@dataclass(frozen=True)
class Config:
    bitrix_state_path: Path
    sheet_id: str
    google_service_account_json: Path
    telegram_bot_token: str | None
    telegram_chat_id: int | None
    timezone: str = "Europe/Moscow"
    pause_flag_path: Path = Path("/opt/openclaw/state/crm_company_merge.paused")

    @classmethod
    def from_env(cls) -> "Config":
        required = {
            "BITRIX_STATE_PATH": os.getenv("BITRIX_STATE_PATH"),
            "SHEET_ID": os.getenv("SHEET_ID"),
            "GOOGLE_SERVICE_ACCOUNT_JSON": os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ConfigError(
                "Не заданы обязательные переменные окружения: " + ", ".join(missing)
            )

        telegram_chat_id = _parse_optional_int(os.getenv("TELEGRAM_CHAT_ID"), "TELEGRAM_CHAT_ID")

        return cls(
            bitrix_state_path=Path(str(required["BITRIX_STATE_PATH"])),
            sheet_id=str(required["SHEET_ID"]),
            google_service_account_json=Path(str(required["GOOGLE_SERVICE_ACCOUNT_JSON"])),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=telegram_chat_id,
            timezone=os.getenv("TZ") or "Europe/Moscow",
        )


def _parse_optional_int(value: str | None, name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть целым числом") from exc
