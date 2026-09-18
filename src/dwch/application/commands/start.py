"""`dwch start "goal"` — begin a phase.

The phase kind is inferred: a frozen plan means the phase is
development; otherwise it is planning. `--kind` overrides.

The phase name is generated from the goal and a counter, and is
validated against `phase_name_error`. Existing phase names under
`steps/` are never reused.
"""

from __future__ import annotations

import re
import sys
from argparse import Namespace

from ...domain.rules import is_phase_open, phase_name_error
from ...shared.errors import HarnessError
from ..config import load_config
from ..deps import Deps
from ..state import load_state, now_iso, save_state, set_phase_open


def cmd_start(args: Namespace, deps: Deps) -> int:
    """Start a phase. Returns 0 or 2."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if is_phase_open(state):
        print(
            f"error: phase {state.phase_name} is already open. "
            "Run `dwch done` or `dwch abandon` first.",
            file=sys.stderr,
        )
        return 2

    if not deps.git.is_clean_tracked(deps.project_root):
        print(
            "error: working tree has uncommitted tracked changes; "
            "commit or stash before starting a new phase",
            file=sys.stderr,
        )
        return 2

    kind = args.kind or ("development" if state.plan_frozen else "planning")

    name = _generate_phase_name(deps, config, args.goal)
    err = phase_name_error(name)
    if err is not None:
        print(
            f"error: generated phase name {name!r} is invalid: {err}", file=sys.stderr
        )
        return 2

    steps_root = deps.project_root / config.paths.get("steps", "steps")
    if deps.fs.exists(steps_root / name):
        print(
            f"error: phase {name} already exists; choose a different goal.",
            file=sys.stderr,
        )
        return 2

    now = now_iso()
    head = deps.git.try_head(deps.project_root)
    fresh = set_phase_open(state, name, kind, now)
    from dataclasses import replace

    fresh = replace(fresh, last_commit=head, last_commit_date=now)
    save_state(deps.fs, deps.project_root, fresh)

    try:
        commit = deps.git.commit_all(
            deps.project_root, f"chore: start {kind} phase {name}"
        )
        print(f"commit: {commit}")
    except HarnessError as exc:
        save_state(deps.fs, deps.project_root, state)
        print(f"error: commit failed: {exc}", file=sys.stderr)
        print("state was restored; the phase did not start", file=sys.stderr)
        return 2

    print(f"new phase: {name} ({kind})")
    print("next: run `dwch next` to get a bootstrap")
    return 0


def _generate_phase_name(deps: Deps, config, goal: str) -> str:
    """Generate a phase name from the goal and a counter."""
    steps_root = deps.project_root / config.paths.get("steps", "steps")
    n = 1
    if deps.fs.is_dir(steps_root):
        n = 1 + sum(1 for p in deps.fs.listdir(steps_root) if deps.fs.is_dir(p))
    slug = re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-")[:30]
    if not slug:
        slug = "phase"
    return f"{n:02d}-{slug}"


__all__ = ["cmd_start"]
