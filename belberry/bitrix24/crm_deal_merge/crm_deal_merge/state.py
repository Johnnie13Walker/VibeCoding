from __future__ import annotations

from enum import Enum


class Status(str, Enum):
    NEW = "NEW"
    INVENTORIED = "INVENTORIED"
    PLAN_READY = "PLAN_READY"
    APPROVED = "APPROVED"
    MANUAL = "MANUAL"
    TRANSFERRED = "TRANSFERRED"
    MERGED = "MERGED"
    VERIFIED = "VERIFIED"
    DONE = "DONE"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


TRANSITIONS: dict[Status, set[Status]] = {
    Status.NEW: {Status.INVENTORIED, Status.FAILED},
    Status.INVENTORIED: {Status.PLAN_READY, Status.FAILED},
    Status.PLAN_READY: {Status.APPROVED, Status.MANUAL, Status.FAILED},
    Status.APPROVED: {Status.TRANSFERRED, Status.FAILED},
    Status.MANUAL: {Status.DONE, Status.FAILED},
    Status.TRANSFERRED: {Status.MERGED, Status.FAILED},
    Status.MERGED: {Status.VERIFIED, Status.FAILED},
    Status.VERIFIED: {Status.DONE, Status.FAILED},
    Status.DONE: set(),
    Status.FAILED: {Status.ROLLED_BACK, Status.NEW},
    Status.ROLLED_BACK: set(),
}


class InvalidStateTransition(ValueError):
    """Недопустимый переход статуса очереди merge."""


def can_transition(from_: Status, to: Status) -> bool:
    return to in TRANSITIONS[from_]


def require_transition(from_: Status, to: Status) -> None:
    if not can_transition(from_, to):
        raise InvalidStateTransition(f"Недопустимый переход статуса: {from_.value} -> {to.value}")
