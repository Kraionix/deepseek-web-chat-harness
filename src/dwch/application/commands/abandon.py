"""`dwch abandon` — mark the current phase abandoned.

Closes the phase without finalizing it. Files stay on disk,
including a frozen plan. The next phase does not inherit anything
from an abandoned one.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...domain.rules import is_phase_open, is_unset_phase
from ...shared.errors import HarnessError
from ..config import load_config
from ..deps import Deps
from ..state import load_state, now_iso, save_state, set_phase_abandoned


def cmd_abandon(args: Namespace, deps: Deps) -> int:
    """Abandon the current phase. Returns 0 or 2."""
    if not getattr(args, "yes", False):
        print("error: abandon closes the phase; pass --yes to confirm", file=sys.stderr)
        return 2

    try:
        # Load the config first: it validates that the project is
        # actually initialized before we touch state.
        load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if is_unset_phase(state):
        print("error: no active phase", file=sys.stderr)
        return 2
    if not is_phase_open(state):
        print(
            f"error: phase {state.phase_name} is already {state.phase_status}",
            file=sys.stderr,
        )
        return 2

    now = now_iso()
    fresh = set_phase_abandoned(state, now)
    save_state(deps.fs, deps.project_root, fresh)

    try:
        commit = deps.git.commit_all(
            deps.project_root, f"chore: abandon phase {state.phase_name}"
        )
        print(f"commit: {commit}")
    except HarnessError as exc:
        save_state(deps.fs, deps.project_root, state)
        print(f"error: commit failed: {exc}", file=sys.stderr)
        print("state was restored; the phase was not abandoned", file=sys.stderr)
        return 2

    print(f"abandoned: phase {state.phase_name}")
    return 0


__all__ = ["cmd_abandon"]
