"""`dwch map` — print the module interface map.

Used by the AI to ask for a section of the codebase on demand.
`bootstrap` includes a brief version; this command can render the
full version, or the map for a specific subdirectory.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

from ...shared.errors import HarnessError
from ..config import load_config
from ..deps import Deps
from ..module_map import build_module_map, render_module_map


def cmd_map(args: Namespace, deps: Deps, _config) -> int:
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

    if args.tree:
        text = _tree(deps, root) + "\n" + text

    if args.clipboard:
        if deps.clipboard.write(text):
            print("copied to clipboard", file=sys.stderr)
        else:
            print(text)
    else:
        print(text)
    return 0


def _tree(deps: Deps, root: Path) -> str:
    """Simple indented tree of `root`'s contents."""
    if not deps.fs.is_dir(root):
        return f"{root.name}/ (missing)"
    lines = [f"{root.name}/"]
    _walk(deps, root, lines, prefix="")
    return "\n".join(lines)


def _walk(deps: Deps, path: Path, lines: list[str], prefix: str) -> None:
    entries = sorted(deps.fs.listdir(path), key=lambda p: (p.is_file(), p.name))
    for i, entry in enumerate(entries):
        last = i == len(entries) - 1
        marker = "`-- " if last else "|-- "
        lines.append(f"{prefix}{marker}{entry.name}{'/' if entry.is_dir() else ''}")
        if entry.is_dir() and not entry.name.startswith("."):
            _walk(deps, entry, lines, prefix + ("    " if last else "|   "))


__all__ = ["cmd_map"]
