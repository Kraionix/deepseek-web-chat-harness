"""Built-in verify checks and the configured-command runner.

All checks return a `CheckResult` so `render_report` and
`summarize_check` do not need to know where the result came from.

`task-changes` and `compile` and `plan-structure` are required: a
task that does not deliver the files the plan promised must not
commit. `task-interfaces` is non-required: it informs the report
without blocking the commit, because interface drift is often
transient (a symbol may appear on a later task).
"""

from __future__ import annotations

from pathlib import Path

from ..domain.models import (
    CheckResult,
    DeleteOp,
    MoveOp,
    Plan,
    StepOp,
    Task,
    WriteOp,
)
from ..shared.errors import HarnessError
from . import module_map
from . import plan as plan_mod
from .deps import Deps
from .ports import FilesystemPort


def check_compile(ops: list[StepOp], deps: Deps) -> CheckResult:
    """Run `compile()` on every `.py` file the task writes.

    `WriteOp.path` and `MoveOp.dst` are compiled; `DeleteOp.path`
    and `MoveOp.src` are not, because those files no longer exist.
    Reports syntax errors as `exit_code=1` with a per-file list in
    `stdout`. Files that do not end in `.py` are ignored; if none
    remain, the check passes with `(no python files)`.
    """
    py_files: list[str] = []
    for op in ops:
        if isinstance(op, WriteOp) and op.path.endswith(".py"):
            py_files.append(op.path)
        elif isinstance(op, MoveOp) and op.dst.endswith(".py"):
            py_files.append(op.dst)

    if not py_files:
        return CheckResult(
            name="compile",
            command=("compile",),
            exit_code=0,
            stdout="(no python files)",
            stderr="",
            required=True,
        )
    lines: list[str] = []
    failed = False
    for rel in py_files:
        target = deps.project_root / rel
        try:
            source = deps.fs.read_text(target)
        except HarnessError as exc:
            failed = True
            lines.append(f"{rel}: {exc}")
            continue
        try:
            compile(source, str(target), "exec")
        except (SyntaxError, ValueError) as exc:
            failed = True
            lines.append(f"{rel}: {exc}")
    return CheckResult(
        name="compile",
        command=("compile",),
        exit_code=1 if failed else 0,
        stdout="\n".join(lines),
        stderr="",
        required=True,
    )


def check_task_changes(ops: list[StepOp], task: Task) -> CheckResult:
    """Compare written, deleted, and moved files against the task.

    Three sets are compared, each producing `extra-*` and
    `missing-*`:

    - written: `WriteOp.path` vs `task.files`;
    - deleted: `DeleteOp.path` vs `task.removes`;
    - moves:   `(MoveOp.src, MoveOp.dst)` vs `task.moves`.

    A `MoveOp` contributes only to the `moved` set. It does not
    also count as a write of its destination or a delete of its
    source: the plan schema tracks a rename as one move, and the
    intersection rules in `plan.validate` would forbid the
    duplication anyway.

    Deviation files (`.harness/deviations/...`) are never counted
    as extra: they are the mechanism by which the coder talks back
    to the plan.

    Required: a task whose file set does not match the plan must
    not commit.
    """
    written: set[str] = set()
    deleted: set[str] = set()
    moved: set[tuple[str, str]] = set()
    for op in ops:
        if isinstance(op, WriteOp):
            p = op.path.replace("\\", "/")
            if p.startswith(".harness/deviations/"):
                continue
            written.add(p)
        elif isinstance(op, DeleteOp):
            deleted.add(op.path.replace("\\", "/"))
        elif isinstance(op, MoveOp):
            src = op.src.replace("\\", "/")
            dst = op.dst.replace("\\", "/")
            moved.add((src, dst))

    expected_written = {p.replace("\\", "/") for p in task.files}
    expected_deleted = {p.replace("\\", "/") for p in task.removes}
    expected_moved = {
        (s.replace("\\", "/"), d.replace("\\", "/")) for s, d in task.moves
    }

    diffs: list[str] = []
    for label, extra, missing in (
        (
            "written",
            sorted(written - expected_written),
            sorted(expected_written - written),
        ),
        (
            "deleted",
            sorted(deleted - expected_deleted),
            sorted(expected_deleted - deleted),
        ),
    ):
        if extra:
            diffs.append(f"extra {label}:   " + ", ".join(extra))
        if missing:
            diffs.append(f"missing {label}: " + ", ".join(missing))
    extra_moves = sorted(moved - expected_moved)
    missing_moves = sorted(expected_moved - moved)
    if extra_moves:
        diffs.append(
            "extra moves:   " + ", ".join(f"{s} -> {d}" for s, d in extra_moves)
        )
    if missing_moves:
        diffs.append(
            "missing moves: " + ", ".join(f"{s} -> {d}" for s, d in missing_moves)
        )

    ok = not diffs
    if ok:
        diffs.append("changes match")
    return CheckResult(
        name="task-changes",
        command=("task-changes",),
        exit_code=0 if ok else 1,
        stdout="\n".join(diffs),
        stderr="",
        required=True,
    )


