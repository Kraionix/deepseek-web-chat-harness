"""`dwch health` — check environment and project state.

Prints a table of checks. Exit 0 when all critical checks pass;
exit 1 otherwise. Non-critical failures are recorded but do not
affect the exit code.
"""

from __future__ import annotations

import sys
from argparse import Namespace

from ...shared.errors import HarnessError
from ..config import load_config
from ..deps import Deps
from ..state import load_state


def cmd_health(_args: Namespace, deps: Deps, _config) -> int:
    """Run health checks. Returns 0 or 1."""
    checks: list[tuple[str, bool, str, bool]] = []

    checks.append(_check_python())
    checks.append(_check_venv())
    checks.append(_check_git(deps))
    checks.append(_check_layout(deps))
    checks.append(_check_state(deps))
    checks.append(_check_tokenizer(deps))

    any_critical_failed = False
    for name, ok, detail, critical in checks:
        status = "OK" if ok else "FAIL"
        line = f"{name:<24} {status:<6} {detail}"
        print(line)
        if not ok and critical:
            any_critical_failed = True
    return 1 if any_critical_failed else 0


def _check_python() -> tuple[str, bool, str, bool]:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    ok = sys.version_info >= (3, 11)
    return ("python", ok, version, True)


def _check_venv() -> tuple[str, bool, str, bool]:
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    detail = sys.prefix if in_venv else "not in a venv"
    return ("venv", in_venv, detail, False)


def _check_git(deps: Deps) -> tuple[str, bool, str, bool]:
    """Check git state.

    A tree with only untracked files (e.g. a fresh `.harness/`
    right after `init`, before the user commits it) is not a
    problem: the harness does not need a pristine tree to run.
    Only tracked, uncommitted modifications count as dirty here.
    Operations that *do* require a clean tree (`close`,
    `new-phase`, `rollback`) call `GitPort.is_clean` directly.
    """
    root = deps.project_root
    if not deps.fs.is_dir(root / ".git"):
        return ("git", False, "no .git directory", True)
    try:
        branch = deps.git.current_branch(root)
        lines = deps.git.status_short(root)
    except HarnessError as exc:
        return ("git", False, str(exc), True)

    tracked = [line for line in lines if not line.startswith("??")]
    if tracked:
        detail = f"{len(tracked)} uncommitted change(s) on {branch}"
        return ("git", False, detail, False)

    untracked = len(lines) - len(tracked)
    if untracked:
        detail = f"clean on {branch} ({untracked} untracked)"
        return ("git", True, detail, True)
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
    return (
        "state",
        True,
        f"phase={state.current_phase} step={state.current_step}",
        True,
    )


def _check_tokenizer(deps: Deps) -> tuple[str, bool, str, bool]:
    try:
        _config = load_config(deps.fs, deps.project_root)
    except HarnessError:
        return ("tokenizer", False, "config not readable", True)
    path = _config.tokenizer_path
    if not deps.fs.exists(path):
        return ("tokenizer", False, f"missing: {path.name}", True)
    try:
        _ = deps.counter.count("hello")
    except HarnessError as exc:
        return ("tokenizer", False, str(exc), True)
    return ("tokenizer", True, path.name, True)


__all__ = ["cmd_health"]
