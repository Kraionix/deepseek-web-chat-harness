"""Validation predicates over domain models.

Pure functions with no side effects. Used by commands and by the
CLI to decide whether an operation is legal in the current state.
"""

from __future__ import annotations

from .models import (
    Deviation,
    DeviationType,
    PhaseKind,
    PhaseStatus,
    Plan,
    State,
    StepOp,
    op_paths,
)

_VALID_PHASE_KINDS = frozenset(
    {
        PhaseKind.PLANNING.value,
        PhaseKind.DEVELOPMENT.value,
        PhaseKind.UNSET.value,
    }
)

_VALID_PHASE_STATUSES = frozenset(
    {
        PhaseStatus.OPEN.value,
        PhaseStatus.CLOSED.value,
        PhaseStatus.ABANDONED.value,
    }
)

# Meta-artifacts do not count as real work when deciding whether a
# task advances the plan. Deviation files are the mechanism by which
# the coder talks back to the plan; they are not deliverables.
_NON_SUBSTANTIVE_PREFIXES = (".harness/deviations/",)

# Characters that are unsafe in a directory name on any of the
# supported platforms. Windows reserves them; POSIX would accept
# them but the user's expectation is that a phase name is a slug.
_PHASE_NAME_INVALID_CHARS = frozenset('<>:"|?*')


def is_planning_phase(state: State) -> bool:
    """True when `state` belongs to a planning phase.

    A planning phase produces a plan; it does not execute one.
    """
    return state.phase_kind == PhaseKind.PLANNING.value


def is_development_phase(state: State) -> bool:
    """True when `state` belongs to a development phase.

    A development phase executes a frozen plan. If the plan is not
    frozen, the phase runs but no plan checks fire.
    """
    return state.phase_kind == PhaseKind.DEVELOPMENT.value


def is_unset_phase(state: State) -> bool:
    """True when no phase has been started yet.

    Both `phase_name` and `phase_kind` start as `"unset"` after
    `init`. Commands that require an active phase (`apply`,
    `verify`, `next`) check this predicate and refuse to run.
    """
    return state.phase_kind == PhaseKind.UNSET.value


def is_phase_open(state: State) -> bool:
    """True when the current phase is open for work."""
    return state.phase_status == PhaseStatus.OPEN.value


def is_phase_closed(state: State) -> bool:
    """True when the current phase was finalized normally."""
    return state.phase_status == PhaseStatus.CLOSED.value


def is_phase_abandoned(state: State) -> bool:
    """True when the current phase was abandoned."""
    return state.phase_status == PhaseStatus.ABANDONED.value


def is_plan_frozen(state: State) -> bool:
    """True when the active plan has been frozen."""
    return state.plan_frozen


def is_substantive(ops: list[StepOp]) -> bool:
    """True when at least one op is real work, not a meta-artifact.

    A deviation file is a report, not a deliverable. A task that
    touches only those does not advance `plan.position`. A
    `DeleteOp` or `MoveOp` on a path outside the exempted prefixes
    is substantive: a task that only deletes a file advances the
    plan.
    """
    for op in ops:
        for path in op_paths(op):
            norm = path.replace("\\", "/")
            if norm.startswith(_NON_SUBSTANTIVE_PREFIXES):
                continue
            return True
    return False


def has_blocker(deviations: list[Deviation]) -> bool:
    """True when any deviation has type `BLOCKER`."""
    return any(d.type == DeviationType.BLOCKER for d in deviations)


def has_plan_correction(deviations: list[Deviation]) -> bool:
    """True when any deviation has type `PLAN_CORRECTION`."""
    return any(d.type == DeviationType.PLAN_CORRECTION for d in deviations)


def next_task_id(plan: Plan, position: int) -> str | None:
    """Return the id of the task at `position`, or None past the end.

    `position` is a zero-based index into `plan.tasks`.
    """
    if position < 0 or position >= len(plan.tasks):
        return None
    return plan.tasks[position].id


def phase_name_error(name: str) -> str | None:
    """Return an error message if `name` is not a safe directory name.

    A phase name becomes a directory under `steps/`, so it must not
    contain path separators, parent references, characters that are
    illegal on Windows, or any control character.
    """
    if not name:
        return "phase name must be non-empty"
    if name != name.strip():
        return "phase name must not have leading or trailing whitespace"
    for ch in name:
        if ch.isspace() and ch != " ":
            return "phase name must not contain tabs or newlines"
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            return "phase name must not contain control characters"
    if " " in name:
        return "phase name must not contain spaces"
    if "/" in name or "\\" in name:
        return "phase name must not contain path separators"
    if name in {".", ".."}:
        return "phase name must not be '.' or '..'"
    bad = sorted(set(name) & _PHASE_NAME_INVALID_CHARS)
    if bad:
        joined = " ".join(repr(c) for c in bad)
        return f"phase name contains invalid characters: {joined}"
    return None


def is_state_consistent(state: State) -> bool:
    """True when the state fields are internally coherent.

    Checks that the phase name is non-empty, the counters are
    non-negative, and the enums are known. A fuller check
    (state vs. git HEAD) happens in `health` because it needs the
    git port.
    """
    return (
        bool(state.phase_name)
        and state.phase_kind in _VALID_PHASE_KINDS
        and state.phase_status in _VALID_PHASE_STATUSES
        and state.plan_version >= 0
        and state.plan_position >= 0
        and state.failure_count >= 0
        and state.rollback_count >= 0
    )


__all__ = [
    "has_blocker",
    "has_plan_correction",
    "is_development_phase",
    "is_phase_abandoned",
    "is_phase_closed",
    "is_phase_open",
    "is_plan_frozen",
    "is_planning_phase",
    "is_state_consistent",
    "is_substantive",
    "is_unset_phase",
    "next_task_id",
    "phase_name_error",
]
