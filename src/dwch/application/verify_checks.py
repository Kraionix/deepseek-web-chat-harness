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
    Deviation,
    DeviationType,
    FileSpec,
    Lock,
    Roadmap,
    RoadmapStep,
    State,
)
from ..shared.errors import HarnessError
from . import lock as lock_mod
from . import module_map
from .deps import Deps
from .ports import FilesystemPort


def check_compile(specs: list[FileSpec], deps: Deps) -> CheckResult:
    """Run `compile()` on every `.py` file listed in the step.

    Reports syntax errors as `exit_code=1` with a per-file list in
    `stdout`. Files that do not end in `.py` are ignored; if none
    remain, the check passes with `(no python files)`.

    The source is read through the filesystem port, and `compile()`
    is called directly: it does not print to stdout or stderr, so
    no redirection is needed.
    """
    py_files = [s.path for s in specs if s.path.endswith(".py")]
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


def check_roadmap_step(args_step: int, state: State) -> CheckResult:
    """Verify that `args_step` is the next roadmap position.

    `roadmap_step` counts completed steps, so the expected step is
    `roadmap_step + 1`. A mismatch means the coder skipped or
    repeated a step.
    """
    expected = state.roadmap_step + 1
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


def check_roadmap_files(specs: list[FileSpec], step: RoadmapStep) -> CheckResult:
    """Compare written files against `step.files`.

    Deviation files (`.harness/deviations/...`) are never counted as
    extra: they are the mechanism by which the coder talks back to
    the plan.
    """
    written = {
        s.path.replace("\\", "/")
        for s in specs
        if not s.path.replace("\\", "/").startswith(".harness/deviations/")
    }
    expected = set(step.files)
    extra = sorted(written - expected)
    missing = sorted(expected - written)
    ok = not extra and not missing
    lines: list[str] = []
    if extra:
        lines.append("extra:   " + ", ".join(extra))
    if missing:
        lines.append("missing: " + ", ".join(missing))
    if ok:
        lines.append("files match")
    return CheckResult(
        name="roadmap-files",
        command=("roadmap-files",),
        exit_code=0 if ok else 1,
        stdout="\n".join(lines),
        stderr="",
        required=False,
    )


def check_roadmap_interfaces(
    fs: FilesystemPort,
    project_root: Path,
    specs: list[FileSpec],
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
    Post: one `CheckResult` per spec, in order. A spec with an empty
          command yields `exit_code=1` with an explanatory `stderr`.
    """
    return [_run_one(spec, deps) for spec in specs]


def compute_auto_deviations(
    specs: list[FileSpec],
    step: RoadmapStep,
) -> list[Deviation]:
    """Derive auto-deviations from file-set mismatches.

    Only the file set is checked here. Interface drift is reported
    in the check, not written to `deviations/`: it is often
    transient (a symbol appears on a later step).
    """
    written = {
        s.path.replace("\\", "/")
        for s in specs
        if not s.path.replace("\\", "/").startswith(".harness/deviations/")
    }
    expected = set(step.files)
    out: list[Deviation] = []
    extra = sorted(written - expected)
    missing = sorted(expected - written)
    if extra:
        out.append(
            Deviation(
                type=DeviationType.EXTRA_FILE,
                affected=tuple(extra),
                reason="auto-detected by verify",
                detail="",
                auto=True,
            )
        )
    if missing:
        out.append(
            Deviation(
                type=DeviationType.MISSING_FILE,
                affected=tuple(missing),
                reason="auto-detected by verify",
                detail="",
                auto=True,
            )
        )
    return out


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
    "check_roadmap_files",
    "check_roadmap_interfaces",
    "check_roadmap_step",
    "compute_auto_deviations",
    "run_configured",
]
