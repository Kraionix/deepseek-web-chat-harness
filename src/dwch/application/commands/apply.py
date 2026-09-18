"""`dwch apply` — write the files of a step, or the phase summary.

Two forms share one command:

- `dwch apply NN` — parse a step message and write its files.
- `dwch apply summary` — write the current phase's summary.

In both forms the message is read from the clipboard, or from
`--from-file`. Before any file is written, the entire message is
parsed and every path is validated. On any error, nothing is
written.

A step's raw message is saved to `steps/{phase}/step-NN.txt` for
the record, even when parsing fails. This makes a failed apply
diagnosable without asking the AI to re-send.

A summary's raw message is saved to `steps/{phase}/summary.txt`,
and the single file block is written to
`.harness/summaries/{phase}.md`. The summary does not modify state;
`dwch close` records it later. A summary is never overwritten: once
written, only the user can remove it, and `close` will refuse to
run twice on the same phase anyway.

Step filenames go through `format_step`, so `apply 1` and
`apply 01` write the same `step-01.txt`, matching what `verify 01`
looks for.
"""

from __future__ import annotations

import contextlib
import sys
from argparse import Namespace
from pathlib import Path

from ...domain.rules import is_unset_phase
from ...shared.errors import FormatError, HarnessError
from ..config import load_config
from ..deps import Deps
from ..format import (
    detect_marker_collision,
    format_step,
    parse_step_arg,
    parse_step_message,
    validate_paths,
)
from ..handoff import ensure_metadata
from ..state import load_state


def cmd_apply(args: Namespace, deps: Deps) -> int:
    """Dispatch to the step form or the summary form.

    Returns 0 on success, 1 on parse error, 2 on I/O or precondition
    failure.
    """
    if args.step == "summary":
        return _apply_summary(args, deps)
    return _apply_step(args, deps)


def _apply_step(args: Namespace, deps: Deps) -> int:
    """Apply a numbered step. Returns 0, 1, or 2."""
    try:
        step_num = parse_step_arg(args.step)
    except FormatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if is_unset_phase(state):
        print(
            "error: no active phase; run "
            "`dwch new-phase NAME --kind {planning|development}` first",
            file=sys.stderr,
        )
        return 2

    tag = format_step(step_num)
    steps_root = deps.project_root / config.paths.get("steps", "steps")
    steps_dir = steps_root / state.current_phase
    step_text = _read_message(args, deps)
    if step_text is None:
        return 2
    if not step_text.strip():
        print("error: empty step message", file=sys.stderr)
        return 1

    deps.fs.mkdir(steps_dir, parents=True)
    _ensure_steps_gitignore(deps, steps_root)
    step_file = steps_dir / f"step-{tag}.txt"
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
            deps.fs.mkdir(target.parent, parents=True)
            deps.fs.write_text(target, spec.content)
            written.append((spec.path, existed))
    except HarnessError as exc:
        _rollback_written(deps, written)
        print(f"error writing files: {exc}", file=sys.stderr)
        print("partial writes were rolled back", file=sys.stderr)
        return 2

    # Invariant: after a step, the harness block in handoff.md is
    # present and current, even if the AI rewrote the surrounding
    # prose without it.
    ensure_metadata(deps.fs, deps.project_root, state)

    log_lines = [
        f"step:  {tag}",
        f"phase: {state.current_phase}",
        f"saved: {step_file.relative_to(deps.project_root).as_posix()}",
        f"files: {len(written)}",
    ]
    for path, existed in written:
        verb = "overwrote" if existed else "wrote"
        log_lines.append(f"  {verb} {path}")
    log_text = "\n".join(log_lines) + "\n"
    deps.fs.write_text(steps_dir / f"apply-{tag}.log", log_text)
    sys.stdout.write(log_text)
    return 0


