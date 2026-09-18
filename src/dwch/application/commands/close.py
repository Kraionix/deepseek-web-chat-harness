"""`dwch close` — finalize a phase.

A close is a lifecycle transition. It:

1. Checks five preconditions, in order: state loads, a phase is
   active, the phase is not already closed, the phase summary
   exists, and the working tree has no uncommitted tracked changes.
2. Optionally freezes the roadmap (`--freeze`, planning only).
3. Records the summary and the close timestamp in `state.toml`.
4. Refreshes the harness block in `handoff.md`.
5. Commits the transition.
6. Optionally tags the close.
7. Prints a recommendation to close the chat and start a new phase.

The summary requirement is deliberate: it is the only cross-phase
context the next session sees, and a phase that ends without one
leaves the next chat blind.

Timestamps use `state.now_iso()` (microsecond precision), because
`is_phase_closed` compares `last_closed` and `last_opened` as
strings; second-resolution would let a rapid close/new-phase pair
collide.

If the commit fails, state is restored and the command exits 2:
the phase was not closed, and the next command must see the
pre-close state.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from datetime import UTC, datetime

from ...domain.rules import (
    is_phase_closed,
    is_planning_phase,
    is_unset_phase,
)
from ...shared.errors import HarnessError
from .. import lock as lock_mod
from .. import roadmap as roadmap_mod
from ..config import load_config
from ..deps import Deps
from ..handoff import ensure_metadata
from ..state import (
    load_state,
    now_iso,
    save_state,
    set_roadmap_frozen,
    with_updates,
)


def cmd_close(args: Namespace, deps: Deps) -> int:
    """Close the current phase. Returns 0 on success, 2 on error."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if is_unset_phase(state):
        print(
            "error: no active phase to close. Run "
            "`dwch new-phase NAME --kind {planning|development}` first.",
            file=sys.stderr,
        )
        return 2

    if is_phase_closed(state):
        print(
            f"error: phase {state.current_phase} is already closed.",
            file=sys.stderr,
        )
        return 2

    summary_rel = f".harness/summaries/{state.current_phase}.md"
    summary_path = deps.project_root / summary_rel
    if not deps.fs.exists(summary_path):
        print(
            f"error: no summary at {summary_rel}. "
            "Write one with `dwch apply summary` first.",
            file=sys.stderr,
        )
        return 2

    if not deps.git.is_clean_tracked(deps.project_root):
        print(
            "error: working tree has uncommitted tracked changes. "
            "Commit or stash your changes before closing.",
            file=sys.stderr,
        )
        return 2

    head = deps.git.try_head(deps.project_root)
    now = now_iso()

    if args.freeze:
        rc = _freeze(deps, config, state, head, now)
        if rc != 0:
            return rc

    # Reload: `_freeze` writes state itself. The reload keeps the
    # summary record consistent with any freeze-side changes
    # (roadmap_frozen, roadmap_step).
    before = load_state(deps.fs, deps.project_root)
    updated = with_updates(
        before,
        last_commit=head,
        last_commit_date=now,
        last_closed=now,
        summary_phase=before.current_phase,
        summary_written_at=now,
    )
    save_state(deps.fs, deps.project_root, updated)
    ensure_metadata(deps.fs, deps.project_root, updated)

    try:
        commit = deps.git.commit_all(
            deps.project_root, f"chore: close phase {updated.current_phase}"
        )
        print(f"commit: {commit}")
    except HarnessError as exc:
        # Close did not happen. Restore state and the handoff block,
        # then exit 2. The tree is dirty; the user must resolve it.
        save_state(deps.fs, deps.project_root, before)
        ensure_metadata(deps.fs, deps.project_root, before)
        print(f"error: commit failed: {exc}", file=sys.stderr)
        print(
            "state was restored; the phase was not closed. "
            "Fix the tree and re-run `dwch close`.",
            file=sys.stderr,
        )
        return 2

    if args.tag and head:
        # Second-resolution: a minute-resolution tag collides on a
        # rapid close/reopen/close sequence, and a second-resolution
        # one does not.
        tag = f"session-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        try:
            deps.git.tag(deps.project_root, tag, f"session close at {now}")
            print(f"tagged: {tag}")
        except HarnessError as exc:
            print(f"warning: could not create tag: {exc}", file=sys.stderr)

    print(f"closed. phase={updated.current_phase} step={updated.current_step}")
    print()
    print("next:")
    print("  1. Close this chat.")
    print("  2. Start a new phase:")
    print("     dwch new-phase NAME --kind {planning|development}")
    print("  3. dwch bootstrap --clipboard")
    print("  4. Open a fresh chat, paste the bootstrap.")
    return 0


def _freeze(deps: Deps, config, state, head: str, now: str) -> int:
    """Write the roadmap lock and mark state frozen. Returns 0 on success."""
    if not is_planning_phase(state):
        print(
            "error: --freeze is only valid in a planning phase",
            file=sys.stderr,
        )
        return 2

    roadmap_path = deps.project_root / config.roadmap.get(
        "path", ".harness/roadmap.toml"
    )
    if not deps.fs.exists(roadmap_path):
        print(
            f"error: no roadmap at {roadmap_path}; nothing to freeze. "
            "Write `.harness/roadmap.toml` in a step first, then "
            "`dwch apply NN` and `dwch verify NN` before closing.",
            file=sys.stderr,
        )
        return 2

    try:
        roadmap = roadmap_mod.load(deps.fs, roadmap_path)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    problems = roadmap_mod.validate(roadmap)
    if problems:
        print("error: roadmap is not structurally valid:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 2

    lock_path = deps.project_root / config.roadmap.get(
        "lock_path", ".harness/roadmap.lock"
    )
    architecture_paths = []
    for name in config.context.get("architecture", []):
        full = deps.project_root / name
        if not deps.fs.exists(full):
            print(
                f"error: architecture file missing: {name}. "
                "Create it in a planning step, or remove it from "
                "`context.architecture` in `.harness/config.toml`.",
                file=sys.stderr,
            )
            return 2
        architecture_paths.append(full)

    try:
        lock_mod.write(
            deps.fs,
            lock_path,
            deps.project_root,
            roadmap_path,
            architecture_paths,
            at=now,
            phase=state.current_phase,
            commit=head,
            version=roadmap.meta.version,
        )
    except HarnessError as exc:
        print(f"error: could not write lock: {exc}", file=sys.stderr)
        return 2

    set_roadmap_frozen(deps.fs, deps.project_root, state, version=roadmap.meta.version)
    print(f"frozen roadmap v{roadmap.meta.version} at {lock_path}")
    return 0


__all__ = ["cmd_close"]
