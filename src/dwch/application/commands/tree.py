"""`dwch tree [ROOT]` — print an indented directory tree.

Read-only. `ROOT` defaults to `context.map_root` from config, or
the project root when `map_root` is unset.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

from ...shared.errors import HarnessError
from ..config import load_config
from ..deps import Deps


def cmd_tree(args: Namespace, deps: Deps) -> int:
    """Print a directory tree. Returns 0 or 2."""
    try:
        config = load_config(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    name = getattr(args, "root", None) or config.context.get("map_root") or "."
    root = deps.project_root / name
    if not deps.fs.is_dir(root):
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2
    lines = [f"{root.name or root.as_posix()}/"]
    _walk(deps, root, lines, prefix="")
    print("\n".join(lines))
    return 0


def _walk(deps: Deps, path: Path, lines: list[str], prefix: str) -> None:
    try:
        entries = sorted(
            deps.fs.listdir(path),
            key=lambda p: (deps.fs.is_file(p), p.name),
        )
    except HarnessError:
        return
    for i, entry in enumerate(entries):
        last = i == len(entries) - 1
        marker = "`-- " if last else "|-- "
        suffix = "/" if deps.fs.is_dir(entry) else ""
        lines.append(f"{prefix}{marker}{entry.name}{suffix}")
        if deps.fs.is_dir(entry) and not entry.name.startswith("."):
            _walk(deps, entry, lines, prefix + ("    " if last else "|   "))


__all__ = ["cmd_tree"]