def _apply_summary(args: Namespace, deps: Deps) -> int:
    """Write the current phase's summary. Returns 0, 1, or 2.

    Pre:  an active phase exists; the clipboard or `--from-file`
          holds exactly one file block whose normalized path equals
          `.harness/summaries/{phase}.md`; no summary for this phase
          exists on disk yet.
    Post: the summary file and the raw message are on disk. State is
          unchanged; `dwch close` records the summary afterwards.
    Raises: never. Errors are printed and converted into an exit
          code.
    """
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if is_unset_phase(state):
        print(
            "error: no active phase; run "
            "`dwch new-phase NAME --kind {planning|development}` first",
            file=sys.stderr,
        )
        return 2

    steps_root = deps.project_root / config.paths.get("steps", "steps")
    steps_dir = steps_root / state.current_phase

    summary_text = _read_message(args, deps, label="summary")
    if summary_text is None:
        return 2
    if not summary_text.strip():
        print("error: empty summary message", file=sys.stderr)
        return 1

    try:
        specs = parse_step_message(summary_text)
        validate_paths(specs, deps.project_root)
    except FormatError as exc:
        print(f"parse error: {exc}", file=sys.stderr)
        return 1

    expected = f".harness/summaries/{state.current_phase}.md"
    if len(specs) != 1:
        print(
            f"error: summary message must contain exactly one file block "
            f"for {expected}, got {len(specs)}",
            file=sys.stderr,
        )
        return 1
    actual = specs[0].path.replace("\\", "/")
    if actual != expected:
        print(
            f"error: summary block path must be {expected}, got {actual}",
            file=sys.stderr,
        )
        return 1

    summary_path = deps.project_root / expected
    if deps.fs.exists(summary_path):
        print(
            f"error: summary already exists at {expected}. "
            "Summaries are append-only; delete the file first if you "
            "need to rewrite it.",
            file=sys.stderr,
        )
        return 2

    deps.fs.mkdir(steps_dir, parents=True)
    _ensure_steps_gitignore(deps, steps_root)
    deps.fs.write_text(steps_dir / "summary.txt", summary_text)

    deps.fs.mkdir(summary_path.parent, parents=True)
    deps.fs.write_text(summary_path, specs[0].content)

    print(f"wrote: {expected}")
    print("next: dwch close")
    return 0


def _read_message(args: Namespace, deps: Deps, label: str = "step") -> str | None:
    """Return the message text, or None after printing an error.

    `--from-file` resolves its argument relative to the project
    root, not the process working directory. The message is project
    data; it belongs with the project, not with the shell.

    `label` names the message kind in error text ("step" or
    "summary").
    """
    if args.from_file is not None:
        path = Path(args.from_file)
        if not path.is_absolute():
            path = deps.project_root / path
        if not deps.fs.is_file(path):
            print(f"error: file not found: {path}", file=sys.stderr)
            return None
        try:
            return deps.fs.read_text(path)
        except HarnessError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return None
    text = deps.clipboard.read()
    if not text.strip():
        print(
            f"error: clipboard is empty; copy the {label} message first, "
            "or use --from-file",
            file=sys.stderr,
        )
        return None
    return text


def _ensure_steps_gitignore(deps: Deps, steps_root: Path) -> None:
    """Write `steps/.gitignore` if missing.

    `init` writes this file for new projects. Calling it here lets
    projects self-heal on the next apply, without requiring a full
    re-init. The pattern `*` ignores every file and subdirectory
    under `steps/`, including phase directories.
    """
    gitignore = steps_root / ".gitignore"
    if deps.fs.exists(gitignore):
        return
    deps.fs.write_text(
        gitignore,
        "# Session artifacts: step messages, apply logs, reports.\n*\n!.gitignore\n",
    )


def _rollback_written(deps: Deps, written: list[tuple[str, bool]]) -> None:
    """Best-effort rollback of files written before a failure.

    Files that existed before the apply are restored from `HEAD`;
    files that did not are removed. Empty directories created by
    `mkdir(parents=True)` are left behind — removing them safely
    would require knowing which were created by this call, and the
    cost of leaving an empty directory is nil.
    """
    tracked = [p for p, existed in written if existed]
    new_files = [p for p, existed in written if not existed]

    if tracked:
        with contextlib.suppress(HarnessError):
            deps.git.checkout_paths(deps.project_root, "HEAD", tracked)

    for rel in new_files:
        target = deps.project_root / rel
        with contextlib.suppress(HarnessError):
            deps.fs.unlink(target)


__all__ = ["cmd_apply"]
