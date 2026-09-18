"""`dwch verify NN` — run checks, commit, produce the report.

The report is written to `steps/{phase}/report-NN.txt` and
optionally copied to the clipboard. It is the only channel through
which the AI learns what happened, so it is deliberately complete:
every check's full stdout and stderr, the commit hash on success,
and any deviations recorded against the roadmap.

On any required check failing, the commit is skipped but the report
is still written. The AI needs to see the failure to fix it.

On success, `verify` updates `state.toml` (current_step,
roadmap_step, last_commit_date) before committing, so the state
file is included in the same commit as the step's files. If the
commit itself fails, state is restored and only the report is left
behind — a failed verify must not leave the tree in a state that
looks verified.

Auto-deviations are computed in memory on every run, so the report
always shows them, but they are written to disk only when the run
succeeds. A failed run must not leave the tree dirty. A step that
declares a blocker suppresses auto-deviations: the missing files
are intentional, and an extra `missing-file` entry would only add
noise.
"""

from __future__ import annotations

import contextlib
import sys
from argparse import Namespace
from pathlib import Path, PurePosixPath

from ...domain.models import CheckResult, Deviation, FileSpec, Report, Roadmap
from ...domain.rules import (
    has_blocker,
    is_development_phase,
    is_planning_phase,
    is_roadmap_frozen,
    is_substantive,
    is_unset_phase,
)
from ...shared.errors import FormatError, HarnessError
from .. import deviations as dev_mod
from .. import lock as lock_mod
from .. import roadmap as roadmap_mod
from ..config import load_config
from ..deps import Deps
from ..format import (
    format_step,
    parse_step_arg,
    parse_step_message,
    render_report,
    summarize_check,
    validate_paths,
)
from ..state import load_state, now_iso, save_state, with_updates
from ..verify_checks import (
    check_architecture_lock,
    check_compile,
    check_roadmap_files,
    check_roadmap_interfaces,
    check_roadmap_step,
    compute_auto_deviations,
    run_configured,
)


