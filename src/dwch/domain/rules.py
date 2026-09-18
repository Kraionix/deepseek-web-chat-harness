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
    State,
)

_VALID_PHASE_KINDS = frozenset(
    {
        PhaseKind.PLANNING.value,
        PhaseKind.DEVELOPMENT.value,
        PhaseKind.UNSET.value,
    }
)

# Meta-artifacts do not count as real work when deciding whether a
# step advances the roadmap. Handoffs and summaries are written by
# the AI, but they are process files, not deliverables.
_NON_SUBSTANTIVE_PREFIXES = (
    ".harness/deviations/",
    ".harness/summaries/",
)
_NON_SUBSTANTIVE_EXACT = (".harness/handoff.md",)


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
    """True when the active roadmap has been frozen by `close --freeze`.

    A frozen roadmap has a lock file and drives the roadmap checks
    in `verify`. An unfrozen one does not.
    """
    return state.roadmap_frozen


def is_phase_closed(state: State) -> bool:
    """True when the current phase has already been closed.

    A phase is closed when `last_closed` is set and is not older
    than `last_opened`. Both timestamps use the same ISO format, so
    a lexicographic comparison is equivalent to a chronological one.
    """
    if not state.last_closed:
        return False
    return state.last_closed >= state.last_opened


def is_substantive(specs: list[FileSpec]) -> bool:
    """True when at least one spec is real work, not a meta-artifact.

    Deviation files, phase summaries, and handoff rewrites are
    process artifacts. A step that touches only those does not
    advance `roadmap_step`: it reports, blocks, or reorganizes, but
    it does not deliver.
    """
    for spec in specs:
        path = spec.path.replace("\\", "/")
        if path in _NON_SUBSTANTIVE_EXACT:
            continue
        if path.startswith(_NON_SUBSTANTIVE_PREFIXES):
            continue
        return True
    return False


def has_blocker(deviations: list[Deviation]) -> bool:
    """True when any deviation has type `BLOCKER`."""
    return any(d.type == DeviationType.BLOCKER for d in deviations)


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
    "has_blocker",
    "is_development_phase",
    "is_phase_closed",
    "is_planning_phase",
    "is_roadmap_frozen",
    "is_state_consistent",
    "is_substantive",
    "is_unset_phase",
]
