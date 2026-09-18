"""`dwch verify` — run checks, produce the report, hint on failure.

Checks are derived from the current task's spec. On success,
`state.verify.ok` becomes True and the report is written. On
failure, `state.failure` is updated, the failure count for the
current task is incremented, and a short hint is placed on the
clipboard.

`verify` never commits. Committing is `done`'s job, and only after
`verify` says the tree is in a good state.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...domain.models import CheckResult, Report
from ...domain.rules import is_planning_phase, is_unset_phase
from ...shared.errors import FormatError, HarnessError
from ...shared.paths import normalize_rel
from .. import plan as plan_mod
from ..config import load_config
from ..deps import Deps
from ..format import (
    parse_step_message,
    render_hint,
    render_report,
    summarize_check,
    validate_paths,
)
from ..state import (
    load_state,
    now_iso,
    save_state,
    set_verify_fail,
    set_verify_ok,
)
from ..verify_checks import (
    check_compile,
    check_plan_structure,
    check_task_changes,
    check_task_interfaces,
    run_configured,
)


def cmd_verify(args: Namespace, deps: Deps) -> int:
    """Verify the current task. Returns 0, 1, or 2."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if is_unset_phase(state):
        print('error: no active phase; run `dwch start "goal"` first', file=sys.stderr)
        return 2

    task_id, task_or_none = _current_task(state, deps, config)
    if task_id is None:
        print(
            "error: no current task; the plan is missing or exhausted",
            file=sys.stderr,
        )
        return 2

    steps_dir = (
        deps.project_root
        / config.paths.get("steps", "steps")
        / state.phase_name
        / task_id
    )
    message_path = steps_dir / "message.txt"
    if not deps.fs.exists(message_path):
        print(
            f"error: {message_path} not found; run `dwch apply` first",
            file=sys.stderr,
        )
        return 2

    try:
        ops = parse_step_message(deps.fs.read_text(message_path))
        validate_paths(ops, deps.project_root)
    except FormatError as exc:
        print(
            f"error: {message_path.name} contains no valid blocks: {exc}",
            file=sys.stderr,
        )
        return 2

    apply_log = ""
    log_path = steps_dir / "apply.log"
    if deps.fs.exists(log_path):
        apply_log = deps.fs.read_text(log_path).rstrip()

    checks: list[CheckResult] = [check_compile(ops, deps)]

    plan_path = deps.project_root / config.plan["path"]
    if is_planning_phase(state):
        checks.extend(_planning_checks(ops, deps, config, plan_path))
        checks.extend(run_configured(list(config.planning_commands), deps))
    else:
        plan = None
        if deps.fs.exists(plan_path):
            try:
                plan = plan_mod.load(deps.fs, plan_path)
            except HarnessError as exc:
                print(f"warning: could not load plan: {exc}", file=sys.stderr)
        if plan is not None and task_or_none is not None:
            checks.append(check_task_changes(ops, task_or_none))
            checks.append(
                check_task_interfaces(
                    deps.fs, deps.project_root, ops, task_or_none, plan
                )
            )
        checks.extend(run_configured(list(config.verify_commands), deps))

    for check in checks:
        print(summarize_check(check))

    all_ok = all(c.exit_code == 0 for c in checks if c.required)

    attempt = state.failure_count + 1 if state.failure_task_id == task_id else 1

    if all_ok:
        fresh = set_verify_ok(state, task_id, now_iso())
        save_state(deps.fs, deps.project_root, fresh)
    else:
        first_fail = next((c for c in checks if c.exit_code != 0 and c.required), None)
        check_name = first_fail.name if first_fail else "unknown"
        excerpt = ""
        if first_fail is not None:
            text = (first_fail.stdout or "") + (first_fail.stderr or "")
            excerpt = text.strip()[:500]
        fresh = set_verify_fail(state, task_id, check_name, excerpt, now_iso())
        save_state(deps.fs, deps.project_root, fresh)

    report = Report(
        task_id=task_id,
        attempt=attempt,
        apply_log=apply_log,
        checks=tuple(checks),
        commit_hash=None,
        commit_message=None,
        deviations=(),
        plan_position=None,
        notes="",
        question="",
    )
    rendered = render_report(report)
    report_path = steps_dir / f"report-{attempt}.txt"
    deps.fs.write_text(report_path, rendered)
    print(f"report: {report_path}")

    if not all_ok:
        hint = render_hint(report)
        if deps.clipboard.write(hint):
            print("hint copied to clipboard", file=sys.stderr)
        else:
            print("warning: clipboard unavailable", file=sys.stderr)
    elif getattr(args, "clipboard", False):
        if deps.clipboard.write(rendered):
            print("report copied to clipboard", file=sys.stderr)
        else:
            print("warning: clipboard unavailable", file=sys.stderr)

    return 0 if all_ok else 1


def _current_task(state, deps: Deps, config):
    """Return `(task_id, task_or_none)` for the current position."""
    if is_planning_phase(state):
        return "planning", None
    plan_path = deps.project_root / config.plan["path"]
    if not deps.fs.exists(plan_path):
        return None, None
    plan = plan_mod.load(deps.fs, plan_path)
    if state.plan_position < 0 or state.plan_position >= len(plan.tasks):
        return None, None
    task = plan.tasks[state.plan_position]
    return task.id, task


def _planning_checks(ops, deps: Deps, config, plan_path) -> list[CheckResult]:
    """Checks that run in a planning phase.

    A plan written by the planner is validated structurally so that
    a malformed file cannot be frozen. The check runs only when the
    current task writes the plan file.
    """
    out: list[CheckResult] = []
    plan_rel = normalize_rel(str(config.plan["path"]))
    wrote_plan = any(
        normalize_rel(op.path) == plan_rel
        for op in ops
        if hasattr(op, "path") and not hasattr(op, "src")
    )
    if not wrote_plan:
        return out
    if not deps.fs.exists(plan_path):
        out.append(
            CheckResult(
                name="plan-structure",
                command=("plan-structure",),
                exit_code=1,
                stdout="",
                stderr="plan file was written but could not be parsed",
                required=True,
            )
        )
        return out
    try:
        plan = plan_mod.load(deps.fs, plan_path)
    except HarnessError as exc:
        out.append(
            CheckResult(
                name="plan-structure",
                command=("plan-structure",),
                exit_code=1,
                stdout="",
                stderr=str(exc),
                required=True,
            )
        )
        return out
    out.append(check_plan_structure(plan, deps.project_root))
    return out


__all__ = ["cmd_verify"]
