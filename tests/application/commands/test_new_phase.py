"""Tests for `application.commands.new_phase`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.new_phase import cmd_new_phase
from dwch.application.state import load_state


def _args(name: str = "p1", kind: str = "planning") -> Namespace:
    """Minimal namespace for `cmd_new_phase`."""
    return Namespace(name=name, kind=kind)


def test_new_planning_phase(harness_root: Path, deps) -> None:
    """A planning phase resets `current_step` to zero."""
    assert cmd_new_phase(_args("planning-01", "planning"), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.current_phase == "planning-01"
    assert state.phase_kind == "planning"
    assert state.current_step == 0


def test_new_development_no_roadmap(harness_root: Path, deps, capsys) -> None:
    """A development phase without a frozen roadmap starts at 0 and warns."""
    assert cmd_new_phase(_args("dev-01", "development"), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.phase_kind == "development"
    assert state.current_step == 0
    assert "no frozen roadmap" in capsys.readouterr().err


def test_new_phase_rejects_bad_name(harness_root: Path, deps) -> None:
    """A name with a path separator is refused."""
    assert cmd_new_phase(_args("bad/name", "planning"), deps) == 2


def test_new_phase_rejects_space(harness_root: Path, deps) -> None:
    """A name with a space is refused."""
    assert cmd_new_phase(_args("has space", "planning"), deps) == 2


def test_new_phase_dirty_tree(harness_root: Path, deps) -> None:
    """A modified tracked file blocks the transition."""
    deps.git.commit_all(harness_root, "harness setup")
    (harness_root / "README.md").write_text("changed\n", encoding="utf-8")
    assert cmd_new_phase(_args("p1", "planning"), deps) == 2
