"""Tests for `application.commands.start`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from dwch.application.commands.start import cmd_start
from dwch.application.state import load_state


def _args(goal: str = "design the API", kind: str | None = None) -> Namespace:
    """Minimal namespace for `cmd_start`."""
    return Namespace(goal=goal, kind=kind)


@pytest.mark.slow
def test_start_planning_by_default(harness_root: Path, deps) -> None:
    """With no frozen plan, the kind is inferred as planning."""
    assert cmd_start(_args("first"), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.phase_kind == "planning"
    assert state.phase_status == "open"


@pytest.mark.slow
def test_start_explicit_kind(harness_root: Path, deps) -> None:
    """An explicit `--kind` overrides the inference."""
    assert cmd_start(_args("dev", "development"), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.phase_kind == "development"


def test_start_rejects_open_phase(harness_root: Path, deps, capsys) -> None:
    """A start is refused while a phase is open."""
    # Force an open phase directly.
    from dwch.application.state import initial_state, save_state, set_phase_open

    state = set_phase_open(initial_state(), "p1", "planning", "now")
    save_state(deps.fs, harness_root, state)
    assert cmd_start(_args("p2"), deps) == 2
    assert "already open" in capsys.readouterr().err


@pytest.mark.slow
def test_start_commit_failure_restores_state(
    harness_root: Path, deps, broken_deps, capsys
) -> None:
    """A failed commit leaves state unchanged."""
    before = load_state(deps.fs, harness_root)
    rc = cmd_start(_args("p1"), broken_deps)
    assert rc == 2
    after = load_state(deps.fs, harness_root)
    assert after.phase_name == before.phase_name
    assert after.phase_status == before.phase_status
    assert "commit failed" in capsys.readouterr().err
