"""Load and save `.harness/state.toml`.

State is written by the harness. Save operations are atomic: the
new content is written to a temp file and then renamed over the
original, so a crash mid-write leaves the file either fully old or
fully new, never partially written.

All `set_*` helpers are pure: they return a new `State` and do not
touch disk. The caller decides when to persist.
"""

from __future__ import annotations

import tomllib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ..domain.models import State
from ..shared.errors import StateError
from ..shared.toml import escape_basic_string
from .ports import FilesystemPort

_STATE_FORMAT_VERSION = "0.4.0"

# Invariant: every timestamp the harness records uses microsecond
# precision. A rapid close-then-start pair must remain
# distinguishable.
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
    plan = data.get("plan", {})
    verify = data.get("verify", {})
    failure = data.get("failure", {})
    rollback = data.get("rollback", {})
    session = data.get("session", {})

    return State(
        harness_version=version,
        phase_name=str(phase.get("name", "unset")),
        phase_kind=str(phase.get("kind", "unset")),
        phase_status=str(phase.get("status", "closed")),
        phase_opened_at=str(phase.get("opened_at", "")),
        phase_closed_at=str(phase.get("closed_at", "")),
        plan_version=int(plan.get("version", 0)),
        plan_sha256=str(plan.get("sha256", "")),
        plan_position=int(plan.get("position", 0)),
        plan_frozen=bool(plan.get("frozen", False)),
        verify_ok=bool(verify.get("ok", False)),
        verify_task_id=str(verify.get("task_id", "")),
        verify_at=str(verify.get("at", "")),
        failure_task_id=str(failure.get("task_id", "")),
        failure_check_name=str(failure.get("check_name", "")),
        failure_excerpt=str(failure.get("excerpt", "")),
        failure_count=int(failure.get("count", 0)),
        rollback_count=int(rollback.get("count", 0)),
        last_commit=str(session.get("last_commit", "")),
        last_commit_date=str(session.get("last_commit_date", "")),
    )


def save_state(fs: FilesystemPort, project_root: Path, state: State) -> None:
    """Write `.harness/state.toml` atomically.

    The file is written to `state.toml.tmp` and then renamed over
    the destination. A crash between `write_text` and `rename`
    leaves the destination untouched and a stray `.tmp` file behind,
    which is harmless and overwritten on the next save.
    """
    path = _state_path(project_root)
    tmp = path.with_suffix(".toml.tmp")
    fs.write_text(tmp, _render_state(state))
    fs.rename(tmp, path)


def initial_state() -> State:
    """Return a fresh `State` for a newly-initialized project.

    Phase is `unset` (kind) with status `closed`: no work is active
    until `start` opens one.
    """
    return State(
        harness_version=_STATE_FORMAT_VERSION,
        phase_name="unset",
        phase_kind="unset",
        phase_status="closed",
        phase_opened_at=now_iso(),
        phase_closed_at="",
        plan_version=0,
        plan_sha256="",
        plan_position=0,
        plan_frozen=False,
        verify_ok=False,
        verify_task_id="",
        verify_at="",
        failure_task_id="",
        failure_check_name="",
        failure_excerpt="",
        failure_count=0,
        rollback_count=0,
        last_commit="",
        last_commit_date="",
    )


def set_phase_open(state: State, name: str, kind: str, at: str) -> State:
    """Return `state` with a fresh phase opened.

    Resets `phase_closed_at`. Does not touch the plan fields: the
    caller decides whether to reset the plan position.
    """
    return replace(
        state,
        phase_name=name,
        phase_kind=kind,
        phase_status="open",
        phase_opened_at=at,
        phase_closed_at="",
    )


def set_phase_closed(state: State, at: str) -> State:
    """Return `state` with the phase closed normally."""
    return replace(state, phase_status="closed", phase_closed_at=at)


def set_phase_abandoned(state: State, at: str) -> State:
    """Return `state` with the phase abandoned.

    Files stay on disk including a frozen plan. The next phase does
    not inherit anything from an abandoned one.
    """
    return replace(state, phase_status="abandoned", phase_closed_at=at)


