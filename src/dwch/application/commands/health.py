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
from .. import lock as lock_mod
from .. import roadmap as roadmap_mod
from ..config import load_config
from ..deps import Deps
from ..state import load_state


def cmd_health(_args: Namespace, deps: Deps) -> int:
    """Run health checks. Returns 0 or 1."""
    checks: list[tuple[str, bool, str, bool]] = []

    checks.append(_check_python())
    checks.append(_check_venv())
    checks.append(_check_git(deps))
    checks.append(_check_layout(deps))
    checks.append(_check_state(deps))
    checks.append(_check_tokenizer(deps))
    checks.append(_check_roadmap(deps))
    checks.append(_check_summary(deps))

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

    A `.git` entry is either a directory (the common case) or a
    file (a linked worktree or a submodule). Both are valid git
    repositories and both are accepted; only a missing entry is a
    failure.

    Two cases are not errors:

    - Untracked files only (e.g. a fresh `.harness/` right after
      `init`, before the user commits it). The harness does not
      need a pristine tree to run.
    - An empty repository with no commits yet. `git rev-parse` has
      nothing to resolve, but `git status` still works. Report the
      branch as `(no commits)`.

    Only tracked, uncommitted modifications count as dirty here.
    """
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
        # Empty repository: no commits, so HEAD cannot be resolved.
        branch = "(no commits)"

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
    """Check that state loads and passes the coherence predicate.

    `load_state` catches structural errors (bad TOML, missing file).
    `is_state_consistent` catches semantic ones (negative counters,
    unknown phase kind). A state that fails the latter is not fatal
    for `load_state`, but `health` reports it as a failure so the
    user sees the problem before it confuses a later command.
    """
    try:
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        return ("state", False, str(exc), True)
    if not is_state_consistent(state):
        return ("state", False, "state is internally inconsistent", True)
    detail = (
        f"phase={state.current_phase} kind={state.phase_kind} step={state.current_step}"
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


def _check_roadmap(deps: Deps) -> tuple[str, bool, str, bool]:
    """Report the roadmap and lock state, if any.

    The check is informational: a missing roadmap is OK, and a
    changed architecture document is reported but does not fail
    health. Its `critical` flag is always False.

    A malformed lock is reported as a failure rather than raising:
    `health` is the place a user looks when something is wrong, and
    it must never crash on a broken file.
    """
    try:
        config = load_config(deps.fs, deps.project_root)
    except HarnessError:
        return ("roadmap", False, "config not readable", False)

    roadmap_path = deps.project_root / config.roadmap.get(
        "path", ".harness/roadmap.toml"
    )
    if not deps.fs.exists(roadmap_path):
        return ("roadmap", True, "none", False)

    try:
        roadmap = roadmap_mod.load(deps.fs, roadmap_path)
    except HarnessError as exc:
        return ("roadmap", False, str(exc), False)

    lock_path = deps.project_root / config.roadmap.get(
        "lock_path", ".harness/roadmap.lock"
    )
    try:
        lock = lock_mod.load(deps.fs, lock_path)
    except HarnessError as exc:
        return ("roadmap", False, f"invalid lock: {exc}", False)
    if lock is None:
        detail = f"v{roadmap.meta.version} not frozen"
        return ("roadmap", True, detail, False)

    architecture_paths = [
        deps.project_root / p for p in config.context.get("architecture", [])
    ]
    problems = lock_mod.check(
        deps.fs, lock, deps.project_root, roadmap_path, architecture_paths
    )
    if problems:
        detail = f"v{lock.version} frozen; drift: {len(problems)} file(s)"
        return ("roadmap", False, detail, False)
    detail = f"v{lock.version} frozen at {lock.commit or '(no commit)'}"
    return ("roadmap", True, detail, False)


def _check_summary(deps: Deps) -> tuple[str, bool, str, bool]:
    """Report the phase summary recorded in state, if any.

    The check is informational and never fails health: a project
    with no summary yet is a normal state, and a missing summary
    file is a strong signal for the next `close` but not for the
    current command. Its `critical` flag is always False.
    """
    try:
        state = load_state(deps.fs, deps.project_root)
    except HarnessError:
        return ("summary", False, "state not readable", False)
    if not state.summary_phase:
        return ("summary", True, "none yet", False)
    path = deps.project_root / ".harness" / "summaries" / f"{state.summary_phase}.md"
    if not deps.fs.exists(path):
        return (
            "summary",
            False,
            f"state says {state.summary_phase}, file missing",
            False,
        )
    return (
        "summary",
        True,
        f"{state.summary_phase} ({state.summary_written_at})",
        False,
    )


__all__ = ["cmd_health"]
