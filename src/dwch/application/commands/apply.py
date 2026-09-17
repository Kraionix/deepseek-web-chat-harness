"""`dwch apply NN` — parse a step message and write its files.

The message is read from the clipboard, or from `--from-file`.
Before any file is written, the entire message is parsed and every
path is validated. On any error, nothing is written.

The raw message is saved to `steps/step-NN.txt` for the record,
even when parsing fails. This makes a failed apply diagnosable
without asking the AI to re-send.
"""

from __future__ import annotations

import contextlib
import sys
from argparse import Namespace
from pathlib import Path

from ...shared.errors import FormatError, HarnessError
from ..config import load_config
from ..deps import Deps
from ..format import (
    detect_marker_collision,
    parse_step_message,
    validate_paths,
)


def cmd_apply(args: Namespace, deps: Deps, _config) -> int:
    """Apply a step. Returns 0 on success, 1 on parse error, 2 on I/O."""
    try:
        config = load_config(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    steps_dir = deps.project_root / config.paths.get("steps", "steps")
    step_text = _read_message(args, deps)
    if step_text is None:
        return 2
    if not step_text.strip():
        print("error: empty step message", file=sys.stderr)
        return 1

    deps.fs.mkdir(steps_dir, parents=True)
    _ensure_steps_gitignore(deps, steps_dir)
    step_file = steps_dir / f"step-{args.step}.txt"
    deps.fs.write_text(step_file, step_text)

    try:
        specs = parse_step_message(step_text)
        validate_paths(specs, deps.project_root)
        for spec in specs:
            detect_marker_collision(spec)
    except FormatError as exc:
        print(f"parse error: {exc}", file=sys.stderr)
        print(f"raw message saved: {step_file}", file=sys.stderr)
        print("--- first 200 chars of the message ---", file=sys.stderr)
        preview = step_text[:200].replace("\n", "\\n")
        print(preview, file=sys.stderr)
        print("--- end preview ---", file=sys.stderr)
        return 1

    written: list[tuple[str, bool]] = []
    try:
        for spec in specs:
            target = deps.project_root / spec.path
            existed = deps.fs.exists(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            deps.fs.write_text(target, spec.content)
            written.append((spec.path, existed))
    except OSError as exc:
        _rollback_written(deps, written)
        print(f"error writing files: {exc}", file=sys.stderr)
        print("partial writes were rolled back via git", file=sys.stderr)
        return 2

    log_lines = [
        f"step:  {args.step}",
        f"saved: {step_file.relative_to(deps.project_root)}",
        f"files: {len(written)}",
    ]
    for path, existed in written:
        verb = "overwrote" if existed else "wrote"
        log_lines.append(f"  {verb} {path}")
    log_text = "\n".join(log_lines) + "\n"
    (steps_dir / f"apply-{args.step}.log").write_text(
        log_text, encoding="utf-8", newline="\n"
    )
    sys.stdout.write(log_text)
    return 0


def _read_message(args: Namespace, deps: Deps) -> str | None:
    if args.from_file is not None:
        path = Path(args.from_file)
        if not path.is_file():
            print(f"error: file not found: {path}", file=sys.stderr)
            return None
        return path.read_text(encoding="utf-8")
    text = deps.clipboard.read()
    if not text.strip():
        print(
            "error: clipboard is empty; copy the step message first, "
            "or use --from-file",
            file=sys.stderr,
        )
        return None
    return text


def _ensure_steps_gitignore(deps: Deps, steps_dir: Path) -> None:
    """Write `steps/.gitignore` if missing.

    `init` writes this file for new projects. Calling it here lets
    projects initialized before this rule self-heal on the next
    apply, without requiring a full re-init.
    """
    gitignore = steps_dir / ".gitignore"
    if deps.fs.exists(gitignore):
        return
    deps.fs.write_text(
        gitignore,
        "# Session artifacts: step messages, apply logs, reports.\n*\n!.gitignore\n",
    )


def _rollback_written(deps: Deps, written: list[tuple[str, bool]]) -> None:
    """Best-effort rollback of files written before a failure."""
    paths = [p for p, _ in written]
    if not paths:
        return
    # Rollback is best-effort. The report still says which files
    # were written; the user can inspect git status themselves.
    with contextlib.suppress(HarnessError):
        deps.git.checkout_paths(deps.project_root, "HEAD", paths)


__all__ = ["cmd_apply"]
