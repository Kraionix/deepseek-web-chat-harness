"""`dwch new-phase NAME` — begin a new phase.

Two kinds of phase exist: `planning` and `development`. Each has
its own handoff template. The phase kind is stored in `state.toml`
and drives the bootstrap and verify behaviour.

A development phase inherits its starting step from the active
roadmap: `current_step` is set to `state.roadmap_step`, so the
phase continues numbering where the previous phase stopped. A
planning phase resets `current_step` to zero.

Refuses to start a development phase when the roadmap is exhausted
(`roadmap_step >= len(steps)`). At that point the correct action is
a new planning phase that produces a new roadmap version.

The transition commits the whole tree via `commit_all`, so untracked
files are expected and do not count as dirt. Only modifications to
already-tracked files block the command. This lets the very first
phase be started right after `dwch init`, when `.harness/` and
`steps/` are still untracked.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from datetime import UTC, datetime
from importlib.resources import files

from ...shared.errors import HarnessError
from .. import roadmap as roadmap_mod
from ..config import load_config
from ..deps import Deps
from ..handoff import update_metadata
from ..rules import is_roadmap_frozen
from ..state import load_state, save_state, with_updates

# Characters that are unsafe in a directory name on any of the
# supported platforms: Windows reserves them, POSIX would accept
# them but the user's expectation is that a phase name is a slug.
_INVALID_NAME_CHARS = frozenset('<>:"|?*')


def cmd_new_phase(args: Namespace, deps: Deps) -> int:
    """Start a new phase. Returns 0 on success, 2 on error."""
    try:
        config = load_config(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not deps.git.is_clean_tracked(deps.project_root):
        print(
            "error: working tree has uncommitted tracked changes; "
            "commit or stash before starting a new phase",
            file=sys.stderr,
        )
        return 2

    name = args.name
    err = _validate_phase_name(name)
    if err is not None:
        print(f"error: {err}", file=sys.stderr)
        return 2

    kind = args.kind
    state = load_state(deps.fs, deps.project_root)

    if kind == "planning" and is_roadmap_frozen(state):
        print(
            "warning: a new roadmap version will replace the current frozen one",
            file=sys.stderr,
        )

    # `_resolve_start_step` raises on a missing or exhausted
    # roadmap. The command owns the conversion from exception to
    # exit code: the CLI's generic handler is a fallback, not the
    # primary contract.
    try:
        start_step = _resolve_start_step(deps, config, state, kind)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if kind == "development" and start_step == 0 and not is_roadmap_frozen(state):
        print(
            "warning: starting a development phase with no frozen roadmap; "
            "roadmap checks will be skipped",
            file=sys.stderr,
        )

    now = datetime.now(UTC).isoformat(timespec="seconds")
    head = deps.git.try_head(deps.project_root)

    _reset_handoff(deps, name, kind)

    updated = with_updates(
        state,
        current_phase=name,
        phase_kind=kind,
        current_step=start_step,
        last_commit=head,
        last_commit_date=now,
        last_opened=now,
    )
    save_state(deps.fs, deps.project_root, updated)
    update_metadata(deps.fs, deps.project_root, updated)

    try:
        commit = deps.git.commit_all(
            deps.project_root, f"chore: start {kind} phase {name}"
        )
    except HarnessError as exc:
        print(f"warning: could not commit new phase: {exc}", file=sys.stderr)
        commit = head

    print(f"new phase: {name} ({kind})")
    if commit and commit != head:
        print(f"commit: {commit}")
    if kind == "development" and start_step > 0:
        print(f"resuming at roadmap step {start_step + 1}")
    print("next: `dwch bootstrap --clipboard`")
    return 0


def _resolve_start_step(deps: Deps, config, state, kind: str) -> int:
    """Return the starting `current_step` for a new phase.

    A planning phase always starts at zero. A development phase
    resumes at `state.roadmap_step` when a roadmap is frozen and
    has remaining steps; it starts at zero when no roadmap exists.

    Pre:  `state` is the current, loaded state.
    Post: a non-negative int.
    Raises: `HarnessError` when the frozen roadmap is missing or
          has no remaining steps.
    """
    if kind != "development":
        return 0
    if not is_roadmap_frozen(state):
        return 0

    roadmap_path = deps.project_root / config.roadmap.get(
        "path", ".harness/roadmap.toml"
    )
    if not deps.fs.exists(roadmap_path):
        raise HarnessError(
            f"roadmap not found at {roadmap_path}, but state says frozen"
        )

    roadmap = roadmap_mod.load(deps.fs, roadmap_path)

    if state.roadmap_step >= len(roadmap.steps):
        raise HarnessError(
            "roadmap is complete; there are no more steps. "
            "Start a planning phase to write a new roadmap version."
        )

    return state.roadmap_step


def _validate_phase_name(name: str) -> str | None:
    """Return an error message when `name` is not a safe directory name.

    A phase name becomes a directory under `steps/`, so it must not
    contain path separators, parent references, or characters that
    are illegal on Windows.
    """
    if not name:
        return "phase name must be non-empty"
    if name != name.strip():
        return "phase name must not have leading or trailing whitespace"
    if " " in name:
        return "phase name must not contain spaces"
    if "/" in name or "\\" in name:
        return "phase name must not contain path separators"
    if name in {".", ".."}:
        return "phase name must not be '.' or '..'"
    bad = sorted(set(name) & _INVALID_NAME_CHARS)
    if bad:
        joined = " ".join(repr(c) for c in bad)
        return f"phase name contains invalid characters: {joined}"
    return None


def _reset_handoff(deps: Deps, name: str, kind: str) -> None:
    """Write `.harness/handoff.md` from the phase-kind template."""
    template_name = (
        "planning-handoff.md" if kind == "planning" else "development-handoff.md"
    )
    template = files("dwch.templates") / template_name
    body = template.read_text(encoding="utf-8").replace("{{phase}}", name)
    deps.fs.write_text(deps.project_root / ".harness" / "handoff.md", body)


__all__ = ["cmd_new_phase"]
