"""`dwch rollback` — undo the last step.

Reverts the last commit, updates state, marks the step as rolled
back, and commits the state change. Requires `--yes` because the
operation discards committed work.

`last_commit` is not rewritten: it records the hash known at the
last lifecycle transition, not HEAD after every operation. That is
consistent with `verify`, which also leaves it alone.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from datetime import UTC, datetime

from ...domain.models import State
from ...shared.errors import HarnessError
from ..config import load_config
from ..deps import Deps
from ..state import load_state, save_state


def cmd_rollback(args: Namespace, deps: Deps, _config) -> int:
    """Rollback the last step. Returns 0 or 2."""
    if not args.yes:
        print("error: rollback discards work; pass --yes to confirm", file=sys.stderr)
        return 2

    try:
        load_config(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not deps.git.is_clean(deps.project_root):
        print("error: working tree is dirty; commit or stash first", file=sys.stderr)
        return 2

    state = load_state(deps.fs, deps.project_root)
    if state.current_step <= 0:
        print("error: no step to roll back", file=sys.stderr)
        return 2

    try:
        deps.git.reset_hard(deps.project_root, "HEAD~1")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    new_step = state.current_step - 1
    now = datetime.now(UTC).isoformat(timespec="seconds")
    updated = State(
        harness_version=state.harness_version,
        current_phase=state.current_phase,
        current_step=new_step,
        total_steps=new_step,
        last_commit=state.last_commit,
        last_commit_date=now,
        last_opened=state.last_opened,
        last_closed=state.last_closed,
    )
    save_state(deps.fs, deps.project_root, updated)

    # Commit the state change so the tree is clean for the next
    # command. The reset already discarded the step's commit; this
    # commit records the rollback itself.
    try:
        commit = deps.git.commit_all(
            deps.project_root, f"chore: rollback step {state.current_step}"
        )
        print(f"commit: {commit}")
    except HarnessError as exc:
        print(f"warning: could not commit rollback: {exc}", file=sys.stderr)

    print(f"rolled back to step {new_step}")
    return 0


__all__ = ["cmd_rollback"]
