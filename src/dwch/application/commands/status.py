"""`dwch status` — print the current state in a compact form.

Read-only. Prints phase, plan position, deviations, verify result,
and failure info. Intended as a quick check between commands.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...shared.errors import HarnessError
from .. import deviations as dev_mod
from .. import plan as plan_mod
from ..config import load_config
from ..deps import Deps
from ..state import load_state


def cmd_status(_args: Namespace, deps: Deps) -> int:
    """Print status. Returns 0 or 2."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"phase:    {state.phase_name}")
    print(f"kind:     {state.phase_kind}")
    print(f"status:   {state.phase_status}")
    print(f"opened:   {state.phase_opened_at or '(never)'}")
    if state.phase_closed_at:
        print(f"closed:   {state.phase_closed_at}")

    plan_path = deps.project_root / config.plan["path"]
    total = 0
    if deps.fs.exists(plan_path):
        try:
            plan = plan_mod.load(deps.fs, plan_path)
            total = len(plan.tasks)
        except HarnessError as exc:
            print(f"plan:     (unreadable: {exc})")
    print(
        f"plan:     v{state.plan_version} "
        f"position={state.plan_position}/{total} "
        f"frozen={state.plan_frozen}"
    )
    if state.plan_sha256:
        print(f"sha256:   {state.plan_sha256[:16]}...")

    dev_dir = deps.project_root / config.plan["deviations_path"]
    task_id = _current_task_id(state, deps, config)
    if task_id:
        devs = dev_mod.load(deps.fs, dev_dir, task_id)
        if devs:
            print(f"deviations for {task_id}:")
            for d in devs:
                print(f"  - {d.type.value}: {', '.join(d.affected) or '-'}")

    print(f"verify:   ok={state.verify_ok} task={state.verify_task_id or '(none)'}")
    if state.verify_at:
        print(f"          at={state.verify_at}")
    if state.failure_count:
        print(
            f"failure:  task={state.failure_task_id} "
            f"check={state.failure_check_name} count={state.failure_count}"
        )
    print(f"rollbacks:{state.rollback_count}")
    return 0


def _current_task_id(state, deps: Deps, config) -> str:
    if state.phase_kind == "planning":
        return "planning"
    plan_path = deps.project_root / config.plan["path"]
    if not deps.fs.exists(plan_path):
        return ""
    try:
        plan = plan_mod.load(deps.fs, plan_path)
    except HarnessError:
        return ""
    if state.plan_position < 0 or state.plan_position >= len(plan.tasks):
        return ""
    return plan.tasks[state.plan_position].id


__all__ = ["cmd_status"]
