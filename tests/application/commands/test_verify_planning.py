"""Tests for `application.commands.verify` in a planning phase."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.new_phase import cmd_new_phase
from dwch.application.commands.verify import cmd_verify

_ROADMAP_GOOD = """\
[meta]
version = 1
note = "x"

[[interfaces]]
name = "A"
kind = "class"
module = "src/a.py"
signature = "class A"
doc = ""

[[steps]]
number = 1
title = "one"
goal = ""
files = ["src/a.py"]
interfaces = ["A"]
acceptance = []
depends_on = []
"""


def _phase(root: Path, deps) -> None:
    """Start a planning phase."""
    assert cmd_new_phase(Namespace(name="p", kind="planning"), deps) == 0


def _apply_roadmap(root: Path, deps, body: str, path: str) -> None:
    """Write a roadmap via `apply` so `verify` sees it on disk."""
    deps.clipboard.text = f"<<<FILE:{path}>>>\n{body}<<<END>>>\n"
    assert cmd_apply(Namespace(step="01", from_file=None), deps) == 0


def test_planning_verify_roadmap_ok(harness_root: Path, deps) -> None:
    """A valid roadmap passes the structure check."""
    _phase(harness_root, deps)
    _apply_roadmap(harness_root, deps, _ROADMAP_GOOD, ".harness/roadmap.toml")
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 0


def test_planning_verify_roadmap_bad(harness_root: Path, deps) -> None:
    """An unknown interface reference fails `roadmap-structure`."""
    _phase(harness_root, deps)
    bad = _ROADMAP_GOOD.replace('interfaces = ["A"]', 'interfaces = ["Z"]')
    _apply_roadmap(harness_root, deps, bad, ".harness/roadmap.toml")
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 1


def test_planning_verify_double_slash_path(harness_root: Path, deps) -> None:
    """`.harness//roadmap.toml` is recognized as the roadmap."""
    _phase(harness_root, deps)
    _apply_roadmap(harness_root, deps, _ROADMAP_GOOD, ".harness//roadmap.toml")
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 0


def test_planning_verify_missing_roadmap_section(harness_root: Path, deps) -> None:
    """A step that does not write a roadmap skips the structure check."""
    _phase(harness_root, deps)
    deps.clipboard.text = "<<<FILE:docs/x.md>>>\nhello\n<<<END>>>\n"
    assert cmd_apply(Namespace(step="01", from_file=None), deps) == 0
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 0


def test_planning_verify_bad_step_argument(harness_root: Path, deps) -> None:
    """A non-integer step argument exits 2."""
    _phase(harness_root, deps)
    assert cmd_verify(Namespace(step="abc", clipboard=False), deps) == 2


def test_planning_verify_zero_step_argument(harness_root: Path, deps) -> None:
    """`verify 0` exits 2."""
    _phase(harness_root, deps)
    _apply_roadmap(harness_root, deps, _ROADMAP_GOOD, ".harness/roadmap.toml")
    assert cmd_verify(Namespace(step="0", clipboard=False), deps) == 2


def test_planning_verify_single_digit_step(harness_root: Path, deps) -> None:
    """`apply 1` + `verify 1` agree on the same step file."""
    _phase(harness_root, deps)
    deps.clipboard.text = (
        "<<<FILE:.harness/roadmap.toml>>>\n" + _ROADMAP_GOOD + "<<<END>>>\n"
    )
    assert cmd_apply(Namespace(step="1", from_file=None), deps) == 0
    assert cmd_verify(Namespace(step="1", clipboard=False), deps) == 0
