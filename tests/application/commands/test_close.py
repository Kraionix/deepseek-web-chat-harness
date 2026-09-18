"""Tests for `application.commands.close`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.close import cmd_close
from dwch.application.commands.new_phase import cmd_new_phase
from dwch.application.commands.verify import cmd_verify
from dwch.application.state import load_state

_ROADMAP = """\
[meta]
version = 1
note = "x"

[[steps]]
number = 1
title = "one"
goal = ""
files = ["src/a.py"]
interfaces = []
acceptance = []
depends_on = []
"""


def _args(freeze: bool = False, tag: bool = False) -> Namespace:
    """Minimal namespace for `cmd_close`."""
    return Namespace(tag=tag, freeze=freeze)


def _apply_summary(deps, phase: str, body: str = "summary text") -> None:
    """Write a phase summary via `apply summary`."""
    deps.clipboard.text = (
        f"<<<FILE:.harness/summaries/{phase}.md>>>\n{body}\n<<<END>>>\n"
    )
    assert cmd_apply(Namespace(step="summary", from_file=None), deps) == 0


def _planning_with_roadmap(root: Path, deps) -> None:
    """Produce a valid roadmap during a planning phase."""
    cmd_new_phase(Namespace(name="plan", kind="planning"), deps)
    deps.clipboard.text = (
        "<<<FILE:.harness/roadmap.toml>>>\n" + _ROADMAP + "<<<END>>>\n"
    )
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)


def test_close_requires_summary(harness_root: Path, deps, capsys) -> None:
    """A close without a summary on disk is refused."""
    cmd_new_phase(Namespace(name="plan", kind="planning"), deps)
    assert cmd_close(_args(), deps) == 2
    assert "no summary" in capsys.readouterr().err


def test_close_freezes_roadmap(harness_root: Path, deps) -> None:
    """`--freeze` writes the lock, marks state frozen, records summary."""
    _planning_with_roadmap(harness_root, deps)
    arch = harness_root / "docs" / "architecture.md"
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("Architecture\n", encoding="utf-8")

    _apply_summary(deps, "plan")

    assert cmd_close(_args(freeze=True), deps) == 0
    assert (harness_root / ".harness" / "roadmap.lock").is_file()
    state = load_state(deps.fs, harness_root)
    assert state.roadmap_frozen
    assert state.summary_phase == "plan"
    assert state.summary_written_at != ""


def test_close_freeze_outside_planning(harness_root: Path, deps) -> None:
    """`--freeze` in a development phase is refused."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    _apply_summary(deps, "dev")
    assert cmd_close(_args(freeze=True), deps) == 2


def test_close_freeze_no_roadmap(harness_root: Path, deps) -> None:
    """`--freeze` without a roadmap on disk is refused."""
    cmd_new_phase(Namespace(name="plan", kind="planning"), deps)
    _apply_summary(deps, "plan")
    assert cmd_close(_args(freeze=True), deps) == 2


def test_close_without_freeze(harness_root: Path, deps) -> None:
    """A plain `close` finalizes the phase."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    _apply_summary(deps, "dev")
    assert cmd_close(_args(), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.summary_phase == "dev"


def test_close_updates_state_summary(harness_root: Path, deps) -> None:
    """`close` records the summary phase and a non-empty timestamp."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    _apply_summary(deps, "dev", "phase dev wrap-up")
    assert cmd_close(_args(), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.summary_phase == "dev"
    assert state.summary_written_at != ""


def test_close_twice_refused(harness_root: Path, deps, capsys) -> None:
    """A second `close` on the same phase is refused."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    _apply_summary(deps, "dev")
    assert cmd_close(_args(), deps) == 0
    assert cmd_close(_args(), deps) == 2
    assert "already closed" in capsys.readouterr().err
