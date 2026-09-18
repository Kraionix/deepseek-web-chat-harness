"""Load and save `.harness/state.toml`.

State is written by the harness. Save operations are atomic: the
new content is written to a temp file and then renamed over the
original, so a crash mid-write leaves the file either fully old or
fully new, never partially written.
"""

from __future__ import annotations

import tomllib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ..domain.models import State
from ..shared.errors import StateError
from .ports import FilesystemPort

# Version of the state file format. Independent of the package
# version: a patch release that does not change the format keeps
# this value, and existing `.harness/state.toml` files keep working.
#
# 0.3.0 adds a `[summary]` section and rejects any file whose
# `[harness].version` does not match. Backward compatibility is not
# preserved.
_STATE_FORMAT_VERSION = "0.3.0"

# Invariant: every timestamp the harness records uses microsecond
# precision. `is_phase_closed` compares `last_closed` and
# `last_opened` as strings, so two lifecycle events landing in the
# same wall-clock second must still be distinguishable. Second
# resolution is not enough: `close` followed immediately by
# `new-phase` collides.
#
# Public so that every command calls `now_iso()` rather than
# re-importing the constant. Drift between commands is the class of
# bug the constant exists to prevent.
TIMESTAMP_TIMESPEC = "microseconds"


def now_iso() -> str:
    """Return the current UTC time as an ISO string.

    Every lifecycle timestamp the harness writes goes through this
    function, so the format is uniform and `TIMESTAMP_TIMESPEC` is
    applied in one place.
    """
    return datetime.now(UTC).isoformat(timespec=TIMESTAMP_TIMESPEC)


def load_state(fs: FilesystemPort, project_root: Path) -> State:
    """Read `.harness/state.toml`.

    Pre:  `project_root` is a directory; the harness has been
          initialized.
    Post: returns a `State` with every field populated. Missing
          optional sections fall back to defaults.
    Raises: `StateError` on missing file, malformed content, or a
          file written by an incompatible harness version.
    """
    path = _state_path(project_root)
    if not fs.exists(path):
        raise StateError(f"state not found: {path}. Run `dwch init` first.")
    try:
        data = tomllib.loads(fs.read_text(path))
    except tomllib.TOMLDecodeError as exc:
        raise StateError(f"invalid TOML in {path}: {exc}") from exc

    harness = data.get("harness", {})
    version = str(harness.get("version", ""))
    if version != _STATE_FORMAT_VERSION:
        raise StateError(
            f"state version {version!r} does not match harness "
            f"version {_STATE_FORMAT_VERSION!r}. Run `dwch init --force` "
            "or delete `.harness/state.toml` and re-initialize."
        )

    phase = data.get("phase", {})
    step = data.get("step", {})
    roadmap = data.get("roadmap", {})
    rollback = data.get("rollback", {})
    session = data.get("session", {})
    summary = data.get("summary", {})

    return State(
        harness_version=version,
        current_phase=str(phase.get("current", "unset")),
        phase_kind=str(phase.get("kind", "unset")),
        current_step=int(step.get("current", 0)),
        last_commit=str(step.get("last_commit", "")),
        last_commit_date=str(step.get("last_commit_date", "")),
        roadmap_version=int(roadmap.get("version", 0)),
        roadmap_step=int(roadmap.get("step", 0)),
        roadmap_frozen=bool(roadmap.get("frozen", False)),
        rollback_count=int(rollback.get("count", 0)),
        last_opened=str(session.get("last_opened", "")),
        last_closed=str(session.get("last_closed", "")),
        summary_phase=str(summary.get("phase", "")),
        summary_written_at=str(summary.get("written_at", "")),
    )


def save_state(fs: FilesystemPort, project_root: Path, state: State) -> None:
    """Write `.harness/state.toml` atomically.

    The file is written to `state.toml.tmp` and then renamed over
    the destination. Both operations go through the filesystem port
    so that alternate implementations (in-memory for tests) behave
    the same way.

    The rename is atomic: a concurrent reader sees either the old
    state or the new state, never a truncated file. A crash between
    `write_text` and `rename` leaves the destination untouched and
    a stray `.tmp` file behind, which is harmless and overwritten on
    the next save.
    """
    path = _state_path(project_root)
    tmp = path.with_suffix(".toml.tmp")
    fs.write_text(tmp, _render_state(state))
    fs.rename(tmp, path)


def initial_state() -> State:
    """Return a fresh `State` for a newly-initialized project."""
    return State(
        harness_version=_STATE_FORMAT_VERSION,
        current_phase="unset",
        phase_kind="unset",
        current_step=0,
        last_commit="",
        last_commit_date="",
        roadmap_version=0,
        roadmap_step=0,
        roadmap_frozen=False,
        rollback_count=0,
        last_opened=now_iso(),
        last_closed="",
        summary_phase="",
        summary_written_at="",
    )


def set_roadmap_frozen(
    fs: FilesystemPort,
    project_root: Path,
    state: State,
    *,
    version: int,
) -> State:
    """Return `state` marked frozen for roadmap `version` and persisted.

    `roadmap_step` is reset to zero: a new roadmap version has its
    own step numbering, starting from 1.
    """
    updated = replace(
        state,
        roadmap_frozen=True,
        roadmap_version=version,
        roadmap_step=0,
    )
    save_state(fs, project_root, updated)
    return updated


def with_updates(state: State, **kwargs) -> State:
    """Return a copy of `state` with the given fields replaced.

    Pre:  every key in `kwargs` is a field name of `State`.
    Post: a new frozen `State`; the original is unchanged.
    """
    return replace(state, **kwargs)


def _state_path(project_root: Path) -> Path:
    return project_root / ".harness" / "state.toml"


def _render_state(state: State) -> str:
    """Render `State` as a TOML document.

    Hand-written: stdlib has no TOML writer. The format is
    deliberately flat — no nested tables — so a small renderer is
    sufficient.
    """
    frozen = "true" if state.roadmap_frozen else "false"
    lines = [
        "[harness]",
        f'version = "{state.harness_version}"',
        "",
        "[phase]",
        f'current = "{state.current_phase}"',
        f'kind = "{state.phase_kind}"',
        "",
        "[step]",
        f"current = {state.current_step}",
        f'last_commit = "{state.last_commit}"',
        f'last_commit_date = "{state.last_commit_date}"',
        "",
        "[roadmap]",
        f"version = {state.roadmap_version}",
        f"step = {state.roadmap_step}",
        f"frozen = {frozen}",
        "",
        "[rollback]",
        f"count = {state.rollback_count}",
        "",
        "[session]",
        f'last_opened = "{state.last_opened}"',
        f'last_closed = "{state.last_closed}"',
        "",
        "[summary]",
        f'phase = "{state.summary_phase}"',
        f'written_at = "{state.summary_written_at}"',
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "TIMESTAMP_TIMESPEC",
    "initial_state",
    "load_state",
    "now_iso",
    "save_state",
    "set_roadmap_frozen",
    "with_updates",
]
