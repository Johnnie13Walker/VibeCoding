"""Guardrails агента Ларисы Ивановны."""

from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT_CONFIG, LarisaIvanovnaConfig


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""


class LarisaIvanovnaPolicy:
    def __init__(self, config: LarisaIvanovnaConfig = DEFAULT_CONFIG) -> None:
        self.config = config

    def can_access(self, scope: str) -> PolicyDecision:
        normalized_scope = str(scope or "").strip().lower()
        if normalized_scope in self.config.blocked_scopes:
            return PolicyDecision(
                allowed=False,
                reason=f"Контур {self.config.display_name} не работает с доменом {normalized_scope}.",
            )
        if normalized_scope not in self.config.allowed_scopes:
            return PolicyDecision(
                allowed=False,
                reason=f"Домен {normalized_scope} не входит в подтвержденную зону ответственности агента.",
            )
        return PolicyDecision(allowed=True)

    def assert_allowed(self, scope: str) -> None:
        decision = self.can_access(scope)
        if not decision.allowed:
            raise PermissionError(decision.reason)
