"""End-to-end lifecycle tests across every command.

Every test here is marked `slow`: each one runs a full
planning-to-development cycle.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.done import cmd_done
from dwch.application.commands.next import cmd_next
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

_GREET = "def greet(name):\n    return name\n"


def test_planning_then_development(harness_root: Path, deps) -> None:
    """A full planning-to-development cycle runs clean."""
    assert cmd_start(Namespace(goal="plan", kind="planning"), deps) == 0
    deps.clipboard.text = "<<<FILE:.harness/plan.toml>>>\n" + _PLAN + "<<<END>>>\n"
    assert cmd_apply(Namespace(from_file=None), deps) == 0
    assert cmd_verify(Namespace(clipboard=False), deps) == 0
    assert cmd_done(Namespace(), deps) == 0

    frozen = load_state(deps.fs, harness_root)
    assert frozen.plan_frozen is True
    assert frozen.plan_sha256 != ""
    assert frozen.phase_status == "closed"

    assert cmd_start(Namespace(goal="dev", kind="development"), deps) == 0
    assert cmd_next(Namespace(), deps) == 0
    assert "section: contract" in deps.clipboard.text
    assert "section: task" in deps.clipboard.text

    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    assert cmd_apply(Namespace(from_file=None), deps) == 0
    assert cmd_verify(Namespace(clipboard=False), deps) == 0
    assert cmd_done(Namespace(), deps) == 0

    final = load_state(deps.fs, harness_root)
    assert final.plan_position == 1
    assert final.phase_status == "closed"


def test_failed_verify_then_fix_bootstrap(harness_root: Path, deps) -> None:
    """A failed verify produces a report, a hint, and a fix-bootstrap."""
    assert cmd_start(Namespace(goal="plan", kind="planning"), deps) == 0
    deps.clipboard.text = "<<<FILE:.harness/plan.toml>>>\n" + _PLAN + "<<<END>>>\n"
    cmd_apply(Namespace(from_file=None), deps)
    cmd_verify(Namespace(clipboard=False), deps)
    cmd_done(Namespace(), deps)

    assert cmd_start(Namespace(goal="dev", kind="development"), deps) == 0
    deps.clipboard.text = "<<<FILE:src/wrong.py>>>\nx = 1\n<<<END>>>\n"
    cmd_apply(Namespace(from_file=None), deps)
    assert cmd_verify(Namespace(clipboard=False), deps) == 1

    state = load_state(deps.fs, harness_root)
    assert state.failure_count == 1
    assert state.plan_position == 0

    from dwch.application.commands.fix import cmd_fix

    deps.clipboard.text = ""
    assert cmd_fix(Namespace(), deps) == 0
    assert "section: failure" in deps.clipboard.text
