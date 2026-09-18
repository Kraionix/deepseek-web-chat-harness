"""End-to-end test of the two-phase transition flow."""

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
id = "greet"
title = "Greet"
goal = "Write greet."
files = ["src/app.py"]
interfaces = []
acceptance = []
depends_on = []
"""


def test_two_phase_transition(harness_root: Path, deps) -> None:
    """A planning phase and a development phase share committed state."""
    # Phase 00: planning.
    assert cmd_start(Namespace(goal="00-planning", kind="planning"), deps) == 0
    deps.clipboard.text = "<<<FILE:.harness/plan.toml>>>\n" + _PLAN + "<<<END>>>\n"
    assert cmd_apply(Namespace(from_file=None), deps) == 0
    assert cmd_verify(Namespace(clipboard=False), deps) == 0
    assert cmd_done(Namespace(), deps) == 0

    state = load_state(deps.fs, harness_root)
    assert state.plan_frozen is True
    assert state.phase_status == "closed"

    # Phase 01: development. No handoff, no summary — state and plan
    # carry everything.
    assert cmd_start(Namespace(goal="01-dev", kind="development"), deps) == 0
    deps.clipboard.text = "<<<FILE:src/app.py>>>\nprint(1)\n<<<END>>>\n"
    assert cmd_apply(Namespace(from_file=None), deps) == 0
    assert cmd_verify(Namespace(clipboard=False), deps) == 0
    assert cmd_done(Namespace(), deps) == 0

    final = load_state(deps.fs, harness_root)
    assert final.phase_status == "closed"
    assert final.plan_position == 1
