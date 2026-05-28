"""Telegram route-адаптеры Ларисы Ивановны."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import os
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from ..config import DEFAULT_CONFIG, TelegramRouteConfig


@dataclass(frozen=True)
class TelegramRouteDescription:
    route_key: str
    bot_token_env: str | None
    chat_id_env: str | None
    parse_mode: str


class TelegramProvider(ABC):
    @abstractmethod
    def describe_route(self) -> TelegramRouteDescription:
        raise NotImplementedError

    @abstractmethod
    def send(
        self,
        text: str,
        *,
        chat_id: str = "",
        send_reply: Callable[..., Any] | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class NullTelegramProvider(TelegramProvider):
    def describe_route(self) -> TelegramRouteDescription:
        telegram_config = DEFAULT_CONFIG.telegram
        return TelegramRouteDescription(
            route_key=telegram_config.route_key,
            bot_token_env=telegram_config.bot_token_env_candidates[0],
            chat_id_env=telegram_config.chat_id_env_candidates[0],
            parse_mode=telegram_config.parse_mode,
        )

    def send(
        self,
        text: str,
        *,
        chat_id: str = "",
        send_reply: Callable[..., Any] | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        route = self.describe_route()
        return {
            "delivered": False,
            "route_key": route.route_key,
            "chat_id": chat_id,
            "limitation": "Telegram route Ларисы Ивановны не был передан в runtime.",
        }


class SharedTelegramRouteProvider(TelegramProvider):
    def __init__(
        self,
        *,
        env_data: Mapping[str, str] | None = None,
        config: TelegramRouteConfig = DEFAULT_CONFIG.telegram,
    ) -> None:
        if env_data is None:
            self.env_data = dict(os.environ)
        else:
            self.env_data = {str(key): str(value) for key, value in env_data.items()}
        self.config = config

    def _resolve_first_env(self, names: tuple[str, ...]) -> tuple[str | None, str]:
        for name in names:
            value = str(self.env_data.get(name) or "").strip()
            if value:
                return name, value
        return None, ""

    def _targets(self) -> dict[str, str]:
        targets: dict[str, str] = {}
        for entry in str(self.env_data.get("TELEGRAM_TARGETS") or "").split(","):
            prepared = entry.strip()
            if not prepared or "=" not in prepared:
                continue
            alias, raw_chat_id = prepared.split("=", 1)
            alias = alias.strip().lower()
            chat_id = raw_chat_id.strip()
            if alias and chat_id:
                targets[alias] = chat_id
        return targets

    def _allowed_chat_ids(self) -> set[str]:
        values = {
            item.strip()
            for item in str(self.env_data.get("TELEGRAM_ALLOWED_CHAT_IDS") or "").split(",")
            if item.strip()
        }
        _, default_chat = self._resolve_first_env(self.config.chat_id_env_candidates)
        if default_chat:
            values.add(default_chat)
        for chat_id in self._targets().values():
            values.add(chat_id)
        return values

    def _resolve_chat_id(self, explicit_chat_id: str = "") -> str:
        candidate = str(explicit_chat_id or "").strip()
        if candidate:
            return candidate

        _, env_chat_id = self._resolve_first_env(self.config.chat_id_env_candidates)
        if env_chat_id:
            return env_chat_id

        targets = self._targets()
        for alias in (self.config.route_key, self.config.route_key.replace("-", "_")):
            candidate = str(targets.get(alias.lower()) or "").strip()
            if candidate:
                return candidate
        return ""

    def _is_dry_run(self) -> bool:
        for env_name in self.config.dry_run_env_candidates:
            if str(self.env_data.get(env_name) or "").strip() == "1":
                return True
        return False

    def describe_route(self) -> TelegramRouteDescription:
        bot_env, _ = self._resolve_first_env(self.config.bot_token_env_candidates)
        chat_env, _ = self._resolve_first_env(self.config.chat_id_env_candidates)
        return TelegramRouteDescription(
            route_key=self.config.route_key,
            bot_token_env=bot_env,
            chat_id_env=chat_env or f"TELEGRAM_TARGETS:{self.config.route_key}",
            parse_mode=self.config.parse_mode,
        )

    def send(
        self,
        text: str,
        *,
        chat_id: str = "",
        send_reply: Callable[..., Any] | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        route = self.describe_route()
        target_chat_id = self._resolve_chat_id(chat_id)
        allowed_chat_ids = self._allowed_chat_ids()
        if not target_chat_id:
            return {
                "delivered": False,
                "route_key": route.route_key,
                "chat_id": "",
                "limitation": "Для маршрута Ларисы Ивановны не настроен chat_id.",
            }
        if allowed_chat_ids and target_chat_id not in allowed_chat_ids:
            return {
                "delivered": False,
                "route_key": route.route_key,
                "chat_id": target_chat_id,
                "limitation": f"Telegram chat_id {target_chat_id} не разрешен routing-конфигом.",
            }

        effective_parse_mode = parse_mode or route.parse_mode
        if send_reply is not None:
            try:
                if effective_parse_mode:
                    send_reply(target_chat_id, text, parse_mode=effective_parse_mode)
                else:
                    send_reply(target_chat_id, text)
            except TypeError:
                send_reply(target_chat_id, text)
            result = {
                "delivered": True,
                "route_key": route.route_key,
                "chat_id": target_chat_id,
                "transport": "callback",
            }
            if effective_parse_mode:
                result["parse_mode"] = effective_parse_mode
            return result

        if self._is_dry_run():
            result = {
                "delivered": False,
                "dry_run": True,
                "route_key": route.route_key,
                "chat_id": target_chat_id,
                "transport": "telegram-api",
            }
            if effective_parse_mode:
                result["parse_mode"] = effective_parse_mode
            return result

        _, bot_token = self._resolve_first_env(self.config.bot_token_env_candidates)
        if not bot_token:
            return {
                "delivered": False,
                "route_key": route.route_key,
                "chat_id": target_chat_id,
                "limitation": "Не задан TELEGRAM_BOT_TOKEN для отправки Ларисы Ивановны.",
            }

        endpoint = (
            f"{str(self.env_data.get('TELEGRAM_API_BASE_URL') or 'https://api.telegram.org').rstrip('/')}"
            f"/bot{bot_token}/sendMessage"
        )
        payload: dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if effective_parse_mode:
            payload["parse_mode"] = effective_parse_mode
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            endpoint,
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception as error:  # noqa: BLE001
            return {
                "delivered": False,
                "route_key": route.route_key,
                "chat_id": target_chat_id,
                "limitation": f"Ошибка отправки в Telegram: {error}",
            }

        if payload.get("ok") is not True:
            return {
                "delivered": False,
                "route_key": route.route_key,
                "chat_id": target_chat_id,
                "limitation": f"Telegram sendMessage failed: {payload.get('description') or 'unknown error'}",
            }

        result = {
            "delivered": True,
            "route_key": route.route_key,
            "chat_id": target_chat_id,
            "transport": "telegram-api",
        }
        if effective_parse_mode:
            result["parse_mode"] = effective_parse_mode
        return result
