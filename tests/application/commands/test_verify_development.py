"""Tests for `application.commands.verify` in a development phase.

Updated for 0.3.0: the planning phase that produces the frozen
roadmap now closes with a summary, so `_plan_and_freeze` writes one
before calling `close --freeze`.
"""

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
note = "demo"

[[interfaces]]
name = "greet"
kind = "function"
module = "src/app.py"
signature = "def greet(name)"
doc = ""

[[steps]]
number = 1
title = "Greet"
goal = "Write greet."
files = ["src/app.py"]
interfaces = ["greet"]
acceptance = []
depends_on = []
"""

_GREET = "def greet(name):\n    return name\n"


def _plan_and_freeze(root: Path, deps) -> None:
    """Run a short planning phase to produce a frozen roadmap."""
    assert cmd_new_phase(Namespace(name="plan", kind="planning"), deps) == 0
    deps.clipboard.text = (
        "<<<FILE:.harness/roadmap.toml>>>\n" + _ROADMAP + "<<<END>>>\n"
    )
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)
    arch = root / "docs" / "architecture.md"
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("Architecture\n", encoding="utf-8")

    # 0.3.0: close requires a summary.
    deps.clipboard.text = (
        "<<<FILE:.harness/summaries/plan.md>>>\nplanning done\n<<<END>>>\n"
    )
    assert cmd_apply(Namespace(step="summary", from_file=None), deps) == 0

    assert cmd_close(Namespace(tag=False, freeze=True), deps) == 0
    assert cmd_new_phase(Namespace(name="dev", kind="development"), deps) == 0


def test_development_happy_path(harness_root: Path, deps) -> None:
    """A matching step passes and advances `roadmap_step`."""
    _plan_and_freeze(harness_root, deps)
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    assert cmd_apply(Namespace(step="01", from_file=None), deps) == 0
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.roadmap_step == 1


def test_development_blocker_does_not_advance(harness_root: Path, deps) -> None:
    """A blocker deviation is committed but does not advance the plan."""
    _plan_and_freeze(harness_root, deps)
    blocker = (
        ".harness/deviations/step-01.toml",
        '[[deviation]]\ntype = "blocker"\nreason = "nope"\n',
    )
    deps.clipboard.text = f"<<<FILE:{blocker[0]}>>>\n{blocker[1]}<<<END>>>\n"
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)
    state = load_state(deps.fs, harness_root)
    assert state.roadmap_step == 0


def test_development_past_end_of_roadmap(harness_root: Path, deps) -> None:
    """A step past the end of the roadmap fails."""
    _plan_and_freeze(harness_root, deps)
    # First step succeeds.
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)

    # Second step targets a roadmap position that does not exist.
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    cmd_apply(Namespace(step="02", from_file=None), deps)
    assert cmd_verify(Namespace(step="02", clipboard=False), deps) == 1


def test_development_bad_step_argument(harness_root: Path, deps) -> None:
    """A non-integer step argument exits 2."""
    _plan_and_freeze(harness_root, deps)
    assert cmd_verify(Namespace(step="abc", clipboard=False), deps) == 2
