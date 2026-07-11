#!/usr/bin/env python3
"""Spec state machine — enforces legal transitions (OR-R2).

States:
    draft → ready → in_progress → implemented → merged
                                         ↘ failed_red / failed_green / failed_e2e
"""

from halo.common.models import (
    SPEC_STATUS_DRAFT, SPEC_STATUS_READY, SPEC_STATUS_IN_PROGRESS,
    SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED,
    SPEC_STATUS_FAILED_RED, SPEC_STATUS_FAILED_GREEN, SPEC_STATUS_FAILED_E2E,
)


TRANSITIONS = {
    SPEC_STATUS_DRAFT: [SPEC_STATUS_READY],
    SPEC_STATUS_READY: [SPEC_STATUS_IN_PROGRESS],
    SPEC_STATUS_IN_PROGRESS: [SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_FAILED_RED, SPEC_STATUS_FAILED_GREEN, SPEC_STATUS_FAILED_E2E],
    SPEC_STATUS_IMPLEMENTED: [SPEC_STATUS_MERGED, SPEC_STATUS_DRAFT, SPEC_STATUS_FAILED_RED, SPEC_STATUS_FAILED_GREEN],
    SPEC_STATUS_MERGED: [],
    SPEC_STATUS_FAILED_RED: [SPEC_STATUS_DRAFT, SPEC_STATUS_READY],
    SPEC_STATUS_FAILED_GREEN: [SPEC_STATUS_DRAFT, SPEC_STATUS_READY],
    SPEC_STATUS_FAILED_E2E: [SPEC_STATUS_DRAFT, SPEC_STATUS_READY],
}

COMMIT_PREFIXES = {
    (SPEC_STATUS_READY, SPEC_STATUS_IN_PROGRESS): "agent: start",
    (SPEC_STATUS_IN_PROGRESS, SPEC_STATUS_IMPLEMENTED): "agent: implement",
    (SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED): "human: approve",
    (SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_DRAFT): "human: reject",
}


class InvalidTransitionError(Exception):
    pass


def can_transition(from_status, to_status):
    """Check if a transition is legal."""
    return to_status in TRANSITIONS.get(from_status, [])


def transition(from_status, to_status):
    """Validate and perform a state transition. Returns (new_status, commit_prefix)."""
    if not can_transition(from_status, to_status):
        raise InvalidTransitionError(
            f"Illegal transition: {from_status} → {to_status}"
        )
    prefix = COMMIT_PREFIXES.get((from_status, to_status), "")
    return to_status, prefix


def get_legal_transitions(status):
    """Return all legal target states from the given status."""
    return TRANSITIONS.get(status, [])


def is_terminal(status):
    """Check if a status is terminal (no further transitions)."""
    return len(TRANSITIONS.get(status, [])) == 0


def is_failed(status):
    """Check if a status is a failure state."""
    return status in (SPEC_STATUS_FAILED_RED, SPEC_STATUS_FAILED_GREEN, SPEC_STATUS_FAILED_E2E)