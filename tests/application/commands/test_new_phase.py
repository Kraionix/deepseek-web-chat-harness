"""Tests for `application.commands.new_phase`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.close import cmd_close
from dwch.application.commands.new_phase import cmd_new_phase
from dwch.application.state import load_state


def _args(name: str = "p1", kind: str = "planning") -> Namespace:
    """Minimal namespace for `cmd_new_phase`."""
    return Namespace(name=name, kind=kind)


def _apply_summary(deps, phase: str) -> None:
    """Write a phase summary via `apply summary`."""
    deps.clipboard.text = (
        f"<<<FILE:.harness/summaries/{phase}.md>>>\nsummary\n<<<END>>>\n"
    )
    assert cmd_apply(Namespace(step="summary", from_file=None), deps) == 0


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


def test_new_phase_rejects_newline(harness_root: Path, deps, capsys) -> None:
    """A name with an embedded newline is refused before any write."""
    assert cmd_new_phase(_args("a\nb", "planning"), deps) == 2
    err = capsys.readouterr().err
    assert "newlines" in err or "control" in err
    # No directory was created and no state was written.
    assert not (harness_root / "steps" / "a\nb").exists()
    state = load_state(deps.fs, harness_root)
    assert state.current_phase == "unset"


def test_new_phase_rejects_tab(harness_root: Path, deps, capsys) -> None:
    """A name with an embedded tab is refused."""
    assert cmd_new_phase(_args("a\tb", "planning"), deps) == 2
    err = capsys.readouterr().err
    assert "tabs" in err or "control" in err


def test_new_phase_rejects_nul(harness_root: Path, deps, capsys) -> None:
    """A name containing NUL is refused before `Path.exists`."""
    assert cmd_new_phase(_args("a\x00b", "planning"), deps) == 2
    err = capsys.readouterr().err
    assert "control" in err


def test_new_phase_dirty_tree(harness_root: Path, deps) -> None:
    """A modified tracked file blocks the transition."""
    deps.git.commit_all(harness_root, "harness setup")
    (harness_root / "README.md").write_text("changed\n", encoding="utf-8")
    assert cmd_new_phase(_args("p1", "planning"), deps) == 2


def test_new_phase_requires_previous_closed(harness_root: Path, deps, capsys) -> None:
    """A new phase is refused while the previous one is still open."""
    assert cmd_new_phase(_args("p1", "planning"), deps) == 0
    assert cmd_new_phase(_args("p2", "planning"), deps) == 2
    assert "not closed" in capsys.readouterr().err


def test_new_phase_rejects_existing_name(harness_root: Path, deps, capsys) -> None:
    """A phase name already on disk is refused."""
    assert cmd_new_phase(_args("p1", "planning"), deps) == 0
    _apply_summary(deps, "p1")
    assert cmd_close(Namespace(tag=False, freeze=False), deps) == 0
    # `steps/p1/` now exists; reusing the name is refused.
    assert cmd_new_phase(_args("p1", "planning"), deps) == 2
    assert "already exists" in capsys.readouterr().err


def test_new_phase_commit_failure_restores_state(
    harness_root: Path, deps, broken_deps, capsys
) -> None:
    """A failed commit leaves state at the pre-phase values."""
    before = load_state(deps.fs, harness_root)
    rc = cmd_new_phase(Namespace(name="p1", kind="planning"), broken_deps)
    assert rc == 2
    after = load_state(deps.fs, harness_root)
    assert after.current_phase == before.current_phase
    assert after.phase_kind == before.phase_kind
    err = capsys.readouterr().err
    assert "commit failed" in err
    assert "did not start" in err
