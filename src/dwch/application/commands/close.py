"""`dwch close` — finalize the session.

Updates `.harness/state.toml` (last_closed, last_commit), refreshes
the metadata block in `handoff.md`, commits both, and optionally
creates a `session-YYYYMMDD-HHMM` tag. Refuses to run on a dirty
git tree.
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


def cmd_close(args: Namespace, deps: Deps, _config) -> int:
    """Close the session. Returns 0 on success, 2 on error."""
    try:
        load_config(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not deps.git.is_clean(deps.project_root):
        print(
            "error: working tree is dirty. Commit or stash your "
            "changes before closing.",
            file=sys.stderr,
        )
        return 2

    state = load_state(deps.fs, deps.project_root)
    head = _try_head(deps)
    now = datetime.now(UTC).isoformat(timespec="seconds")

    updated = State(
        harness_version=state.harness_version,
        current_phase=state.current_phase,
        current_step=state.current_step,
        total_steps=state.total_steps,
        last_commit=head,
        last_commit_date=now,
        last_opened=state.last_opened,
        last_closed=now,
    )
    save_state(deps.fs, deps.project_root, updated)
    update_metadata(deps.fs, deps.project_root, updated)

    # Commit the close transition. Without this, the tree is left
    # dirty (state.toml, handoff.md modified) and the next command
    # that requires a clean tree would refuse to run.
    try:
        commit = deps.git.commit_all(
            deps.project_root, f"chore: close phase {updated.current_phase}"
        )
        print(f"commit: {commit}")
    except HarnessError as exc:
        print(f"warning: could not commit close: {exc}", file=sys.stderr)

    if args.tag and head:
        tag = f"session-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}"
        try:
            deps.git.tag(deps.project_root, tag, f"session close at {now}")
            print(f"tagged: {tag}")
        except HarnessError as exc:
            print(f"warning: could not create tag: {exc}", file=sys.stderr)

    print(f"closed. phase={updated.current_phase} step={updated.current_step}")
    print("next: continue phase, or `dwch new-phase NAME` to advance")
    return 0


def _try_head(deps: Deps) -> str:
    try:
        return deps.git.rev_parse(deps.project_root, "HEAD")
    except HarnessError:
        return ""


__all__ = ["cmd_close"]
