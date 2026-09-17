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
file is included in the same commit as the step's files.

Auto-deviations are computed in memory on every run, so the report
always shows them, but they are written to disk only when the run
succeeds. A failed run must not leave the tree dirty. A step that
declares a blocker suppresses auto-deviations: the missing files
are intentional, and an extra `missing-file` entry would only add
noise.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from datetime import UTC, datetime

from ...domain.models import CheckResult, Deviation, FileSpec, Report
from ...domain.rules import has_blocker, is_substantive
from ...shared.errors import FormatError, HarnessError
from .. import deviations as dev_mod
from .. import lock as lock_mod
from .. import roadmap as roadmap_mod
from ..config import load_config
from ..deps import Deps
from ..format import (
    parse_step_message,
    render_report,
    summarize_check,
)
from ..state import load_state, save_state, with_updates
from ..verify_checks import (
    check_architecture_lock,
    check_compile,
    check_roadmap_files,
    check_roadmap_interfaces,
    check_roadmap_step,
    compute_auto_deviations,
    run_configured,
)


def cmd_verify(args: Namespace, deps: Deps, _config) -> int:
    """Verify a step. Returns 0 on success, 1 on check failure, 2 on error."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if state.current_phase == "unset" or state.phase_kind == "unset":
        print(
            "error: no active phase; run "
            "`dwch new-phase NAME --kind {planning|development}` first",
            file=sys.stderr,
        )
        return 2

    steps_dir = (
        deps.project_root / config.paths.get("steps", "steps") / state.current_phase
    )
    step_file = steps_dir / f"step-{args.step}.txt"
    apply_log_path = steps_dir / f"apply-{args.step}.log"

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

    missing = [s.path for s in specs if not (deps.project_root / s.path).is_file()]
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
    roadmap = None
    if deps.fs.exists(roadmap_path):
        try:
            roadmap = roadmap_mod.load(deps.fs, roadmap_path)
        except HarnessError:
            roadmap = None

    is_planning = state.phase_kind == "planning"
    is_development = state.phase_kind == "development"
    dev_dir = deps.project_root / config.roadmap.get(
        "deviations_path", ".harness/deviations"
    )

    checks: list[CheckResult] = []

    if is_planning:
        checks.extend(_planning_checks(specs, deps, config, roadmap))
    elif is_development:
        checks.extend(_development_checks(args, deps, config, state, roadmap, specs))
    else:
        print(
            "error: no phase is active. Run `dwch new-phase NAME --kind ...` first.",
            file=sys.stderr,
        )
        return 2

    for check in checks:
        print(summarize_check(check))

    all_required_ok = all(c.exit_code == 0 for c in checks if c.required)

    # Declared deviations are read before auto-detection: a blocker
    # is a deliberate "I cannot do this", and auto-flagging the
    # missing files on top of it would only add noise.
    declared = dev_mod.load_step(deps.fs, dev_dir, int(args.step))

    auto_devs: list[Deviation] = []
    if (
        is_development
        and state.roadmap_frozen
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
        commit_message = f"step {args.step}: applied and verified"
        if auto_devs:
            dev_mod.write_auto(deps.fs, dev_dir, int(args.step), auto_devs)
        now = datetime.now(UTC).isoformat(timespec="seconds")
        advance_roadmap = (
            is_development
            and state.roadmap_frozen
            and roadmap is not None
            and is_substantive(specs)
        )
        updated = with_updates(
            state,
            current_step=int(args.step),
            last_commit_date=now,
            roadmap_step=state.roadmap_step + (1 if advance_roadmap else 0),
        )
        save_state(deps.fs, deps.project_root, updated)
        if advance_roadmap:
            after_step = before_step + 1
        try:
            commit_hash = deps.git.commit_all(deps.project_root, commit_message)
        except HarnessError as exc:
            print(f"warning: commit failed: {exc}", file=sys.stderr)

    if commit_hash:
        print(f"commit: {commit_hash}")
    elif not all_required_ok:
        print("commit: skipped (required check failed)")

    all_devs = tuple(declared) + tuple(auto_devs)
    report = Report(
        step_number=int(args.step),
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
    report_path = steps_dir / f"report-{args.step}.txt"
    deps.fs.write_text(report_path, rendered)
    print(f"report: {report_path}")

    if args.clipboard:
        if deps.clipboard.write(rendered):
            print("report copied to clipboard", file=sys.stderr)
        else:
            print("warning: clipboard unavailable", file=sys.stderr)

    return 0 if all_required_ok else 1


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
    resolved from config, not hard-coded.
    """
    out: list[CheckResult] = []

    roadmap_rel = str(config.roadmap.get("path", ".harness/roadmap.toml")).replace(
        "\\", "/"
    )
    wrote_roadmap = any(s.path.replace("\\", "/") == roadmap_rel for s in specs)
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
    args: Namespace,
    deps: Deps,
    config,
    state,
    roadmap,
    specs: list[FileSpec],
) -> list[CheckResult]:
    """Checks that run only in a development phase."""
    out: list[CheckResult] = [check_compile(specs, deps)]

    if state.roadmap_frozen and roadmap is not None:
        out.append(check_roadmap_step(int(args.step), state))
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
