import os
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


def load_config(required: list[str] | None = None) -> dict[str, str]:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(dotenv_path=env_path, override=False)

    required = required or ["DATABASE_URL"]
    missing = [name for name in required if not os.environ.get(name)]

    if missing:
        raise ConfigError(f"Missing required env vars: {', '.join(missing)}")

    return {name: os.environ[name] for name in required}
