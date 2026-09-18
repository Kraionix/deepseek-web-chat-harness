"""Tests for `application.commands.abandon`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.abandon import cmd_abandon
from dwch.application.commands.start import cmd_start
from dwch.application.state import load_state


def test_abandon_requires_yes(harness_root: Path, deps) -> None:
    """Without `--yes`, abandon is refused."""
    cmd_start(Namespace(goal="p", kind="planning"), deps)
    assert cmd_abandon(Namespace(yes=False), deps) == 2


def test_abandon_closes_phase(harness_root: Path, deps) -> None:
    """Abandon marks the phase abandoned and leaves files on disk."""
    cmd_start(Namespace(goal="p", kind="planning"), deps)
    assert cmd_abandon(Namespace(yes=True), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.phase_status == "abandoned"
    assert state.phase_closed_at != ""


def test_abandon_no_phase(harness_root: Path, deps, capsys) -> None:
    """Without a phase, abandon exits 2."""
    assert cmd_abandon(Namespace(yes=True), deps) == 2
    assert "no active phase" in capsys.readouterr().err
