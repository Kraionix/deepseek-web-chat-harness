"""`dwch rollback` — undo the last task commit.

User-only. Refuses unless HEAD subject begins with `task `. Performs
`git reset --hard HEAD~1`, reloads state, increments
`state.rollback.count`, and commits `chore: rollback task {id}`.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...shared.errors import HarnessError
from ..config import load_config
from ..deps import Deps
from ..state import (
    increment_rollback,
    load_state,
    now_iso,
    save_state,
    with_updates,
)


def cmd_rollback(args: Namespace, deps: Deps) -> int:
    """Rollback the last task commit. Returns 0 or 2."""
    if not getattr(args, "yes", False):
        print("error: rollback discards work; pass --yes to confirm", file=sys.stderr)
        return 2

    try:
        load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not deps.git.is_clean(deps.project_root):
        print("error: working tree is dirty; commit or stash first", file=sys.stderr)
        return 2

    try:
        subject = deps.git.last_commit_subject(deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not subject.startswith("task "):
        print(
            "error: HEAD is not a task commit; nothing to roll back. "
            f"HEAD is: {subject or '(unknown)'}",
            file=sys.stderr,
        )
        return 2

    task_id = state.verify_task_id or state.failure_task_id or "(unknown)"

    try:
        deps.git.reset_hard(deps.project_root, "HEAD~1")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        after = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: state after reset: {exc}", file=sys.stderr)
        return 2

    bumped = increment_rollback(after)
    bumped = with_updates(bumped, last_commit_date=now_iso())
    save_state(deps.fs, deps.project_root, bumped)

    try:
        commit = deps.git.commit_all(
            deps.project_root, f"chore: rollback task {task_id}"
        )
        print(f"commit: {commit}")
    except HarnessError as exc:
        print(f"warning: could not commit rollback: {exc}", file=sys.stderr)

    print(f"rolled back task {task_id}")
    return 0


__all__ = ["cmd_rollback"]
