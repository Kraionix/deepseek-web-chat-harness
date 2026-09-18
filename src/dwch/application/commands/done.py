"""`dwch done` — close the current task.

Requires `state.verify.ok` for the current task. Commits the task
as `task {id}: applied and verified`. In development, advances
`state.plan.position`; when the last task is done, closes the
phase with a second commit and — in planning — freezes the plan by
computing its SHA-256 and recording it in state.

A planning phase has one logical task; `done` always closes it.
If `plan.toml` is present and valid, it is frozen in the same
series of commits.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...domain.rules import is_planning_phase, is_unset_phase
from ...shared.errors import HarnessError, PlanError
from .. import plan as plan_mod
from ..config import load_config
from ..deps import Deps
from ..state import (
    advance_position,
    load_state,
    now_iso,
    reset_failure,
    save_state,
    set_phase_closed,
    set_plan_frozen,
    with_updates,
)


def cmd_done(_args: Namespace, deps: Deps) -> int:
    """Close the current task. Returns 0 or 2."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if is_unset_phase(state):
        print("error: no active phase", file=sys.stderr)
        return 2

    if not state.verify_ok:
        print(
            "error: current task is not verified; run `dwch verify` first",
            file=sys.stderr,
        )
        return 2

    plan_path = deps.project_root / config.plan["path"]
    is_planning = is_planning_phase(state)
    plan = None

    if is_planning:
        task_id = state.verify_task_id or "planning"
    else:
        if not deps.fs.exists(plan_path):
            print(f"error: plan not found: {plan_path}", file=sys.stderr)
            return 2
        try:
            plan = plan_mod.load(deps.fs, plan_path)
        except HarnessError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if state.plan_position >= len(plan.tasks):
            print("error: plan is exhausted", file=sys.stderr)
            return 2
        task = plan.tasks[state.plan_position]
        task_id = task.id
        if state.verify_task_id and state.verify_task_id != task_id:
            print(
                f"error: verify was for {state.verify_task_id!r}, "
                f"current task is {task_id!r}",
                file=sys.stderr,
            )
            return 2

    # Advance and persist; the task commit will include state.toml.
    if is_planning:
        advanced = reset_failure(state)
    else:
        advanced = advance_position(reset_failure(state))
    save_state(deps.fs, deps.project_root, advanced)

    try:
        task_commit = deps.git.commit_all(
            deps.project_root, f"task {task_id}: applied and verified"
        )
        print(f"commit: {task_commit}")
    except HarnessError as exc:
        # Restore state; the task did not advance.
        save_state(deps.fs, deps.project_root, state)
        print(f"error: commit failed: {exc}", file=sys.stderr)
        print("state was restored; the task was not closed", file=sys.stderr)
        return 2

    # Determine whether the phase closes.
    if is_planning:
        rc = _freeze_if_possible(deps, plan_path)
        if rc is None:
            return 2
        closing = True
    else:
        assert plan is not None
        closing = advanced.plan_position >= len(plan.tasks)

    if not closing:
        return 0

    # Reload: `_freeze_if_possible` writes state itself, and the
    # close must reflect the frozen fields.
    current = load_state(deps.fs, deps.project_root)
    now = now_iso()
    final = set_phase_closed(current, now)
    final = with_updates(final, last_commit=task_commit, last_commit_date=now)
    save_state(deps.fs, deps.project_root, final)

    try:
        close_commit = deps.git.commit_all(
            deps.project_root, f"chore: close phase {state.phase_name}"
        )
        print(f"commit: {close_commit}")
    except HarnessError as exc:
        print(f"error: close commit failed: {exc}", file=sys.stderr)
        return 2

    print(f"phase {state.phase_name} closed")
    return 0


def _freeze_if_possible(deps: Deps, plan_path) -> bool | None:
    """Freeze the plan if it exists and is valid.

    Returns None (after printing an error) when the plan file exists
    but is invalid: the phase must not close on a broken plan.
    Returns True otherwise. A missing plan file is not an error: a
    planner may close a phase that only produced design documents.
    """
    if not deps.fs.exists(plan_path):
        return True
    try:
        plan = plan_mod.load(deps.fs, plan_path)
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None
    problems = plan_mod.validate(plan, deps.project_root)
    if problems:
        print("error: plan is not structurally valid:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return None
    sha = plan_mod.sha256(deps.fs, plan_path)
    state = load_state(deps.fs, deps.project_root)
    frozen = set_plan_frozen(state, plan.meta.version, sha)
    save_state(deps.fs, deps.project_root, frozen)
    print(f"frozen plan v{plan.meta.version} sha {sha[:12]}")
    return True


__all__ = ["cmd_done"]
