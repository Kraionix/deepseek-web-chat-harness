"""Tests for `application.commands.next`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.next import cmd_next
from dwch.application.commands.start import cmd_start


def _start(root: Path, deps, kind: str = "planning") -> None:
    """Start a phase."""
    assert cmd_start(Namespace(goal="p", kind=kind), deps) == 0


def test_next_no_phase(harness_root: Path, deps) -> None:
    """Without a phase, `next` exits 2."""
    assert cmd_next(Namespace(), deps) == 2


def test_next_copies_bootstrap_to_clipboard(harness_root: Path, deps) -> None:
    """`next` writes a bootstrap to the clipboard."""
    _start(harness_root, deps)
    deps.clipboard.text = ""
    assert cmd_next(Namespace(), deps) == 0
    assert "section: contract" in deps.clipboard.text
    assert "section: meta" in deps.clipboard.text


def test_next_is_idempotent(harness_root: Path, deps) -> None:
    """`next` does not advance state."""
    from dwch.application.state import load_state

    _start(harness_root, deps)
    before = load_state(deps.fs, harness_root)
    cmd_next(Namespace(), deps)
    cmd_next(Namespace(), deps)
    after = load_state(deps.fs, harness_root)
    assert before.plan_position == after.plan_position
