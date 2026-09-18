"""`dwch rollback` — undo the last step.

Reverts the last commit, reloads state from the previous commit,
increments `rollback_count`, and commits a marker. Requires `--yes`
because the operation discards committed work.

Only a commit produced by `verify` may be rolled back. A `close`
and a `new-phase` commit are lifecycle transitions: rolling them
back would take the phase with them, and the user almost never
wants that from a command named "rollback the last step". The two
are told apart by the commit subject (`step NN: ...` vs
`chore: close phase ...` / `chore: start ... phase ...`).

`current_step` and `roadmap_step` are not modified directly: the
`git reset --hard` restores them from the previous commit's
`state.toml`. The commit that follows exists only to make the tree
clean for the next command.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...shared.errors import HarnessError
from ..config import load_config
from ..deps import Deps
from ..state import load_state, now_iso, save_state, with_updates

# A verify commit's subject begins with this prefix. `verify` builds
# the message as `f"step {args.step}: applied and verified"`. The
# prefix is the only signal `rollback` has to tell a step commit
# from a lifecycle commit, and it is stable.
_VERIFY_SUBJECT_PREFIX = "step "


def cmd_rollback(args: Namespace, deps: Deps) -> int:
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

    try:
        before = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if before.current_step <= 0:
        print("error: no step to roll back", file=sys.stderr)
        return 2

    try:
        subject = deps.git.last_commit_subject(deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not subject.startswith(_VERIFY_SUBJECT_PREFIX):
        print(
            "error: HEAD is not a verify commit; nothing to roll back. "
            f"HEAD is: {subject or '(unknown)'}. "
            "Rollback only undoes the last `dwch verify`.",
            file=sys.stderr,
        )
        return 2

    try:
        deps.git.reset_hard(deps.project_root, "HEAD~1")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # State on disk is now the previous commit's state. Reload it,
    # then bump only the rollback marker so the marker commit is
    # non-empty.
    try:
        after = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: state after reset: {exc}", file=sys.stderr)
        return 2

    updated = with_updates(
        after,
        rollback_count=after.rollback_count + 1,
        last_commit_date=now_iso(),
    )
    save_state(deps.fs, deps.project_root, updated)

    try:
        commit = deps.git.commit_all(
            deps.project_root, f"chore: rollback step {before.current_step}"
        )
        print(f"commit: {commit}")
    except HarnessError as exc:
        print(f"warning: could not commit rollback: {exc}", file=sys.stderr)

    print(f"rolled back to step {after.current_step}")
    return 0


__all__ = ["cmd_rollback"]
