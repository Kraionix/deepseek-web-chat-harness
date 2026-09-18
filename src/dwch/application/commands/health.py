"""`dwch health` — check environment and project state.

Prints a table of checks. Exit 0 when all critical checks pass;
exit 1 otherwise. Non-critical failures are recorded but do not
affect the exit code.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...domain.rules import is_state_consistent
from ...shared.errors import HarnessError
from .. import plan as plan_mod
from ..config import load_config
from ..deps import Deps
from ..state import load_state


def cmd_health(_args: Namespace, deps: Deps) -> int:
    """Run health checks. Returns 0 or 1."""
    checks: list[tuple[str, bool, str, bool]] = [
        _check_python(),
        _check_venv(),
        _check_git(deps),
        _check_layout(deps),
        _check_state(deps),
        _check_tokenizer(deps),
        _check_plan(deps),
    ]

    any_critical_failed = False
    for name, ok, detail, critical in checks:
        status = "OK" if ok else "FAIL"
        print(f"{name:<24} {status:<6} {detail}")
        if not ok and critical:
            any_critical_failed = True
    return 1 if any_critical_failed else 0


def _check_python() -> tuple[str, bool, str, bool]:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    ok = sys.version_info >= (3, 11)
    return ("python", ok, version, True)


def _check_venv() -> tuple[str, bool, str, bool]:
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    return ("venv", in_venv, sys.prefix if in_venv else "not in a venv", False)


def _check_git(deps: Deps) -> tuple[str, bool, str, bool]:
    root = deps.project_root
    git_entry = root / ".git"
    if not (deps.fs.is_dir(git_entry) or deps.fs.is_file(git_entry)):
        return ("git", False, "no .git directory or file", True)
    try:
        lines = deps.git.status_short(root)
    except HarnessError as exc:
        return ("git", False, str(exc), True)
    try:
        branch = deps.git.current_branch(root)
    except HarnessError:
        branch = "(no commits)"
    tracked = [line for line in lines if not line.startswith("??")]
    if tracked:
        return (
            "git",
            False,
            f"{len(tracked)} uncommitted change(s) on {branch}",
            False,
        )
    untracked = len(lines) - len(tracked)
    if untracked:
        return ("git", True, f"clean on {branch} ({untracked} untracked)", True)
    return ("git", True, f"clean on {branch}", True)


def _check_layout(deps: Deps) -> tuple[str, bool, str, bool]:
    required = [".harness", ".harness/config.toml", ".harness/state.toml"]
    missing = [
        name for name in required if not deps.fs.exists(deps.project_root / name)
    ]
    if missing:
        return ("layout", False, f"missing: {', '.join(missing)}", True)
    return ("layout", True, "all required files present", True)


def _check_state(deps: Deps) -> tuple[str, bool, str, bool]:
    try:
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        return ("state", False, str(exc), True)
    if not is_state_consistent(state):
        return ("state", False, "state is internally inconsistent", True)
    detail = (
        f"phase={state.phase_name} kind={state.phase_kind} "
        f"status={state.phase_status} position={state.plan_position}"
    )
    return ("state", True, detail, True)


def _check_tokenizer(deps: Deps) -> tuple[str, bool, str, bool]:
    try:
        config = load_config(deps.fs, deps.project_root)
    except HarnessError:
        return ("tokenizer", False, "config not readable", True)
    path = config.tokenizer_path
    if not deps.fs.exists(path):
        return ("tokenizer", False, f"missing: {path.name}", True)
    try:
        _ = deps.counter.count("hello")
    except HarnessError as exc:
        return ("tokenizer", False, str(exc), True)
    return ("tokenizer", True, path.name, True)


def _check_plan(deps: Deps) -> tuple[str, bool, str, bool]:
    """Report the plan and frozen status, if any. Informational."""
    try:
        config = load_config(deps.fs, deps.project_root)
    except HarnessError:
        return ("plan", False, "config not readable", False)

    path = deps.project_root / config.plan["path"]
    if not deps.fs.exists(path):
        return ("plan", True, "none", False)
    try:
        plan = plan_mod.load(deps.fs, path)
    except HarnessError as exc:
        return ("plan", False, str(exc), False)
    try:
        state = load_state(deps.fs, deps.project_root)
    except HarnessError:
        state = None
    if state is not None and state.plan_frozen:
        if state.plan_version != plan.meta.version:
            return (
                "plan",
                False,
                f"frozen v{state.plan_version}, file v{plan.meta.version}",
                False,
            )
        current_sha = plan_mod.sha256(deps.fs, path)
        if current_sha != state.plan_sha256:
            return ("plan", False, f"v{state.plan_version} frozen; file drifted", False)
        return (
            "plan",
            True,
            f"v{state.plan_version} frozen at {current_sha[:12]}",
            False,
        )
    return ("plan", True, f"v{plan.meta.version} not frozen", False)


__all__ = ["cmd_health"]
