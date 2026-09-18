"""Tests for `application.commands.verify` in a planning phase."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.start import cmd_start
from dwch.application.commands.verify import cmd_verify

_PLAN_GOOD = """\
[meta]
version = 1
note = "x"

[[interfaces]]
name = "A"
kind = "class"
module = "src/a.py"
signature = "class A"
doc = ""

[[tasks]]
id = "models"
title = "one"
goal = ""
files = ["src/a.py"]
interfaces = ["A"]
acceptance = []
depends_on = []
"""


def _start(root: Path, deps) -> None:
    """Start a planning phase."""
    assert cmd_start(Namespace(goal="plan", kind="planning"), deps) == 0


def _apply(root: Path, deps, body: str, path: str) -> None:
    """Write a plan via `apply` so `verify` sees it on disk."""
    deps.clipboard.text = f"<<<FILE:{path}>>>\n{body}<<<END>>>\n"
    assert cmd_apply(Namespace(from_file=None), deps) == 0


def test_planning_verify_plan_ok(harness_root: Path, deps) -> None:
    """A valid plan passes the structure check."""
    _start(harness_root, deps)
    _apply(harness_root, deps, _PLAN_GOOD, ".harness/plan.toml")
    assert cmd_verify(Namespace(clipboard=False), deps) == 0


def test_planning_verify_plan_bad(harness_root: Path, deps) -> None:
    """An unknown interface reference fails `plan-structure`."""
    _start(harness_root, deps)
    bad = _PLAN_GOOD.replace('interfaces = ["A"]', 'interfaces = ["Z"]')
    _apply(harness_root, deps, bad, ".harness/plan.toml")
    assert cmd_verify(Namespace(clipboard=False), deps) == 1


def test_planning_verify_writes_hint_on_failure(harness_root: Path, deps) -> None:
    """A failed verify places a hint on the clipboard."""
    _start(harness_root, deps)
    bad = _PLAN_GOOD.replace('interfaces = ["A"]', 'interfaces = ["Z"]')
    _apply(harness_root, deps, bad, ".harness/plan.toml")
    cmd_verify(Namespace(clipboard=False), deps)
    assert "verify FAILED" in deps.clipboard.text


def test_planning_verify_increments_failure_count(harness_root: Path, deps) -> None:
    """A failed verify increments `state.failure.count`."""
    from dwch.application.state import load_state

    _start(harness_root, deps)
    bad = _PLAN_GOOD.replace('interfaces = ["A"]', 'interfaces = ["Z"]')
    _apply(harness_root, deps, bad, ".harness/plan.toml")
    cmd_verify(Namespace(clipboard=False), deps)
    assert load_state(deps.fs, harness_root).failure_count == 1
