"""`dwch new-phase NAME` — begin a new phase.

Creates `.harness/phase.toml` for the new phase, resets the step
counter, rewrites `handoff.md` from the template, updates the
metadata block, and commits the three files. Refuses when the
working tree is dirty, or when the phase name is malformed.

The commit is part of the operation, not left to the user: a new
phase is a bookkeeping transition that must leave the tree clean
for the next `apply`.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from datetime import UTC, datetime

from ...domain.models import State
from ...shared.errors import HarnessError
from ..config import load_config
from ..deps import Deps
from ..handoff import update_metadata
from ..state import load_state, save_state


def cmd_new_phase(args: Namespace, deps: Deps, _config) -> int:
    """Start a new phase. Returns 0 on success, 2 on error."""
    try:
        load_config(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not deps.git.is_clean(deps.project_root):
        print("error: working tree is dirty", file=sys.stderr)
        return 2

    name = args.name.strip()
    if not name or " " in name:
        print("error: phase name must be non-empty, no spaces", file=sys.stderr)
        return 2

    state = load_state(deps.fs, deps.project_root)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    head = _try_head(deps)

    _write_phase_file(deps, name, now)
    _reset_handoff(deps, name)

    updated = State(
        harness_version=state.harness_version,
        current_phase=name,
        current_step=0,
        total_steps=0,
        last_commit=head,
        last_commit_date=now,
        last_opened=now,
        last_closed=state.last_closed,
    )
    save_state(deps.fs, deps.project_root, updated)
    update_metadata(deps.fs, deps.project_root, updated)

    # Commit the transition itself. Without this, the next `close`
    # or `new-phase` would refuse to run on the now-dirty tree.
    try:
        commit = deps.git.commit_all(deps.project_root, f"chore: start phase {name}")
    except HarnessError as exc:
        print(
            f"warning: could not commit new phase: {exc}",
            file=sys.stderr,
        )
        commit = head

    print(f"new phase: {name}")
    if commit and commit != head:
        print(f"commit: {commit}")
    print("next: `dwch bootstrap --clipboard`")
    return 0


def _write_phase_file(deps: Deps, name: str, now: str) -> None:
    path = deps.project_root / ".harness" / "phase.toml"
    body = (
        "[phase]\n"
        f'name = "{name}"\n'
        f'started = "{now}"\n'
        "\n"
        "[[steps]]\n"
        "number = 1\n"
        'title = "TODO"\n'
        'status = "pending"\n'
    )
    deps.fs.write_text(path, body)


def _reset_handoff(deps: Deps, name: str) -> None:
    from importlib.resources import files

    template = files("dwch.templates") / "handoff.md"
    body = template.read_text(encoding="utf-8").replace("{{phase}}", name)
    deps.fs.write_text(deps.project_root / ".harness" / "handoff.md", body)


def _try_head(deps: Deps) -> str:
    try:
        return deps.git.rev_parse(deps.project_root, "HEAD")
    except HarnessError:
        return ""


__all__ = ["cmd_new_phase"]
