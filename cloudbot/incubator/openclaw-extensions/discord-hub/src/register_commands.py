import sys

import requests

from common import Config


COMMANDS = [
    {
        "name": "kpi",
        "description": "Показать текущую KPI-сводку",
        "type": 1,
    },
    {
        "name": "alerts",
        "description": "Показать последние алерты",
        "type": 1,
    },
    {
        "name": "client",
        "description": "Показать сводку по клиенту",
        "type": 1,
        "options": [
            {
                "name": "client_id",
                "description": "ID клиента во внешней системе",
                "type": 3,
                "required": True,
            }
        ],
    },
]


def run() -> int:
    if not Config.discord_application_id:
        raise RuntimeError("DISCORD_APPLICATION_ID is not configured")
    if not Config.discord_bot_token:
        raise RuntimeError("DISCORD_COMMAND_BOT_TOKEN is not configured")

    url = f"https://discord.com/api/v10/applications/{Config.discord_application_id}/commands"
    headers = {
        "Authorization": f"Bot {Config.discord_bot_token}",
        "Content-Type": "application/json",
    }
    response = requests.put(url, json=COMMANDS, headers=headers, timeout=30)
    response.raise_for_status()
    print("Commands registered.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"register_commands failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
