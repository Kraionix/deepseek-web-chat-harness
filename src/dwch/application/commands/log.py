"""`dwch log [N]` — recent lifecycle events from the git log.

Read-only. Prints the last `N` commits (default 10) as one line
each. Lifecycle commits (`task ...`, `chore: ...`) are the events
the AI asks about.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...shared.errors import HarnessError
from ..deps import Deps


def cmd_log(args: Namespace, deps: Deps) -> int:
    """Print recent commits. Returns 0 or 2."""
    raw = getattr(args, "n", None)
    n = 10 if raw is None else int(raw)
    if n < 1:
        print("error: N must be >= 1", file=sys.stderr)
        return 2
    try:
        entries = deps.git.log_oneline(deps.project_root, n)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not entries:
        print("(no commits)")
        return 0
    for line in entries:
        print(line)
    return 0


__all__ = ["cmd_log"]
