"""Tests for `application.commands.verify` in a development phase."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.done import cmd_done
from dwch.application.commands.start import cmd_start
from dwch.application.commands.verify import cmd_verify
from dwch.application.state import load_state

pytestmark = pytest.mark.slow

_PLAN = """\
[meta]
version = 1
note = "demo"

[[tasks]]
id = "t1"
title = "Greet"
goal = "Write greet."
files = ["src/app.py"]
interfaces = []
acceptance = []
depends_on = []
"""

_GREET = "def greet(name):\n    return name\n"


def _latest_phase_dir(harness_root: Path) -> Path:
    """Return the phase directory with the highest name (lexicographic).

    `start` auto-generates phase names with a leading counter, so
    the lexicographically greatest name is the most recently
    created phase.
    """
    steps_root = harness_root / "steps"
    dirs = sorted(p for p in steps_root.iterdir() if p.is_dir())
    assert dirs, "no phase directory found"
    return dirs[-1]


def _frozen_plan(root: Path, deps) -> None:
    """Run a short planning phase to produce a frozen plan."""
    assert cmd_start(Namespace(goal="plan", kind="planning"), deps) == 0
    deps.clipboard.text = "<<<FILE:.harness/plan.toml>>>\n" + _PLAN + "<<<END>>>\n"
    cmd_apply(Namespace(from_file=None), deps)
    cmd_verify(Namespace(clipboard=False), deps)
    cmd_done(Namespace(), deps)
    assert cmd_start(Namespace(goal="dev", kind="development"), deps) == 0


def test_development_happy_path(harness_root: Path, deps) -> None:
    """A matching task passes and records `verify_ok`."""
    _frozen_plan(harness_root, deps)
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    assert cmd_apply(Namespace(from_file=None), deps) == 0
    assert cmd_verify(Namespace(clipboard=False), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.verify_ok is True
    assert state.verify_task_id == "t1"


def test_development_verify_does_not_commit(harness_root: Path, deps) -> None:
    """A successful verify does not create a commit."""
    _frozen_plan(harness_root, deps)
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    cmd_apply(Namespace(from_file=None), deps)
    before = deps.git.rev_parse(harness_root, "HEAD")
    cmd_verify(Namespace(clipboard=False), deps)
    after = deps.git.rev_parse(harness_root, "HEAD")
    assert before == after


def test_development_verify_fail_does_not_advance(harness_root: Path, deps) -> None:
    """A failed verify leaves `plan_position` unchanged."""
    _frozen_plan(harness_root, deps)
    deps.clipboard.text = "<<<FILE:src/wrong.py>>>\n" + _GREET + "<<<END>>>\n"
    cmd_apply(Namespace(from_file=None), deps)
    before = load_state(deps.fs, harness_root).plan_position
    assert cmd_verify(Namespace(clipboard=False), deps) == 1
    after = load_state(deps.fs, harness_root)
    assert after.plan_position == before
    assert after.failure_count == 1
    assert after.plan_position == 0


def test_development_verify_uses_task_changes(harness_root: Path, deps) -> None:
    """A task whose files do not match the plan fails `task-changes`."""
    _frozen_plan(harness_root, deps)
    # Correct file, but write it AND an extra one.
    deps.clipboard.text = (
        "<<<FILE:src/app.py>>>\n"
        + _GREET
        + "<<<END>>>\n<<<FILE:src/extra.py>>>\nx = 1\n<<<END>>>\n"
    )
    cmd_apply(Namespace(from_file=None), deps)
    assert cmd_verify(Namespace(clipboard=False), deps) == 1
    phase_dir = _latest_phase_dir(harness_root)
    report = (phase_dir / "t1" / "report-1.txt").read_text(encoding="utf-8")
    assert "task-changes" in report
    assert "extra written" in report
