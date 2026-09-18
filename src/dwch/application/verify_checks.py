"""Built-in verify checks and configured command runner.

All checks return a `CheckResult` so `render_report` and
`summarize_check` do not need to know where the result came from.
Roadmap checks are non-required by default: they inform the report
without blocking the commit.
"""

from __future__ import annotations

from pathlib import Path

from ..domain.models import (
    CheckResult,
    DeleteOp,
    Deviation,
    DeviationType,
    Lock,
    MoveOp,
    Roadmap,
    RoadmapStep,
    State,
    StepOp,
    WriteOp,
)
from ..shared.errors import HarnessError
from . import lock as lock_mod
from . import module_map
from . import roadmap as roadmap_mod
from .deps import Deps
from .ports import FilesystemPort


def check_compile(ops: list[StepOp], deps: Deps) -> CheckResult:
    """Run `compile()` on every `.py` file the step writes.

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


def check_roadmap_step(
    args_step: int,
    state: State,
    roadmap: Roadmap,
) -> CheckResult:
    """Verify that `args_step` is the next roadmap position.

    `roadmap_step` counts completed steps, so the expected step is
    `roadmap_step + 1`. A mismatch means the coder skipped or
    repeated a step.

    A development phase that runs past the end of its roadmap is a
    protocol error: the expected step does not exist. This is
    reported as a failure rather than silently skipping the
    roadmap-files and roadmap-interfaces checks.
    """
    expected = state.roadmap_step + 1
    if roadmap_mod.find_step(roadmap, expected) is None:
        return CheckResult(
            name="roadmap-step",
            command=("roadmap-step",),
            exit_code=1,
            stdout=(
                f"roadmap step {expected} does not exist; "
                f"roadmap v{roadmap.meta.version} has "
                f"{len(roadmap.steps)} step(s)"
            ),
            stderr="",
            required=True,
        )
    ok = args_step == expected
    return CheckResult(
        name="roadmap-step",
        command=("roadmap-step",),
        exit_code=0 if ok else 1,
        stdout=(
            f"step {args_step} matches roadmap position"
            if ok
            else f"expected roadmap step {expected}, got {args_step}"
        ),
        stderr="",
        required=True,
    )


def check_roadmap_changes(ops: list[StepOp], step: RoadmapStep) -> CheckResult:
    """Compare written, deleted, and moved files against the roadmap.

    Three sets are compared, each producing `extra-*` and
    `missing-*`:

    - written: `WriteOp.path` vs `step.files`;
    - deleted: `DeleteOp.path` vs `step.removes`;
    - moves:   `(MoveOp.src, MoveOp.dst)` vs `step.moves`.

    A `MoveOp` contributes only to the `moved` set. It does not
    also count as a write of its destination or a delete of its
    source: the roadmap schema tracks a rename as one move, and
    the intersection rules in `roadmap.validate` would forbid the
    duplication anyway.

    Deviation files (`.harness/deviations/...`) are never counted
    as extra: they are the mechanism by which the coder talks back
    to the plan.
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

    expected_written = {p.replace("\\", "/") for p in step.files}
    expected_deleted = {p.replace("\\", "/") for p in step.removes}
    expected_moved = {
        (s.replace("\\", "/"), d.replace("\\", "/")) for s, d in step.moves
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
        name="roadmap-changes",
        command=("roadmap-changes",),
        exit_code=0 if ok else 1,
        stdout="\n".join(diffs),
        stderr="",
        required=False,
    )


def check_roadmap_interfaces(
    fs: FilesystemPort,
    project_root: Path,
    ops: list[StepOp],
    step: RoadmapStep,
    roadmap: Roadmap,
) -> CheckResult:
    """Check that declared interfaces appear in the written files.

    Missing symbols are reported. Extra public symbols are not: the
    coder may legitimately add helpers. Only interfaces whose
    `module` is among the written files are checked.
    """
    if not step.interfaces:
        return CheckResult(
            name="roadmap-interfaces",
            command=("roadmap-interfaces",),
            exit_code=0,
            stdout="(no interfaces declared for this step)",
            stderr="",
            required=False,
        )

    by_name = {i.name: i for i in roadmap.interfaces}
    expected_modules: dict[str, set[str]] = {}
    for name in step.interfaces:
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
        name="roadmap-interfaces",
        command=("roadmap-interfaces",),
        exit_code=0 if ok else 1,
        stdout="\n".join(missing) if missing else "interfaces present",
        stderr="",
        required=False,
    )


def check_architecture_lock(
    fs: FilesystemPort,
    lock: Lock | None,
    project_root: Path,
    roadmap_path: Path,
    architecture_paths: list[Path],
    *,
    required: bool,
) -> CheckResult | None:
    """Compare the current frozen files against the lock.

    Returns None when there is no lock. The caller decides whether
    to include the check in the report.
    """
    if lock is None:
        return None
    problems = lock_mod.check(fs, lock, project_root, roadmap_path, architecture_paths)
    ok = not problems
    return CheckResult(
        name="architecture-lock",
        command=("architecture-lock",),
        exit_code=0 if ok else 1,
        stdout="\n".join(problems) if problems else "frozen files match",
        stderr="",
        required=required,
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


def compute_auto_deviations(
    ops: list[StepOp],
    step: RoadmapStep,
) -> list[Deviation]:
    """Derive auto-deviations from the six set diffs.

    A `MoveOp` contributes only to the `moved` set; see
    `check_roadmap_changes` for the reasoning. Only file-set
    mismatches are written to `deviations/`. Interface drift is
    reported in the check, not here: it is often transient (a
    symbol appears on a later step).
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

    expected_written = {p.replace("\\", "/") for p in step.files}
    expected_deleted = {p.replace("\\", "/") for p in step.removes}
    expected_moved = {
        (s.replace("\\", "/"), d.replace("\\", "/")) for s, d in step.moves
    }

    out: list[Deviation] = []
    extra = sorted(written - expected_written)
    missing = sorted(expected_written - written)
    if extra:
        out.append(_auto(DeviationType.EXTRA_FILE, extra))
    if missing:
        out.append(_auto(DeviationType.MISSING_FILE, missing))

    extra_removals = sorted(deleted - expected_deleted)
    missing_removals = sorted(expected_deleted - deleted)
    if extra_removals:
        out.append(_auto(DeviationType.EXTRA_REMOVAL, extra_removals))
    if missing_removals:
        out.append(_auto(DeviationType.MISSING_REMOVAL, missing_removals))

    extra_moves = sorted(moved - expected_moved)
    missing_moves = sorted(expected_moved - moved)
    if extra_moves:
        out.append(
            Deviation(
                type=DeviationType.EXTRA_MOVE,
                affected=tuple(f"{s} -> {d}" for s, d in extra_moves),
                reason="auto-detected by verify",
                detail="",
                auto=True,
            )
        )
    if missing_moves:
        out.append(
            Deviation(
                type=DeviationType.MISSING_MOVE,
                affected=tuple(f"{s} -> {d}" for s, d in missing_moves),
                reason="auto-detected by verify",
                detail="",
                auto=True,
            )
        )
    return out


def _auto(dtype: DeviationType, paths: list[str]) -> Deviation:
    """Build an auto deviation for a path list."""
    return Deviation(
        type=dtype,
        affected=tuple(paths),
        reason="auto-detected by verify",
        detail="",
        auto=True,
    )


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
    "check_architecture_lock",
    "check_compile",
    "check_roadmap_changes",
    "check_roadmap_interfaces",
    "check_roadmap_step",
    "compute_auto_deviations",
    "run_configured",
]
