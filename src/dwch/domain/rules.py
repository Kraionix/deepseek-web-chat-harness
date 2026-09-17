"""Validation predicates over domain models.

Pure functions with no side effects. Used by commands and by the
CLI to decide whether an operation is legal in the current state.
"""

from __future__ import annotations

from .models import (
    Deviation,
    DeviationType,
    FileSpec,
    PhaseKind,
    Roadmap,
    State,
)

_VALID_PHASE_KINDS = frozenset(
    {
        PhaseKind.PLANNING.value,
        PhaseKind.DEVELOPMENT.value,
        PhaseKind.UNSET.value,
    }
)


def is_step_number_valid(n: int) -> bool:
    """True when `n` is a positive integer suitable for a step number.

    Step numbers are 1-based. A step number of 0 or negative is
    always a mistake.
    """
    return n >= 1


def is_planning_phase(state: State) -> bool:
    """True when `state` belongs to a planning phase.

    A planning phase produces design artifacts and a roadmap; it
    does not execute a roadmap.
    """
    return state.phase_kind == PhaseKind.PLANNING.value


def is_development_phase(state: State) -> bool:
    """True when `state` belongs to a development phase.

    A development phase executes a frozen roadmap. If the roadmap is
    not frozen, the phase runs but no roadmap checks fire.
    """
    return state.phase_kind == PhaseKind.DEVELOPMENT.value


def is_unset_phase(state: State) -> bool:
    """True when no phase has been started yet.

    Both `current_phase` and `phase_kind` start as `"unset"` after
    `init`. Commands that require an active phase (`apply`,
    `verify`) check this predicate and refuse to run.
    """
    return state.phase_kind == PhaseKind.UNSET.value


def is_roadmap_frozen(state: State) -> bool:
    """True when the active roadmap has been frozen by `close --freeze`."""
    return state.roadmap_frozen


def can_verify_step(state: State, target: int) -> bool:
    """True when `target` is the next step in the current phase.

    Steps are sequential within a phase. Verifying a step that is
    not the immediate successor of the last verified one is a
    protocol error, not a format error.
    """
    return target == state.current_step + 1


def is_substantive(specs: list[FileSpec]) -> bool:
    """True when at least one spec is not a deviation file.

    A step that writes only `.harness/deviations/...` is a blocker
    or a declarative note; it does not advance `roadmap_step`.
    """
    for spec in specs:
        path = spec.path.replace("\\", "/")
        if not path.startswith(".harness/deviations/"):
            return True
    return False


def has_blocker(deviations: list[Deviation]) -> bool:
    """True when any deviation has type `BLOCKER`."""
    return any(d.type == DeviationType.BLOCKER for d in deviations)


def roadmap_step_valid(roadmap: Roadmap, step: int) -> bool:
    """True when `step` names an existing step in `roadmap`.

    `step` is 1-based; step 0 means "not started yet" and is always
    invalid here.
    """
    if step < 1:
        return False
    return any(s.number == step for s in roadmap.steps)


def is_state_consistent(state: State) -> bool:
    """True when the state fields are internally coherent.

    Checks that the phase name is non-empty, the step counters are
    non-negative, the roadmap version is non-negative, and the
    phase kind is one of the known values. A fuller check (state vs.
    git HEAD) happens in `health` because it needs the git port.
    """
    return (
        bool(state.current_phase)
        and state.phase_kind in _VALID_PHASE_KINDS
        and state.current_step >= 0
        and state.roadmap_step >= 0
        and state.roadmap_version >= 0
        and state.rollback_count >= 0
    )


__all__ = [
    "can_verify_step",
    "has_blocker",
    "is_development_phase",
    "is_planning_phase",
    "is_roadmap_frozen",
    "is_state_consistent",
    "is_step_number_valid",
    "is_substantive",
    "is_unset_phase",
    "roadmap_step_valid",
]