def cmd_verify(args: Namespace, deps: Deps) -> int:
    """Verify a step. Returns 0 on success, 1 on check failure, 2 on error."""
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
    steps_dir = (
        deps.project_root / config.paths.get("steps", "steps") / state.current_phase
    )
    step_file = steps_dir / f"step-{tag}.txt"
    apply_log_path = steps_dir / f"apply-{tag}.log"

    if not deps.fs.exists(step_file):
        print(f"error: {step_file} not found; run `apply` first", file=sys.stderr)
        return 2

    step_text = deps.fs.read_text(step_file)
    specs = _parse_step_or_none(step_text)
    if specs is None:
        print(
            f"error: {step_file.name} contains no valid FILE blocks. "
            "The preceding `apply` failed to parse it. "
            "Re-run `apply` with a valid message before verifying.",
            file=sys.stderr,
        )
        return 2

    # The step file may have been edited by hand after `apply`. Its
    # paths were validated when it was written, but not since. Run
    # the same validation here before any path is used.
    try:
        validate_paths(specs, deps.project_root)
    except FormatError as exc:
        print(
            f"error: {step_file.name} contains an unsafe path: {exc}",
            file=sys.stderr,
        )
        return 2

    missing = [s.path for s in specs if not deps.fs.is_file(deps.project_root / s.path)]
    if missing:
        print(
            "error: step references files that do not exist on disk: "
            + ", ".join(missing)
            + ". Run `apply` again.",
            file=sys.stderr,
        )
        return 2

    apply_log = (
        deps.fs.read_text(apply_log_path).rstrip()
        if deps.fs.exists(apply_log_path)
        else ""
    )

    roadmap_path = deps.project_root / config.roadmap.get(
        "path", ".harness/roadmap.toml"
    )
    roadmap = _load_roadmap_or_none(deps, roadmap_path)

    is_planning = is_planning_phase(state)
    is_development = is_development_phase(state)
    dev_dir = deps.project_root / config.roadmap.get(
        "deviations_path", ".harness/deviations"
    )

    checks: list[CheckResult] = []

    if is_planning:
        checks.extend(_planning_checks(specs, deps, config, roadmap))
    elif is_development:
        checks.extend(
            _development_checks(step_num, deps, config, state, roadmap, specs)
        )
    else:
        print(
            "error: no phase is active. Run `dwch new-phase NAME --kind ...` first.",
            file=sys.stderr,
        )
        return 2

    # A development phase that says it is frozen must actually be
    # frozen. A missing roadmap file is a real problem: the roadmap
    # checks would be silently skipped. Report it as a required
    # check so the report explains the situation.
    if is_development and is_roadmap_frozen(state) and roadmap is None:
        checks.append(
            CheckResult(
                name="roadmap-missing",
                command=("roadmap-missing",),
                exit_code=1,
                stdout=(
                    f"state says frozen, but "
                    f"{roadmap_path.relative_to(deps.project_root)} "
                    "was not found or could not be parsed"
                ),
                stderr="",
                required=True,
            )
        )

    for check in checks:
        print(summarize_check(check))

    all_required_ok = all(c.exit_code == 0 for c in checks if c.required)

    # Declared deviations are read before auto-detection: a blocker
    # is a deliberate "I cannot do this", and auto-flagging the
    # missing files on top of it would only add noise.
    declared = dev_mod.load_step(deps.fs, dev_dir, step_num)

    auto_devs: list[Deviation] = []
    if (
        is_development
        and is_roadmap_frozen(state)
        and roadmap is not None
        and not has_blocker(declared)
    ):
        current = roadmap_mod.find_step(roadmap, state.roadmap_step + 1)
        if current is not None:
            auto_devs = compute_auto_deviations(specs, current)

    before_step = state.roadmap_step
    after_step = before_step
    commit_hash: str | None = None
    commit_message: str | None = None

    if all_required_ok:
        commit_message = f"step {tag}: applied and verified"
        if auto_devs:
            dev_mod.write_auto(deps.fs, dev_dir, step_num, auto_devs)
        advance_roadmap = (
            is_development
            and is_roadmap_frozen(state)
            and roadmap is not None
            and is_substantive(specs)
        )
        updated = with_updates(
            state,
            current_step=step_num,
            last_commit_date=now_iso(),
            roadmap_step=state.roadmap_step + (1 if advance_roadmap else 0),
        )
        save_state(deps.fs, deps.project_root, updated)
        if advance_roadmap:
            after_step = before_step + 1
        try:
            commit_hash = deps.git.commit_all(deps.project_root, commit_message)
        except HarnessError as exc:
            # Commit failed: the tree is dirty, state already moved,
            # and auto-deviations were written. Undo state and the
            # auto-deviation file, then stop with a non-zero code.
            # The report is still produced below so the user can see
            # the checks that ran.
            save_state(deps.fs, deps.project_root, state)
            if auto_devs:
                auto_path = dev_dir / f"step-{step_num:02d}-auto.toml"
                with contextlib.suppress(HarnessError):
                    deps.fs.unlink(auto_path)
            after_step = before_step
            commit_message = None
            print(f"error: commit failed: {exc}", file=sys.stderr)
            print("state was restored; tree is dirty", file=sys.stderr)
            all_required_ok = False

    if commit_hash:
        print(f"commit: {commit_hash}")
    elif not all_required_ok:
        print("commit: skipped")

    all_devs = tuple(declared) + tuple(auto_devs)
    report = Report(
        step_number=step_num,
        apply_log=apply_log,
        checks=tuple(checks),
        commit_hash=commit_hash,
        commit_message=commit_message,
        deviations=all_devs,
        roadmap_position=(before_step, after_step) if is_development else None,
        notes="",
        question="",
    )
    rendered = render_report(report)
    report_path = steps_dir / f"report-{tag}.txt"
    deps.fs.write_text(report_path, rendered)
    print(f"report: {report_path}")

    if args.clipboard:
        if deps.clipboard.write(rendered):
            print("report copied to clipboard", file=sys.stderr)
        else:
            print("warning: clipboard unavailable", file=sys.stderr)

    return 0 if all_required_ok else 1


