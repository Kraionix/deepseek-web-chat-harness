"""`dwch fix` — assemble a fix-bootstrap for a fresh chat.

Read-only. Uses the same layers as `next`, but L5 is the current
failure description rather than the task spec. Requires a recorded
failure in state.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...shared.errors import HarnessError
from .. import plan as plan_mod
from ..config import load_config
from ..context import build_bootstrap
from ..deps import Deps
from ..state import load_state


def cmd_fix(args: Namespace, deps: Deps) -> int:
    """Build a fix-bootstrap. Returns 0 or 2."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not state.failure_task_id:
        print(
            "error: no recorded failure; run `dwch verify` first",
            file=sys.stderr,
        )
        return 2

    plan_path = deps.project_root / config.plan["path"]
    plan = None
    if deps.fs.exists(plan_path):
        try:
            plan = plan_mod.load(deps.fs, plan_path)
        except HarnessError as exc:
            print(f"warning: could not load plan: {exc}", file=sys.stderr)

    result = build_bootstrap(deps, config, state, plan, mode="fix")

    print("token breakdown:", file=sys.stderr)
    for name, count in result.breakdown.items():
        print(f"  {name:<20} {count:>6}", file=sys.stderr)
    print(f"  {'TOTAL':<20} {result.total_tokens:>6}", file=sys.stderr)
    if result.truncated:
        print("  (truncated to fit max_tokens)", file=sys.stderr)

    if deps.clipboard.write(result.text):
        print("fix-bootstrap copied to clipboard", file=sys.stderr)
    else:
        print("warning: clipboard unavailable; printing to stdout", file=sys.stderr)
        print(result.text)
    return 0


__all__ = ["cmd_fix"]
