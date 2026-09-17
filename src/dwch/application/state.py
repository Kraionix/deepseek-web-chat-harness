"""Load and save `.harness/state.toml`.

State is written by the harness. Save operations are atomic: the
new content is written to a temp file and then renamed over the
original, so a crash mid-write leaves the file either fully old or
fully new, never partially written.
"""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from pathlib import Path

from ..domain.models import State
from ..shared.errors import StateError
from .ports import FilesystemPort

_HARNESS_VERSION = "0.1.0"


def load_state(fs: FilesystemPort, project_root: Path) -> State:
    """Read `.harness/state.toml`.

    Preconditions: `project_root` is a directory; the harness has
    been initialized.
    Postconditions: a `State` with every field populated.

    Raises `StateError` on missing file or malformed content.
    """
    path = _state_path(project_root)
    if not fs.exists(path):
        raise StateError(f"state not found: {path}. Run `dwch init` first.")
    try:
        data = tomllib.loads(fs.read_text(path))
    except tomllib.TOMLDecodeError as exc:
        raise StateError(f"invalid TOML in {path}: {exc}") from exc

    phase = data.get("phase", {})
    step = data.get("step", {})
    session = data.get("session", {})

    return State(
        harness_version=str(data.get("harness", {}).get("version", _HARNESS_VERSION)),
        current_phase=str(phase.get("current", "unset")),
        current_step=int(step.get("current", 0)),
        total_steps=int(step.get("total", 0)),
        last_commit=str(step.get("last_commit", "")),
        last_commit_date=str(step.get("last_commit_date", "")),
        last_opened=str(session.get("last_opened", "")),
        last_closed=str(session.get("last_closed", "")),
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
    now = datetime.now(UTC).isoformat(timespec="seconds")
    return State(
        harness_version=_HARNESS_VERSION,
        current_phase="unset",
        current_step=0,
        total_steps=0,
        last_commit="",
        last_commit_date="",
        last_opened=now,
        last_closed="",
    )


def touch_opened(fs: FilesystemPort, project_root: Path, state: State) -> State:
    """Return `state` with `last_opened` refreshed to now."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    updated = State(
        harness_version=state.harness_version,
        current_phase=state.current_phase,
        current_step=state.current_step,
        total_steps=state.total_steps,
        last_commit=state.last_commit,
        last_commit_date=state.last_commit_date,
        last_opened=now,
        last_closed=state.last_closed,
    )
    save_state(fs, project_root, updated)
    return updated


def _state_path(project_root: Path) -> Path:
    return project_root / ".harness" / "state.toml"


def _render_state(state: State) -> str:
    """Render `State` as a TOML document.

    Hand-written: stdlib has no TOML writer. The format is
    deliberately flat — no nested tables — so a small renderer is
    sufficient.
    """
    lines = [
        "[harness]",
        f'version = "{state.harness_version}"',
        "",
        "[phase]",
        f'current = "{state.current_phase}"',
        "",
        "[step]",
        f"current = {state.current_step}",
        f"total = {state.total_steps}",
        f'last_commit = "{state.last_commit}"',
        f'last_commit_date = "{state.last_commit_date}"',
        "",
        "[session]",
        f'last_opened = "{state.last_opened}"',
        f'last_closed = "{state.last_closed}"',
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "initial_state",
    "load_state",
    "save_state",
    "touch_opened",
]
