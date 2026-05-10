"""Канонический operation_key для idempotency duplicate merge.

Формула:
    sheet=<sheet_id>|domain=<domain>|target=<target_id>|ids=<id1,id2,...>|policy=<policy_version>

POLICY_VERSION bumpается вручную при любом изменении:
- алгоритма build_policy_plan
- порогов risk
- fingerprint-схемы
- contract sheet sync
"""

from __future__ import annotations

from typing import Iterable

POLICY_VERSION = "2026.05.10"


def normalize_domain(value: str) -> str:
    text = str(value or "").strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if text.startswith("www."):
        text = text[len("www."):]
    return text.rstrip("/")


def _normalize_id(value) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() else ""


def order_deal_ids(target_id: str, deal_ids: Iterable) -> tuple[str, ...]:
    target = _normalize_id(target_id)
    others = sorted(
        {_normalize_id(item) for item in deal_ids if _normalize_id(item) and _normalize_id(item) != target},
        key=lambda item: int(item),
    )
    if not target:
        return tuple(others)
    return (target, *others)


def build_operation_key(
    *,
    sheet_id: str,
    domain: str,
    target_id: str,
    deal_ids: Iterable,
    policy_version: str = POLICY_VERSION,
) -> str:
    sheet = str(sheet_id or "").strip()
    if not sheet:
        raise ValueError("sheet_id is required")
    target = _normalize_id(target_id)
    if not target:
        raise ValueError("target_id must be a numeric id")
    normalized_inputs = {_normalize_id(item) for item in deal_ids if _normalize_id(item)}
    if target not in normalized_inputs:
        raise ValueError("target_id must be present in deal_ids")
    ordered = order_deal_ids(target, deal_ids)
    if len(ordered) < 2:
        raise ValueError("deal_ids must contain target and at least one duplicate")
    return (
        f"sheet={sheet}"
        f"|domain={normalize_domain(domain)}"
        f"|target={target}"
        f"|ids={','.join(ordered)}"
        f"|policy={str(policy_version or '').strip()}"
    )
