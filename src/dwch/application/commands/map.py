"""`dwch map` — print the module interface map.

Used by the AI to ask for a section of the codebase on demand.
`next` includes a brief version; this command can render the full
version, or the map for a specific subdirectory.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...shared.errors import HarnessError
from ..config import load_config
from ..deps import Deps
from ..module_map import build_module_map, render_module_map


def cmd_map(args: Namespace, deps: Deps) -> int:
    """Print the map. Returns 0 on success, 2 on error."""
    try:
        config = load_config(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    root_name = args.root or config.context.get("map_root", "")
    if not root_name:
        print(
            "error: no map_root configured and no --root given",
            file=sys.stderr,
        )
        return 2
    root = deps.project_root / root_name
    modules = build_module_map(deps.fs, root, include_private=args.private)
    text = render_module_map(modules, full=args.full)

    if args.clipboard:
        if deps.clipboard.write(text):
            print("copied to clipboard", file=sys.stderr)
        else:
            print(text)
    else:
        print(text)
    return 0


__all__ = ["cmd_map"]
