"""End-to-end test of the two-phase transition flow.

The single test here runs three phases in sequence and is the
slowest in the suite. It is marked `slow` so a fast iteration can
skip it; run it before any commit that touches `close`,
`new-phase`, or the summary model.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.bootstrap import cmd_bootstrap
from dwch.application.commands.close import cmd_close
from dwch.application.commands.new_phase import cmd_new_phase
from dwch.application.commands.verify import cmd_verify
from dwch.application.state import load_state

pytestmark = pytest.mark.slow

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


def _step_args(step: str = "01") -> Namespace:
    """`apply NN` namespace."""
    return Namespace(step=step, from_file=None)


def _summary_args() -> Namespace:
    """`apply summary` namespace."""
    return Namespace(step="summary", from_file=None)


def _apply_summary(deps, phase: str, body: str) -> None:
    """Write a phase summary via `apply summary`."""
    deps.clipboard.text = (
        f"<<<FILE:.harness/summaries/{phase}.md>>>\n{body}\n<<<END>>>\n"
    )
    assert cmd_apply(_summary_args(), deps) == 0


def test_two_phase_transition(harness_root: Path, deps, capsys) -> None:
    """A planning phase and a development phase share a summary."""
    # Phase 00: planning.
    assert cmd_new_phase(Namespace(name="00-planning", kind="planning"), deps) == 0
    deps.clipboard.text = (
        "<<<FILE:.harness/roadmap.toml>>>\n" + _ROADMAP + "<<<END>>>\n"
    )
    assert cmd_apply(_step_args(), deps) == 0
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 0

    arch = harness_root / "docs" / "architecture.md"
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("Architecture\n", encoding="utf-8")

    _apply_summary(deps, "00-planning", "Designed the greet API.")
    assert cmd_close(Namespace(tag=False, freeze=True), deps) == 0

    state = load_state(deps.fs, harness_root)
    assert state.summary_phase == "00-planning"
    assert state.roadmap_frozen

    # Phase 01: development. Bootstrap must show the phase 00 summary.
    assert cmd_new_phase(Namespace(name="01-dev", kind="development"), deps) == 0
    assert cmd_bootstrap(Namespace(clipboard=False), deps) == 0
    boot1 = capsys.readouterr().out
    assert "section: previous_summary" in boot1
    assert "Designed the greet API" in boot1

    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    assert cmd_apply(_step_args(), deps) == 0
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 0

    _apply_summary(deps, "01-dev", "Implemented greet and verified.")
    assert cmd_close(Namespace(tag=False, freeze=False), deps) == 0

    # Phase 02: planning, a new cycle. Bootstrap shows the phase 01 summary.
    assert cmd_new_phase(Namespace(name="02-next", kind="planning"), deps) == 0
    assert cmd_bootstrap(Namespace(clipboard=False), deps) == 0
    boot2 = capsys.readouterr().out
    assert "section: previous_summary" in boot2
    assert "Implemented greet and verified" in boot2
