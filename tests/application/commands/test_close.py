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


def _planning_with_roadmap(root: Path, deps) -> None:
    """Produce a valid roadmap during a planning phase."""
    cmd_new_phase(Namespace(name="plan", kind="planning"), deps)
    deps.clipboard.text = (
        "<<<FILE:.harness/roadmap.toml>>>\n" + _ROADMAP + "<<<END>>>\n"
    )
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)


def test_close_freezes_roadmap(harness_root: Path, deps) -> None:
    """`--freeze` writes the lock and marks state frozen."""
    _planning_with_roadmap(harness_root, deps)
    arch = harness_root / "docs" / "architecture.md"
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("Architecture\n", encoding="utf-8")

    assert cmd_close(_args(freeze=True), deps) == 0
    assert (harness_root / ".harness" / "roadmap.lock").is_file()
    assert load_state(deps.fs, harness_root).roadmap_frozen


def test_close_freeze_outside_planning(harness_root: Path, deps) -> None:
    """`--freeze` in a development phase is refused."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    assert cmd_close(_args(freeze=True), deps) == 2


def test_close_freeze_no_roadmap(harness_root: Path, deps) -> None:
    """`--freeze` without a roadmap on disk is refused."""
    cmd_new_phase(Namespace(name="plan", kind="planning"), deps)
    assert cmd_close(_args(freeze=True), deps) == 2


def test_close_without_freeze(harness_root: Path, deps) -> None:
    """A plain `close` finalizes the phase."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    assert cmd_close(_args(), deps) == 0