def set_verify_ok(state: State, task_id: str, at: str) -> State:
    """Return `state` with a successful verify recorded.

    Clears failure fields: a success resets the consecutive-failure
    counter for the task.
    """
    return replace(
        state,
        verify_ok=True,
        verify_task_id=task_id,
        verify_at=at,
        failure_task_id="",
        failure_check_name="",
        failure_excerpt="",
        failure_count=0,
    )


def set_verify_fail(
    state: State,
    task_id: str,
    check_name: str,
    excerpt: str,
    at: str,
) -> State:
    """Return `state` with a failed verify recorded.

    The consecutive-failure counter increments when the failed task
    is the same as the previous failure's task; otherwise it resets
    to 1. The counter is what drives the fix-loop warning.
    """
    count = state.failure_count + 1 if state.failure_task_id == task_id else 1
    return replace(
        state,
        verify_ok=False,
        verify_task_id=task_id,
        verify_at=at,
        failure_task_id=task_id,
        failure_check_name=check_name,
        failure_excerpt=excerpt,
        failure_count=count,
    )


def reset_failure(state: State) -> State:
    """Return `state` with failure fields cleared."""
    return replace(
        state,
        failure_task_id="",
        failure_check_name="",
        failure_excerpt="",
        failure_count=0,
    )


def set_plan_frozen(state: State, version: int, sha256: str) -> State:
    """Return `state` with the plan frozen at `version`/`sha256`.

    Resets `plan_position` to zero: a frozen plan is a new contract
    with its own task ordering.
    """
    return replace(
        state,
        plan_version=version,
        plan_sha256=sha256,
        plan_frozen=True,
        plan_position=0,
    )


def advance_position(state: State) -> State:
    """Return `state` with `plan_position` incremented by one."""
    return replace(state, plan_position=state.plan_position + 1)


def reset_position(state: State) -> State:
    """Return `state` with `plan_position` reset to zero."""
    return replace(state, plan_position=0)


def increment_rollback(state: State) -> State:
    """Return `state` with `rollback_count` incremented by one."""
    return replace(state, rollback_count=state.rollback_count + 1)


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

    Hand-written: stdlib has no TOML writer. Every string value is
    escaped uniformly; the harness's own values never need it, but
    a `failure.excerpt` can contain anything, and the cost of
    uniform escaping is nil.
    """
    frozen = "true" if state.plan_frozen else "false"
    verify_ok = "true" if state.verify_ok else "false"
    lines = [
        "[harness]",
        f'version = "{escape_basic_string(state.harness_version)}"',
        "",
        "[phase]",
        f'name = "{escape_basic_string(state.phase_name)}"',
        f'kind = "{escape_basic_string(state.phase_kind)}"',
        f'status = "{escape_basic_string(state.phase_status)}"',
        f'opened_at = "{escape_basic_string(state.phase_opened_at)}"',
        f'closed_at = "{escape_basic_string(state.phase_closed_at)}"',
        "",
        "[plan]",
        f"version = {state.plan_version}",
        f'sha256 = "{escape_basic_string(state.plan_sha256)}"',
        f"position = {state.plan_position}",
        f"frozen = {frozen}",
        "",
        "[verify]",
        f"ok = {verify_ok}",
        f'task_id = "{escape_basic_string(state.verify_task_id)}"',
        f'at = "{escape_basic_string(state.verify_at)}"',
        "",
        "[failure]",
        f'task_id = "{escape_basic_string(state.failure_task_id)}"',
        f'check_name = "{escape_basic_string(state.failure_check_name)}"',
        f'excerpt = "{escape_basic_string(state.failure_excerpt)}"',
        f"count = {state.failure_count}",
        "",
        "[rollback]",
        f"count = {state.rollback_count}",
        "",
        "[session]",
        f'last_commit = "{escape_basic_string(state.last_commit)}"',
        f'last_commit_date = "{escape_basic_string(state.last_commit_date)}"',
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "TIMESTAMP_TIMESPEC",
    "advance_position",
    "increment_rollback",
    "initial_state",
    "load_state",
    "now_iso",
    "reset_failure",
    "reset_position",
    "save_state",
    "set_phase_abandoned",
    "set_phase_closed",
    "set_phase_open",
    "set_plan_frozen",
    "set_verify_fail",
    "set_verify_ok",
    "with_updates",
]
