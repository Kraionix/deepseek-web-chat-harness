"""`dwch apply` — write, delete, or move the files of a step.

Two forms share one command:

- `dwch apply NN` — parse a step message and execute its ops.
- `dwch apply summary` — write the current phase's summary.

In both forms the message is read from the clipboard, or from
`--from-file`. Before any file is written, the entire message is
parsed and every path is validated.

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
from dataclasses import dataclass
from pathlib import Path

from ...domain.models import (
    DeleteOp,
    MoveOp,
    StepOp,
    WriteOp,
    op_paths,
)
from ...domain.rules import is_unset_phase
from ...shared.errors import FormatError, HarnessError
from ...shared.paths import normalize_rel, safe_path
from ..config import load_config
from ..deps import Deps
from ..format import (
    MAX_FILE_BYTES,
    MAX_SNAPSHOT_TOTAL_BYTES,
    detect_marker_collision,
    format_step,
    is_protected,
    parse_step_arg,
    parse_step_message,
    validate_paths,
)
from ..handoff import ensure_metadata
from ..state import load_state


@dataclass
class _OpRecord:
    """Per-op state captured before the op was applied.

    Used by rollback. `snapshot` is the old content, present only
    when the op overwrote or deleted an untracked file.
    """

    op: StepOp
    existed_before: bool
    was_tracked: bool
    snapshot: str | None


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
        ops = parse_step_message(step_text)
        validate_paths(ops, deps.project_root)
        for op in ops:
            if isinstance(op, WriteOp):
                detect_marker_collision(op)
        _check_protected_paths(ops)
        _check_preconditions(ops, deps)
        _check_snapshot_limits(ops, deps)
        _check_dirty_tracked(ops, deps)
    except FormatError as exc:
        print(f"parse error: {exc}", file=sys.stderr)
        print(f"raw message saved: {step_file}", file=sys.stderr)
        print("--- first 200 chars of the message ---", file=sys.stderr)
        preview = step_text[:200].replace("\n", "\\n")
        print(preview, file=sys.stderr)
        print("--- end preview ---", file=sys.stderr)
        return 1

    applied: list[_OpRecord] = []
    failure: HarnessError | None = None
    try:
        for op in ops:
            record = _apply_op(op, deps)
            applied.append(record)
    except HarnessError as exc:
        failure = exc
        _rollback(deps, applied)

    # Invariant: after a step, the harness block in handoff.md is
    # present and current, even if the AI rewrote the surrounding
    # prose without it. Only on success: a rolled-back step should
    # leave the handoff as it was.
    if failure is None:
        ensure_metadata(deps.fs, deps.project_root, state)

    log_lines = [
        f"step:  {tag}",
        f"phase: {state.current_phase}",
        f"saved: {step_file.relative_to(deps.project_root).as_posix()}",
        f"ops: {len(applied)}",
    ]
    for record in applied:
        op = record.op
        if isinstance(op, WriteOp):
            verb = "overwrote" if record.existed_before else "wrote"
            log_lines.append(f"  {verb} {op.path}")
        elif isinstance(op, DeleteOp):
            log_lines.append(f"  deleted {op.path}")
        elif isinstance(op, MoveOp):
            log_lines.append(f"  moved {op.src} → {op.dst}")
    if failure is not None:
        log_lines.append(f"rollback: {failure}")
        for record in reversed(applied):
            log_lines.append(f"  restored {_op_label(record.op)}")
    log_text = "\n".join(log_lines) + "\n"
    deps.fs.write_text(steps_dir / f"apply-{tag}.log", log_text)
    sys.stdout.write(log_text)

    if failure is not None:
        print(f"error writing files: {failure}", file=sys.stderr)
        print("partial writes were rolled back", file=sys.stderr)
        return 2
    return 0


def _op_label(op: StepOp) -> str:
    """A short label for the rollback log line."""
    if isinstance(op, WriteOp):
        return op.path
    if isinstance(op, DeleteOp):
        return op.path
    if isinstance(op, MoveOp):
        return f"{op.src} → {op.dst}"
    return "?"


def _check_protected_paths(ops: list[StepOp]) -> None:
    """Refuse `DELETE` or `MOVE` on a protected path."""
    for op in ops:
        if isinstance(op, DeleteOp):
            if is_protected(op.path):
                raise FormatError(f"cannot delete protected path: {op.path}")
        elif isinstance(op, MoveOp):
            if is_protected(op.src):
                raise FormatError(f"cannot move protected path: {op.src}")
            if is_protected(op.dst):
                raise FormatError(f"cannot move to protected path: {op.dst}")


def _check_preconditions(ops: list[StepOp], deps: Deps) -> None:
    """Every precondition that does not depend on the write order.

    - `WriteOp`: the target must not be an existing directory.
    - `DeleteOp`: the target exists, is a file, and is tracked.
    - `MoveOp`: `src` exists and is a file; `dst` does not exist.
    """
    resolved_root = deps.project_root.resolve(strict=False)
    for op in ops:
        if isinstance(op, WriteOp):
            target = safe_path(op.path, resolved_root)
            if deps.fs.is_dir(target):
                raise FormatError(
                    f"cannot write {op.path!r}: a directory exists at that path"
                )
        elif isinstance(op, DeleteOp):
            target = safe_path(op.path, resolved_root)
            if not deps.fs.is_file(target):
                raise FormatError(f"cannot delete {op.path!r}: not a file")
            if not _is_tracked(deps, op.path):
                raise FormatError(
                    f"cannot delete untracked file {op.path!r}: "
                    "only tracked files may be deleted"
                )
        elif isinstance(op, MoveOp):
            src = safe_path(op.src, resolved_root)
            dst = safe_path(op.dst, resolved_root)
            if not deps.fs.is_file(src):
                raise FormatError(f"cannot move {op.src!r}: not a file")
            if deps.fs.exists(dst):
                raise FormatError(
                    f"cannot move to {op.dst!r}: destination already exists"
                )


def _check_snapshot_limits(ops: list[StepOp], deps: Deps) -> None:
    """Refuse a step whose snapshot would exceed the memory limits."""
    resolved_root = deps.project_root.resolve(strict=False)
    total = 0
    count = 0
    for op in ops:
        if not isinstance(op, WriteOp):
            continue
        target = safe_path(op.path, resolved_root)
        if not deps.fs.is_file(target):
            continue
        if _is_tracked(deps, op.path):
            continue
        content = deps.fs.read_text(target)
        size = len(content.encode("utf-8"))
        if size > MAX_FILE_BYTES:
            raise FormatError(
                f"existing untracked file {op.path} is {size} bytes; "
                f"limit is {MAX_FILE_BYTES}"
            )
        total += size
        count += 1

    if total > MAX_SNAPSHOT_TOTAL_BYTES:
        mib = total // (1024 * 1024)
        limit_mib = MAX_SNAPSHOT_TOTAL_BYTES // (1024 * 1024)
        raise FormatError(
            f"step overwrites {count} untracked files totaling {mib} MiB; "
            f"snapshot limit is {limit_mib} MiB; "
            "commit them first or split the step"
        )


def _check_dirty_tracked(ops: list[StepOp], deps: Deps) -> None:
    """Refuse a step that touches a tracked file with uncommitted changes."""
    try:
        lines = deps.git.status_short(deps.project_root)
    except HarnessError:
        return

    modified: set[str] = set()
    for line in lines:
        if line.startswith("??"):
            continue
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        modified.add(normalize_rel(path))

    touched: set[str] = set()
    for op in ops:
        for p in op_paths(op):
            touched.add(normalize_rel(p))

    overlap = touched & modified
    if overlap:
        raise FormatError(
            "uncommitted changes in: "
            + ", ".join(sorted(overlap))
            + "; commit or stash first"
        )


def _apply_op(op: StepOp, deps: Deps) -> _OpRecord:
    """Execute one op and return the state needed to undo it."""
    resolved_root = deps.project_root.resolve(strict=False)

    if isinstance(op, WriteOp):
        target = safe_path(op.path, resolved_root)
        existed = deps.fs.is_file(target)
        tracked = _is_tracked(deps, op.path)
        snapshot = None
        if existed and not tracked:
            snapshot = deps.fs.read_text(target)
        deps.fs.mkdir(target.parent, parents=True)
        deps.fs.write_text(target, op.content)
        return _OpRecord(
            op=op, existed_before=existed, was_tracked=tracked, snapshot=snapshot
        )

    if isinstance(op, DeleteOp):
        target = safe_path(op.path, resolved_root)
        tracked = _is_tracked(deps, op.path)
        snapshot = None
        if not tracked:
            snapshot = deps.fs.read_text(target)
        deps.fs.unlink(target)
        return _OpRecord(
            op=op, existed_before=True, was_tracked=tracked, snapshot=snapshot
        )

    if isinstance(op, MoveOp):
        src = safe_path(op.src, resolved_root)
        dst = safe_path(op.dst, resolved_root)
        deps.fs.mkdir(dst.parent, parents=True)
        deps.fs.rename(src, dst)
        return _OpRecord(op=op, existed_before=True, was_tracked=False, snapshot=None)

    raise TypeError(f"unknown StepOp type: {type(op).__name__}")


def _rollback(deps: Deps, applied: list[_OpRecord]) -> None:
    """Undo the applied ops in reverse order.

    Tracked files are restored with one batched `git checkout`.
    Files that did not exist before the apply are removed.
    Untracked files that were overwritten or deleted are restored
    from the in-memory snapshot. A `MOVE` is reversed with a
    `rename`.
    """
    resolved_root = deps.project_root.resolve(strict=False)
    tracked_paths: list[str] = []

    for record in reversed(applied):
        op = record.op
        with contextlib.suppress(HarnessError):
            if isinstance(op, WriteOp):
                target = safe_path(op.path, resolved_root)
                if not record.existed_before:
                    if deps.fs.exists(target):
                        deps.fs.unlink(target)
                elif record.was_tracked:
                    tracked_paths.append(op.path)
                else:
                    deps.fs.write_text(target, record.snapshot or "")
            elif isinstance(op, DeleteOp):
                if record.was_tracked:
                    tracked_paths.append(op.path)
                else:
                    target = safe_path(op.path, resolved_root)
                    deps.fs.write_text(target, record.snapshot or "")
            elif isinstance(op, MoveOp):
                src = safe_path(op.src, resolved_root)
                dst = safe_path(op.dst, resolved_root)
                if deps.fs.exists(dst):
                    deps.fs.rename(dst, src)

    if tracked_paths:
        with contextlib.suppress(HarnessError):
            deps.git.checkout_paths(deps.project_root, "HEAD", tracked_paths)


def _is_tracked(deps: Deps, rel_path: str) -> bool:
    """True when `rel_path` is in the git index."""
    try:
        out = deps.git.ls_files(deps.project_root, rel_path)
    except HarnessError:
        return False
    return bool(out)


def _apply_summary(args: Namespace, deps: Deps) -> int:
    """Write the current phase's summary. Returns 0, 1, or 2.

    Pre:  an active phase exists; the clipboard or `--from-file`
          holds exactly one FILE block whose normalized path equals
          `.harness/summaries/{phase}.md`; no summary for this phase
          exists on disk yet.
    Post: the summary file and the raw message are on disk. State is
          unchanged; `dwch close` records the summary afterwards.
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
        ops = parse_step_message(summary_text)
        validate_paths(ops, deps.project_root)
    except FormatError as exc:
        print(f"parse error: {exc}", file=sys.stderr)
        return 1

    expected = f".harness/summaries/{state.current_phase}.md"
    if len(ops) != 1:
        print(
            f"error: summary message must contain exactly one file block "
            f"for {expected}, got {len(ops)}",
            file=sys.stderr,
        )
        return 1
    if not isinstance(ops[0], WriteOp):
        print(
            f"error: summary must be a single FILE block; got {type(ops[0]).__name__}",
            file=sys.stderr,
        )
        return 1
    actual = normalize_rel(ops[0].path)
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
    deps.fs.write_text(summary_path, ops[0].content)

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


__all__ = ["cmd_apply"]
