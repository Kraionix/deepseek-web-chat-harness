"""`dwch bootstrap` — produce the opening message for a new chat.

The message is printed to stdout, and optionally copied to the
clipboard. The token breakdown is printed on stderr so the user can
see where the budget goes without it contaminating the copy.

`bootstrap` is read-only with respect to the repository: it does
not modify `state.toml`. A read-only command must never leave the
working tree dirty, because the next lifecycle command (`close`,
`new-phase`) checks for cleanliness.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...shared.errors import HarnessError
from .. import roadmap as roadmap_mod
from ..config import load_config
from ..context import build_bootstrap
from ..deps import Deps
from ..state import load_state


def cmd_bootstrap(args: Namespace, deps: Deps, _config) -> int:
    """Build and print the bootstrap. Returns 0 on success, 2 on error."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    roadmap = _load_roadmap(deps, config)

    try:
        result = build_bootstrap(deps, config, state, roadmap)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Print breakdown to stderr so `--clipboard` copies only the text.
    print("token breakdown:", file=sys.stderr)
    for name, count in result.breakdown.items():
        print(f"  {name:<20} {count:>6}", file=sys.stderr)
    print(f"  {'TOTAL':<20} {result.total_tokens:>6}", file=sys.stderr)
    if result.truncated:
        print("  (truncated to fit max_tokens)", file=sys.stderr)

    if args.clipboard:
        if not deps.clipboard.write(result.text):
            print(
                "warning: clipboard unavailable; printing to stdout",
                file=sys.stderr,
            )
            print(result.text)
        else:
            print("bootstrap copied to clipboard", file=sys.stderr)
    else:
        print(result.text)
    return 0


def _load_roadmap(deps: Deps, config):
    path = deps.project_root / config.roadmap.get("path", ".harness/roadmap.toml")
    if not deps.fs.exists(path):
        return None
    try:
        return roadmap_mod.load(deps.fs, path)
    except HarnessError:
        return None


__all__ = ["cmd_bootstrap"]