def check_task_interfaces(
    fs: FilesystemPort,
    project_root: Path,
    ops: list[StepOp],
    task: Task,
    plan: Plan,
) -> CheckResult:
    """Check that declared interfaces appear in the written files.

    Missing symbols are reported. Extra public symbols are not: the
    coder may legitimately add helpers. Only interfaces whose
    `module` is present after the task's ops are checked.

    Non-required: interface drift is often transient, so a missing
    symbol is a warning, not a blocker.
    """
    if not task.interfaces:
        return CheckResult(
            name="task-interfaces",
            command=("task-interfaces",),
            exit_code=0,
            stdout="(no interfaces declared for this task)",
            stderr="",
            required=False,
        )

    by_name = {i.name: i for i in plan.interfaces}
    expected_modules: dict[str, set[str]] = {}
    for name in task.interfaces:
        iface = by_name.get(name)
        if iface is None or not iface.module:
            continue
        expected_modules.setdefault(iface.module, set()).add(name)

    missing: list[str] = []
    for module_path, names in expected_modules.items():
        full = project_root / module_path
        found = module_map.extract_public_symbols(fs, full)
        for name in sorted(names):
            if name not in found:
                missing.append(f"{module_path}: {name}")

    ok = not missing
    return CheckResult(
        name="task-interfaces",
        command=("task-interfaces",),
        exit_code=0 if ok else 1,
        stdout="\n".join(missing) if missing else "interfaces present",
        stderr="",
        required=False,
    )


def check_plan_structure(plan: Plan, project_root: Path | None) -> CheckResult:
    """Run `plan.validate` and wrap the result in a `CheckResult`.

    Called by `verify` in a planning phase, only when the current
    task writes `plan.toml`. A structurally invalid plan fails the
    check and blocks the commit; the phase cannot be closed and the
    plan cannot be frozen while the check fails.
    """
    problems = plan_mod.validate(plan, project_root)
    return CheckResult(
        name="plan-structure",
        command=("plan-structure",),
        exit_code=0 if not problems else 1,
        stdout="\n".join(problems) if problems else "ok",
        stderr="",
        required=True,
    )


def run_configured(specs: list[dict], deps: Deps) -> list[CheckResult]:
    """Run every configured command and return the results.

    Pre:  `specs` is a list of `{name, command, required}` dicts.
          `config.load_config` guarantees `command` is a non-empty
          list of strings when the key is present.
    Post: one `CheckResult` per spec, in order. A spec with an empty
          command yields `exit_code=1` with an explanatory `stderr`.
    """
    return [_run_one(spec, deps) for spec in specs]


def _run_one(spec: dict, deps: Deps) -> CheckResult:
    name = str(spec.get("name", "unnamed"))
    command = tuple(spec.get("command", []))
    required = bool(spec.get("required", True))
    if not command:
        return CheckResult(
            name=name,
            command=(),
            exit_code=1,
            stdout="",
            stderr="(no command configured)",
            required=required,
        )
    try:
        result = deps.process.run(list(command), cwd=deps.project_root)
    except HarnessError as exc:
        return CheckResult(
            name=name,
            command=command,
            exit_code=127,
            stdout="",
            stderr=str(exc),
            required=required,
        )
    return CheckResult(
        name=name,
        command=command,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        required=required,
    )


__all__ = [
    "check_compile",
    "check_plan_structure",
    "check_task_changes",
    "check_task_interfaces",
    "run_configured",
]
