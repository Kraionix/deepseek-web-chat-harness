"""Tests for `application.commands.close`.

The five tests marked `slow` are the ones the 0.3.1 benchmark put
above the 0.2-second threshold: each runs `cmd_new_phase` (which
commits), then `apply summary`, then `close`, and each of those
three is a git round trip. The other four tests are here for
coverage of the guard clauses, which fire before the expensive
path.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

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


def _apply_summary(deps, phase: str, body: str = "summary text") -> None:
    """Write a phase summary via `apply summary`."""
    deps.clipboard.text = (
        f"<<<FILE:.harness/summaries/{phase}.md>>>\n{body}\n<<<END>>>\n"
    )
    assert cmd_apply(Namespace(step="summary", from_file=None), deps) == 0


def _planning_with_roadmap(root: Path, deps) -> None:
    """Produce a valid roadmap during a planning phase."""
    cmd_new_phase(Namespace(name="plan", kind="planning"), deps)
    deps.clipboard.text = (
        "<<<FILE:.harness/roadmap.toml>>>\n" + _ROADMAP + "<<<END>>>\n"
    )
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)


def test_close_requires_summary(harness_root: Path, deps, capsys) -> None:
    """A close without a summary on disk is refused."""
    cmd_new_phase(Namespace(name="plan", kind="planning"), deps)
    assert cmd_close(_args(), deps) == 2
    assert "no summary" in capsys.readouterr().err


@pytest.mark.slow
def test_close_freezes_roadmap(harness_root: Path, deps) -> None:
    """`--freeze` writes the lock, marks state frozen, records summary."""
    _planning_with_roadmap(harness_root, deps)
    arch = harness_root / "docs" / "architecture.md"
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("Architecture\n", encoding="utf-8")

    _apply_summary(deps, "plan")

    assert cmd_close(_args(freeze=True), deps) == 0
    assert (harness_root / ".harness" / "roadmap.lock").is_file()
    state = load_state(deps.fs, harness_root)
    assert state.roadmap_frozen
    assert state.summary_phase == "plan"
    assert state.summary_written_at != ""


def test_close_freeze_outside_planning(harness_root: Path, deps) -> None:
    """`--freeze` in a development phase is refused."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    _apply_summary(deps, "dev")
    assert cmd_close(_args(freeze=True), deps) == 2


def test_close_freeze_no_roadmap(harness_root: Path, deps) -> None:
    """`--freeze` without a roadmap on disk is refused."""
    cmd_new_phase(Namespace(name="plan", kind="planning"), deps)
    _apply_summary(deps, "plan")
    assert cmd_close(_args(freeze=True), deps) == 2


@pytest.mark.slow
def test_close_without_freeze(harness_root: Path, deps) -> None:
    """A plain `close` finalizes the phase."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    _apply_summary(deps, "dev")
    assert cmd_close(_args(), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.summary_phase == "dev"


@pytest.mark.slow
def test_close_updates_state_summary(harness_root: Path, deps) -> None:
    """`close` records the summary phase and a non-empty timestamp."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    _apply_summary(deps, "dev", "phase dev wrap-up")
    assert cmd_close(_args(), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.summary_phase == "dev"
    assert state.summary_written_at != ""


@pytest.mark.slow
def test_close_twice_refused(harness_root: Path, deps, capsys) -> None:
    """A second `close` on the same phase is refused."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    _apply_summary(deps, "dev")
    assert cmd_close(_args(), deps) == 0
    assert cmd_close(_args(), deps) == 2
    assert "already closed" in capsys.readouterr().err


def test_close_commit_failure_restores_state(
    harness_root: Path, deps, broken_deps, capsys
) -> None:
    """A failed commit leaves state at the pre-close values."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    _apply_summary(deps, "dev")
    before = load_state(deps.fs, harness_root)

    rc = cmd_close(Namespace(tag=False, freeze=False), broken_deps)
    assert rc == 2

    after = load_state(deps.fs, harness_root)
    assert after.last_closed == before.last_closed
    assert after.summary_phase == before.summary_phase
    assert after.summary_written_at == before.summary_written_at

    err = capsys.readouterr().err
    assert "commit failed" in err
    assert "state was restored" in err
    assert "was not closed" in err


@pytest.mark.slow
def test_close_tag_uses_seconds(harness_root: Path, deps) -> None:
    """A `--tag` close produces a tag with second resolution."""
    import subprocess

    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    _apply_summary(deps, "dev")
    assert cmd_close(Namespace(tag=True, freeze=False), deps) == 0

    tags = subprocess.run(
        ["git", "tag", "-l"],
        cwd=harness_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    session_tags = [t for t in tags if t.startswith("session-")]
    assert len(session_tags) == 1
    suffix = session_tags[0][len("session-") :]
    # Format: YYYYMMDD-HHMMSS → 8 digits, dash, 6 digits.
    assert len(suffix) == 15
    assert suffix[8] == "-"
    assert suffix[:8].isdigit()
    assert suffix[9:].isdigit()
