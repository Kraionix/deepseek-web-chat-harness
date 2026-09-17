"""`dwch close` — finalize the session.

Updates `.harness/state.toml` (last_closed, last_commit), refreshes
the metadata block in `handoff.md`, commits both, and optionally
creates a `session-YYYYMMDD-HHMM` tag. Refuses to run when tracked
files have uncommitted changes; untracked files are swept into the
close commit, because the close transition is a bookkeeping commit
that owns the whole tree.

With `--freeze`, additionally computes hashes of the roadmap and
architecture documents and writes `.harness/roadmap.lock`, marking
`state.roadmap_frozen = True`. Valid only in a planning phase.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from datetime import UTC, datetime

from ...domain.rules import is_planning_phase
from ...shared.errors import HarnessError
from .. import lock as lock_mod
from .. import roadmap as roadmap_mod
from ..config import load_config
from ..deps import Deps
from ..handoff import update_metadata
from ..state import load_state, save_state, set_roadmap_frozen, with_updates


def cmd_close(args: Namespace, deps: Deps) -> int:
    """Close the session. Returns 0 on success, 2 on error."""
    try:
        config = load_config(deps.fs, deps.project_root)
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not deps.git.is_clean_tracked(deps.project_root):
        print(
            "error: working tree has uncommitted tracked changes. "
            "Commit or stash your changes before closing.",
            file=sys.stderr,
        )
        return 2

    head = deps.git.try_head(deps.project_root)
    now = datetime.now(UTC).isoformat(timespec="seconds")

    if args.freeze:
        rc = _freeze(deps, config, state, head, now)
        if rc != 0:
            return rc

    state = load_state(deps.fs, deps.project_root)
    updated = with_updates(
        state,
        last_commit=head,
        last_commit_date=now,
        last_closed=now,
    )
    save_state(deps.fs, deps.project_root, updated)
    update_metadata(deps.fs, deps.project_root, updated)

    # Commit the close transition. Without this, the tree is left
    # dirty and the next command that requires a clean tree would
    # refuse to run.
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
    print("next: continue phase, or `dwch new-phase NAME --kind ...`")
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
