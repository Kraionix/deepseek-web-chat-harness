"""`dwch count PATH` — count tokens in a file or directory.

Utility command for the user to inspect sizes without going through
the full `read` pipeline. Prints per-file counts when given a
directory, a single total when given a file.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

from ...shared.errors import FilesystemError
from ..deps import Deps


def cmd_count(args: Namespace, deps: Deps, _config) -> int:
    """Count tokens. Returns 0 on success, 2 on error."""
    target = Path(args.path)
    if not target.is_absolute():
        target = deps.project_root / target

    if deps.fs.is_file(target):
        try:
            text = deps.fs.read_text(target)
        except FilesystemError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"{target.relative_to(deps.project_root)}: {deps.counter.count(text)}")
        return 0

    if deps.fs.is_dir(target):
        files = [
            f
            for f in deps.fs.glob(target, "**/*")
            if deps.fs.is_file(f) and _is_text(f)
        ]
        if not files:
            print("(no text files)", file=sys.stderr)
            return 0
        texts: list[str] = []
        kept: list[Path] = []
        for path in files:
            try:
                texts.append(deps.fs.read_text(path))
                kept.append(path)
            except FilesystemError:
                continue
        counts = deps.counter.count_batch(texts)
        total = 0
        for path, count in zip(kept, counts, strict=True):
            rel = path.relative_to(deps.project_root)
            print(f"{rel}: {count}")
            total += count
        print(f"TOTAL: {total}")
        return 0

    print(f"error: not found: {target}", file=sys.stderr)
    return 2


def _is_text(path: Path) -> bool:
    """Heuristic: extensions we treat as text for token counting."""
    return path.suffix in (
        ".py",
        ".md",
        ".toml",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".cfg",
        ".ini",
        ".rst",
    )


__all__ = ["cmd_count"]
