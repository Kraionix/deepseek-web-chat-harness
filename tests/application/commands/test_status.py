"""Tests for `application.commands.status`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.start import cmd_start
from dwch.application.commands.status import cmd_status


def test_status_prints_phase(harness_root: Path, deps, capsys) -> None:
    """`status` prints the phase name and kind."""
    cmd_start(Namespace(goal="p", kind="planning"), deps)
    assert cmd_status(Namespace(), deps) == 0
    out = capsys.readouterr().out
    assert "phase:" in out
    assert "kind:" in out
    assert "plan:" in out
    assert "verify:" in out


def test_status_without_phase(harness_root: Path, deps, capsys) -> None:
    """`status` works on a fresh project."""
    assert cmd_status(Namespace(), deps) == 0
    assert "unset" in capsys.readouterr().out