def _load_roadmap_or_none(deps: Deps, path: Path) -> Roadmap | None:
    """Load the roadmap if present; warn on stderr and return None.

    Mirrors the bootstrap behaviour. A roadmap that exists but
    cannot be parsed is a real problem for the session: the roadmap
    checks would be skipped silently, and the coder might not
    notice. Warning on stderr surfaces the problem without changing
    the exit code, because a phase may legitimately be running
    without a roadmap (e.g. a development phase started before
    freezing).
    """
    if not deps.fs.exists(path):
        return None
    try:
        return roadmap_mod.load(deps.fs, path)
    except HarnessError as exc:
        print(f"warning: could not load roadmap: {exc}", file=sys.stderr)
        return None


def _parse_step_or_none(text: str) -> list[FileSpec] | None:
    """Parse a step message, returning `None` on any format error.

    Distinguishes "the message had no FILE blocks" from "the message
    had blocks, but one was malformed". Both are errors for verify,
    but the caller's message benefits from knowing which.
    """
    try:
        return parse_step_message(text)
    except FormatError:
        return None


def _planning_checks(
    specs: list[FileSpec],
    deps: Deps,
    config,
    roadmap,
) -> list[CheckResult]:
    """Checks that run only in a planning phase.

    A roadmap written by the architect is validated structurally so
    that a malformed file cannot be frozen. The roadmap path is
    resolved from config, not hard-coded. Paths are compared as
    `PurePosixPath` on both sides so that `.harness//roadmap.toml`
    and `.harness/roadmap.toml` compare equal.
    """
    out: list[CheckResult] = []

    roadmap_rel = PurePosixPath(
        str(config.roadmap.get("path", ".harness/roadmap.toml")).replace("\\", "/")
    )
    wrote_roadmap = any(
        PurePosixPath(s.path.replace("\\", "/")) == roadmap_rel for s in specs
    )
    if wrote_roadmap:
        if roadmap is None:
            out.append(
                CheckResult(
                    name="roadmap-structure",
                    command=("roadmap-structure",),
                    exit_code=1,
                    stdout="",
                    stderr="roadmap file was written but could not be parsed",
                    required=True,
                )
            )
        else:
            problems = roadmap_mod.validate(roadmap)
            out.append(
                CheckResult(
                    name="roadmap-structure",
                    command=("roadmap-structure",),
                    exit_code=0 if not problems else 1,
                    stdout="\n".join(problems) if problems else "ok",
                    stderr="",
                    required=True,
                )
            )

    out.extend(run_configured(list(config.planning_commands), deps))
    return out


def _development_checks(
    step_num: int,
    deps: Deps,
    config,
    state,
    roadmap,
    specs: list[FileSpec],
) -> list[CheckResult]:
    """Checks that run only in a development phase."""
    out: list[CheckResult] = [check_compile(specs, deps)]

    if is_roadmap_frozen(state) and roadmap is not None:
        out.append(check_roadmap_step(step_num, state, roadmap))
        current = roadmap_mod.find_step(roadmap, state.roadmap_step + 1)
        if current is not None:
            out.append(check_roadmap_files(specs, current))
            out.append(
                check_roadmap_interfaces(
                    deps.fs, deps.project_root, specs, current, roadmap
                )
            )

        roadmap_path = deps.project_root / config.roadmap.get(
            "path", ".harness/roadmap.toml"
        )
        lock_path = deps.project_root / config.roadmap.get(
            "lock_path", ".harness/roadmap.lock"
        )
        architecture_paths = [
            deps.project_root / p for p in config.context.get("architecture", [])
        ]
        lock = lock_mod.load(deps.fs, lock_path)
        arch_check = check_architecture_lock(
            deps.fs,
            lock,
            deps.project_root,
            roadmap_path,
            architecture_paths,
            required=bool(config.roadmap.get("lock_required", False)),
        )
        if arch_check is not None:
            out.append(arch_check)

    out.extend(run_configured(list(config.verify_commands), deps))
    return out


__all__ = ["cmd_verify"]
