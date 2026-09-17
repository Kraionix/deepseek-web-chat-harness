"""`dwch read PATH` — wrap one or more files in step markers.

The output is the same format the AI uses to write files, so the
inverse operation is trivial. A header line with the token count
gives the AI advance notice of the size.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

from ...shared.errors import FilesystemError, HarnessError
from ..config import load_config
from ..deps import Deps
from ..format import FILE_CLOSE, FILE_OPEN


def cmd_read(args: Namespace, deps: Deps, _config) -> int:
    """Read files and print them wrapped. Returns 0 or 2."""
    try:
        config = load_config(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    paths = _resolve_paths(args.path, deps)
    if not paths:
        print(f"error: no files match {args.path!r}", file=sys.stderr)
        return 2

    parts: list[str] = []
    for path in paths:
        try:
            text = deps.fs.read_text(path)
        except FilesystemError as exc:
            print(f"warning: skipping {path}: {exc}", file=sys.stderr)
            continue
        rel = path.relative_to(deps.project_root).as_posix()
        tokens = deps.counter.count(text)
        parts.append(f"<!-- {rel} ({tokens} tokens) -->")
        parts.append(f"{FILE_OPEN}{rel}>>>")
        parts.append(text.rstrip("\n"))
        parts.append(FILE_CLOSE)
        parts.append("")

    output = "\n".join(parts)

    # Warn if any single file exceeds the configured threshold.
    for path in paths:
        try:
            size = deps.counter.count(deps.fs.read_text(path))
        except HarnessError:
            continue
        if size > config.read_max_tokens:
            print(
                f"warning: {path.name} is {size} tokens (>{config.read_max_tokens})",
                file=sys.stderr,
            )

    if args.clipboard:
        if deps.clipboard.write(output):
            print("copied to clipboard", file=sys.stderr)
        else:
            print(output)
    else:
        print(output)
    return 0


def _resolve_paths(pattern: str, deps: Deps) -> list[Path]:
    """Resolve one argument to a list of files.

    If the argument contains a glob wildcard, expand it. If it names
    a directory, list its `.py` and `.md` files. Otherwise treat it
    as a single path.
    """
    p = Path(pattern)
    if not p.is_absolute():
        p = deps.project_root / p
    if any(ch in pattern for ch in "*?["):
        return sorted(deps.fs.glob(deps.project_root, pattern))
    if deps.fs.is_dir(p):
        files = deps.fs.listdir(p)
        return sorted(f for f in files if f.suffix in (".py", ".md", ".toml"))
    if deps.fs.is_file(p):
        return [p]
    return []


__all__ = ["cmd_read"]
