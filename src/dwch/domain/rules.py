"""Validation predicates over domain models.

Pure functions with no side effects. Used by commands and by the
CLI to decide whether an operation is legal in the current state.
"""

from __future__ import annotations

from .models import Phase, PhaseStatus, State, StepStatus


def is_step_number_valid(n: int) -> bool:
    """True when `n` is a positive integer suitable for a step number.

    Step numbers are 1-based. A step number of 0 or negative is
    always a mistake.
    """
    return n >= 1


def can_apply_step(current: int, target: int) -> bool:
    """True when the pipeline can move from `current` to `target`.

    Rules: the next step must be exactly one greater than the
    current step (0 means "no steps yet"). Applying a step out of
    order is not allowed — the state would lose track of which
    steps were skipped.
    """
    return target == current + 1


def can_verify_step(current: int, target: int) -> bool:
    """True when `target` is the step currently being processed.

    You cannot verify a step that was not the last one applied.
    """
    return target == current


def is_phase_complete(phase: Phase) -> bool:
    """True when every step in the phase reached a terminal state.

    A phase is complete when no step is `PENDING` or `APPLIED`.
    `FAILED` and `ROLLED_BACK` steps are considered terminal: the
    user decided what to do with them.
    """
    if phase.status is PhaseStatus.COMPLETED:
        return True
    return all(
        step.status in (StepStatus.VERIFIED, StepStatus.FAILED, StepStatus.ROLLED_BACK)
        for step in phase.steps
    )


def is_state_consistent(state: State) -> bool:
    """True when the state fields are internally coherent.

    Checks that the phase name is non-empty and that the step
    number is not negative. A fuller check (state vs. git HEAD)
    happens in `health` because it needs the git port.
    """
    return bool(state.current_phase) and state.current_step >= 0


__all__ = [
    "can_apply_step",
    "can_verify_step",
    "is_phase_complete",
    "is_state_consistent",
    "is_step_number_valid",
]
