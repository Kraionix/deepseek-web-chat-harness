"""`dwch next` — assemble the current task's bootstrap.

Read-only. Does not advance state. Reads `state.plan.position`,
finds the task in `plan.toml`, assembles the bootstrap, writes it
to the clipboard (and stdout on clipboard failure). Idempotent.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...domain.rules import is_phase_open, is_unset_phase
from ...shared.errors import HarnessError
from .. import plan as plan_mod
from ..config import load_config
from ..context import build_bootstrap
from ..deps import Deps
from ..state import load_state


def cmd_next(args: Namespace, deps: Deps) -> int:
    """Build the current-task bootstrap. Returns 0 or 2."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if is_unset_phase(state):
        print(
            'error: no active phase; run `dwch start "goal"` first',
            file=sys.stderr,
        )
        return 2
    if not is_phase_open(state):
        print(
            f"error: phase {state.phase_name} is {state.phase_status}; "
            "start a new phase",
            file=sys.stderr,
        )
        return 2

    plan = _load_plan_or_none(deps, config)
    result = build_bootstrap(deps, config, state, plan, mode="task")

    print("token breakdown:", file=sys.stderr)
    for name, count in result.breakdown.items():
        print(f"  {name:<20} {count:>6}", file=sys.stderr)
    print(f"  {'TOTAL':<20} {result.total_tokens:>6}", file=sys.stderr)
    if result.truncated:
        print("  (truncated to fit max_tokens)", file=sys.stderr)

    if deps.clipboard.write(result.text):
        print("bootstrap copied to clipboard", file=sys.stderr)
    else:
        print("warning: clipboard unavailable; printing to stdout", file=sys.stderr)
        print(result.text)
    return 0


def _load_plan_or_none(deps: Deps, config):
    path = deps.project_root / config.plan["path"]
    if not deps.fs.exists(path):
        return None
    try:
        return plan_mod.load(deps.fs, path)
    except HarnessError as exc:
        print(f"warning: could not load plan: {exc}", file=sys.stderr)
        return None


__all__ = ["cmd_next"]
