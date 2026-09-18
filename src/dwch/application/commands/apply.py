"""`dwch apply` — write, delete, or move the files of the current task.

Reads the message from the clipboard, or from `--from-file`. Before
any file is written, the whole message is parsed and every path is
validated.

The raw message is saved to `steps/{phase}/{task_id}/message.txt`
for the record, even when parsing fails. This makes a failed apply
diagnosable without asking the AI to re-send.

After a successful apply, `state.verify.ok` is reset to False: a
task that has been re-applied has not been verified in its new
form. `done` requires a fresh `verify`.
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
from ...domain.rules import is_planning_phase, is_unset_phase
from ...shared.errors import FormatError, HarnessError
from ...shared.paths import normalize_rel, safe_path
from ..config import load_config
from ..deps import Deps
from ..format import (
    MAX_FILE_BYTES,
    detect_marker_collision,
    parse_step_message,
    validate_paths,
)
from ..state import load_state, save_state, with_updates

# Paths that `DELETE` and `MOVE` may not touch.
_PROTECTED_EXACT = frozenset(
    {
        ".harness/state.toml",
        ".harness/config.toml",
        ".harness/plan.toml",
        ".harness/.gitignore",
    }
)


@dataclass
class _OpRecord:
    """State captured before an op was applied, used for rollback."""

    op: StepOp
    existed_before: bool
    snapshot: str | None


def cmd_apply(args: Namespace, deps: Deps) -> int:
    """Apply a block message. Returns 0 on success, 1 on parse error, 2 on I/O."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if is_unset_phase(state):
        print('error: no active phase; run `dwch start "goal"` first', file=sys.stderr)
        return 2

    task_id = _current_task_id(state, deps, config)
    if task_id is None:
        print(
            "error: no current task; the plan is missing or exhausted",
            file=sys.stderr,
        )
        return 2

    steps_root = deps.project_root / config.paths.get("steps", "steps")
    steps_dir = steps_root / state.phase_name / task_id

    message = _read_message(args, deps)
    if message is None:
        return 2
    if not message.strip():
        print("error: empty message", file=sys.stderr)
        return 1

    deps.fs.mkdir(steps_dir, parents=True)
    _ensure_steps_gitignore(deps, steps_root)
    message_path = steps_dir / "message.txt"
    deps.fs.write_text(message_path, message)

    try:
        ops = parse_step_message(message)
        validate_paths(ops, deps.project_root)
        for op in ops:
            if isinstance(op, WriteOp):
                detect_marker_collision(op)
        _check_protected(ops)
        _check_preconditions(ops, deps)
        _check_dirty_tracked(ops, deps)
    except FormatError as exc:
        print(f"parse error: {exc}", file=sys.stderr)
        print(f"raw message saved: {message_path}", file=sys.stderr)
        return 1

    applied: list[_OpRecord] = []
    failure: HarnessError | None = None
    try:
        for op in ops:
            applied.append(_apply_op(op, deps))
    except HarnessError as exc:
        failure = exc
        _rollback(deps, applied)

    log_lines = [
        f"task:  {task_id}",
        f"phase: {state.phase_name}",
        f"saved: {message_path.relative_to(deps.project_root).as_posix()}",
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
    log_text = "\n".join(log_lines) + "\n"
    deps.fs.write_text(steps_dir / "apply.log", log_text)
    sys.stdout.write(log_text)

    if failure is not None:
        print(f"error writing files: {failure}", file=sys.stderr)
        print("partial writes were rolled back", file=sys.stderr)
        return 2

    # A re-applied task is not verified in its new form.
    fresh = with_updates(state, verify_ok=False, verify_task_id="", verify_at="")
    save_state(deps.fs, deps.project_root, fresh)
    return 0


def _current_task_id(state, deps: Deps, config) -> str | None:
    """Return the task id for the current position, or None."""
    if is_planning_phase(state):
        return "planning"
    from .. import plan as plan_mod

    plan_path = deps.project_root / config.plan["path"]
    if not deps.fs.exists(plan_path):
        return None
    plan = plan_mod.load(deps.fs, plan_path)
    if state.plan_position < 0 or state.plan_position >= len(plan.tasks):
        return None
    return plan.tasks[state.plan_position].id


def _check_protected(ops: list[StepOp]) -> None:
    """Refuse `DELETE` or `MOVE` on a protected path."""
    for op in ops:
        if isinstance(op, DeleteOp):
            if _is_protected(op.path):
                raise FormatError(f"cannot delete protected path: {op.path}")
        elif isinstance(op, MoveOp):
            if _is_protected(op.src):
                raise FormatError(f"cannot move protected path: {op.src}")
            if _is_protected(op.dst):
                raise FormatError(f"cannot move to protected path: {op.dst}")


def _is_protected(rel: str) -> bool:
    norm = normalize_rel(rel)
    if norm in _PROTECTED_EXACT:
        return True
    return norm == "steps" or norm.startswith("steps/")


def _check_preconditions(ops: list[StepOp], deps: Deps) -> None:
    """Every precondition that does not depend on the write order."""
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


def _check_dirty_tracked(ops: list[StepOp], deps: Deps) -> None:
    """Refuse a task that touches a tracked file with uncommitted changes."""
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
        snapshot = deps.fs.read_text(target) if existed else None
        if snapshot is not None and len(snapshot.encode()) > MAX_FILE_BYTES:
            raise FormatError(
                f"existing file {op.path} is larger than {MAX_FILE_BYTES} bytes"
            )
        deps.fs.mkdir(target.parent, parents=True)
        deps.fs.write_text(target, op.content)
        return _OpRecord(op=op, existed_before=existed, snapshot=snapshot)

    if isinstance(op, DeleteOp):
        target = safe_path(op.path, resolved_root)
        snapshot = deps.fs.read_text(target)
        deps.fs.unlink(target)
        return _OpRecord(op=op, existed_before=True, snapshot=snapshot)

    if isinstance(op, MoveOp):
        src = safe_path(op.src, resolved_root)
        dst = safe_path(op.dst, resolved_root)
        deps.fs.mkdir(dst.parent, parents=True)
        deps.fs.rename(src, dst)
        return _OpRecord(op=op, existed_before=True, snapshot=None)

    raise TypeError(f"unknown StepOp type: {type(op).__name__}")


def _rollback(deps: Deps, applied: list[_OpRecord]) -> None:
    """Undo the applied ops in reverse order."""
    resolved_root = deps.project_root.resolve(strict=False)
    for record in reversed(applied):
        op = record.op
        with contextlib.suppress(HarnessError):
            if isinstance(op, WriteOp):
                target = safe_path(op.path, resolved_root)
                if record.existed_before:
                    deps.fs.write_text(target, record.snapshot or "")
                elif deps.fs.exists(target):
                    deps.fs.unlink(target)
            elif isinstance(op, DeleteOp):
                target = safe_path(op.path, resolved_root)
                deps.fs.write_text(target, record.snapshot or "")
            elif isinstance(op, MoveOp):
                src = safe_path(op.src, resolved_root)
                dst = safe_path(op.dst, resolved_root)
                if deps.fs.exists(dst):
                    deps.fs.rename(dst, src)


def _is_tracked(deps: Deps, rel_path: str) -> bool:
    """True when `rel_path` is in the git index."""
    try:
        out = deps.git.ls_files(deps.project_root, rel_path)
    except HarnessError:
        return False
    return bool(out)


def _read_message(args: Namespace, deps: Deps) -> str | None:
    """Return the message text, or None after printing an error."""
    if getattr(args, "from_file", None) is not None:
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
            "error: clipboard is empty; copy the message first, or use --from-file",
            file=sys.stderr,
        )
        return None
    return text


def _ensure_steps_gitignore(deps: Deps, steps_root: Path) -> None:
    """Write `steps/.gitignore` if missing."""
    gitignore = steps_root / ".gitignore"
    if deps.fs.exists(gitignore):
        return
    deps.fs.write_text(
        gitignore,
        "# Session artifacts: messages, apply logs, reports.\n*\n!.gitignore\n",
    )


__all__ = ["cmd_apply"]
