"""Tests for `application.commands.bootstrap`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.bootstrap import cmd_bootstrap
from dwch.application.commands.new_phase import cmd_new_phase


def _args(clipboard: bool = False) -> Namespace:
    """Minimal namespace for `cmd_bootstrap`."""
    return Namespace(clipboard=clipboard)


def test_bootstrap_planning(harness_root: Path, deps, capsys) -> None:
    """A planning bootstrap contains header, progress, and protocol."""
    cmd_new_phase(Namespace(name="p", kind="planning"), deps)
    assert cmd_bootstrap(_args(), deps) == 0
    out = capsys.readouterr().out
    assert "section: header" in out
    assert "section: progress" in out
    assert "section: protocol" in out


def test_bootstrap_development_has_current_step(
    harness_root: Path, deps, capsys
) -> None:
    """A development bootstrap shows the current roadmap step."""
    # A development phase without a roadmap still resolves to a
    # bootstrap that at least includes the header.
    cmd_new_phase(Namespace(name="d", kind="development"), deps)
    assert cmd_bootstrap(_args(), deps) == 0
    out = capsys.readouterr().out
    assert "section: header" in out
    assert "section: progress" in out
