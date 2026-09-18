"""End-to-end lifecycle tests across every command.

Updated for 0.3.0: `close` now requires a phase summary on disk.
Every close in this file is preceded by `dwch apply summary`.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.bootstrap import cmd_bootstrap
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
acceptance = ["greet returns a string"]
depends_on = []
"""

_GREET = "def greet(name):\n    return name\n"


def _apply_summary(deps, phase: str, body: str = "phase done") -> None:
    """Write a phase summary via `apply summary`."""
    deps.clipboard.text = (
        f"<<<FILE:.harness/summaries/{phase}.md>>>\n{body}\n<<<END>>>\n"
    )
    assert cmd_apply(Namespace(step="summary", from_file=None), deps) == 0


def test_planning_then_development(harness_root: Path, deps, capsys) -> None:
    """A full planning-to-development cycle runs clean."""
    # Planning: write and verify the roadmap.
    assert cmd_new_phase(Namespace(name="plan", kind="planning"), deps) == 0
    deps.clipboard.text = (
        "<<<FILE:.harness/roadmap.toml>>>\n" + _ROADMAP + "<<<END>>>\n"
    )
    assert cmd_apply(Namespace(step="01", from_file=None), deps) == 0
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 0

    # The freeze requires every configured architecture file.
    arch = harness_root / "docs" / "architecture.md"
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("Architecture\n", encoding="utf-8")

    # 0.3.0: close requires a summary.
    _apply_summary(deps, "plan", "Planning phase complete.")

    # Freeze the roadmap and start development.
    assert cmd_close(Namespace(tag=False, freeze=True), deps) == 0
    frozen = load_state(deps.fs, harness_root)
    assert frozen.roadmap_frozen
    assert frozen.roadmap_step == 0

    assert cmd_new_phase(Namespace(name="dev", kind="development"), deps) == 0
    assert cmd_bootstrap(Namespace(clipboard=False), deps) == 0
    boot = capsys.readouterr().out
    assert "section: current_step" in boot

    # Implement the first roadmap step.
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    assert cmd_apply(Namespace(step="01", from_file=None), deps) == 0
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 0

    done = load_state(deps.fs, harness_root)
    assert done.roadmap_step == 1


def test_bootstrap_after_roadmap_complete(harness_root: Path, deps, capsys) -> None:
    """Once every step is done, the bootstrap reports completion."""
    # Setup: freeze a single-step roadmap, then run the step.
    assert cmd_new_phase(Namespace(name="plan", kind="planning"), deps) == 0
    deps.clipboard.text = (
        "<<<FILE:.harness/roadmap.toml>>>\n" + _ROADMAP + "<<<END>>>\n"
    )
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)
    arch = harness_root / "docs" / "architecture.md"
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("Architecture\n", encoding="utf-8")

    # 0.3.0: close requires a summary.
    _apply_summary(deps, "plan", "Planning done.")

    cmd_close(Namespace(tag=False, freeze=True), deps)
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)

    # Bootstrap must now report completion instead of the current step.
    assert cmd_bootstrap(Namespace(clipboard=False), deps) == 0
    out = capsys.readouterr().out
    assert "section: roadmap_complete" in out
    assert "section: current_step" not in out
