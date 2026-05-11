from __future__ import annotations

import pytest

from crm_company_merge.state import (
    TRANSITIONS,
    InvalidStateTransition,
    Status,
    can_transition,
    require_transition,
)


def test_all_valid_transitions_allowed() -> None:
    for from_, targets in TRANSITIONS.items():
        for to in targets:
            assert can_transition(from_, to)
            require_transition(from_, to)


@pytest.mark.parametrize(
    ("from_", "to"),
    [
        (Status.NEW, Status.MERGED),
        (Status.DONE, Status.NEW),
        (Status.ROLLED_BACK, Status.NEW),
        (Status.TRANSFERRED, Status.APPROVED),
    ],
)
def test_invalid_transition_raises(from_: Status, to: Status) -> None:
    assert not can_transition(from_, to)
    with pytest.raises(InvalidStateTransition):
        require_transition(from_, to)


def test_terminal_states_have_no_outgoing() -> None:
    assert TRANSITIONS[Status.DONE] == set()
    assert TRANSITIONS[Status.ROLLED_BACK] == set()
