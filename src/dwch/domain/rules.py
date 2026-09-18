"""Validation predicates over domain models.

Pure functions with no side effects. Used by commands and by the
CLI to decide whether an operation is legal in the current state.
"""

from __future__ import annotations

from .models import (
    Deviation,
    DeviationType,
    PhaseKind,
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

# Meta-artifacts do not count as real work when deciding whether a
# step advances the roadmap. Handoffs and summaries are written by
# the AI, but they are process files, not deliverables.
_NON_SUBSTANTIVE_PREFIXES = (
    ".harness/deviations/",
    ".harness/summaries/",
)
_NON_SUBSTANTIVE_EXACT = (".harness/handoff.md",)

# Characters that are unsafe in a directory name on any of the
# supported platforms. Windows reserves them; POSIX would accept
# them but the user's expectation is that a phase name is a slug.
_PHASE_NAME_INVALID_CHARS = frozenset('<>:"|?*')


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


def is_substantive(ops: list[StepOp]) -> bool:
    """True when at least one op is real work, not a meta-artifact.

    Deviation files, phase summaries, and handoff rewrites are
    process artifacts. A step that touches only those does not
    advance `roadmap_step`: it reports, blocks, or reorganizes, but
    it does not deliver.

    A `DeleteOp` or `MoveOp` with a path outside the exempted
    prefixes is substantive: a step that only deletes a file
    advances the roadmap.
    """
    for op in ops:
        for path in op_paths(op):
            norm = path.replace("\\", "/")
            if norm in _NON_SUBSTANTIVE_EXACT:
                continue
            if norm.startswith(_NON_SUBSTANTIVE_PREFIXES):
                continue
            return True
    return False


def has_blocker(deviations: list[Deviation]) -> bool:
    """True when any deviation has type `BLOCKER`."""
    return any(d.type == DeviationType.BLOCKER for d in deviations)


def phase_name_error(name: str) -> str | None:
    """Return an error message if `name` is not a safe directory name.

    A phase name becomes a directory under `steps/`, so it must not
    contain path separators, parent references, characters that are
    illegal on Windows, or any control character. The last rule is
    stricter than `str.strip()` and `" " in name`: a name such as
    `"a\\nb"` would create a directory with an embedded newline and
    corrupt `.harness/handoff.md` and `.harness/state.toml`.
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
    "phase_name_error",
]
