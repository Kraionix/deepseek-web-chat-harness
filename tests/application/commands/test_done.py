"""Tests for `application.commands.done`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.done import cmd_done
from dwch.application.commands.start import cmd_start
from dwch.application.commands.verify import cmd_verify
from dwch.application.state import load_state

_PLAN_TOML = """\
[meta]
version = 1
note = "x"

[[tasks]]
id = "t1"
title = "First"
goal = "Write t1."
files = ["src/a.py"]
interfaces = []
acceptance = []
depends_on = []
"""


def _plan_args() -> Namespace:
    """`apply` namespace with a message on the clipboard."""
    return Namespace(from_file=None)


def _start(root: Path, deps) -> None:
    """Start a planning phase."""
    assert cmd_start(Namespace(goal="plan", kind="planning"), deps) == 0


def _write_plan(deps) -> None:
    """Send the plan through `apply` and verify it."""
    deps.clipboard.text = "<<<FILE:.harness/plan.toml>>>\n" + _PLAN_TOML + "<<<END>>>\n"
    assert cmd_apply(_plan_args(), deps) == 0
    assert cmd_verify(Namespace(clipboard=False), deps) == 0


@pytest.mark.slow
def test_done_requires_verify(harness_root: Path, deps, capsys) -> None:
    """Without a successful verify, `done` refuses."""
    _start(harness_root, deps)
    assert cmd_done(Namespace(), deps) == 2
    assert "not verified" in capsys.readouterr().err


@pytest.mark.slow
def test_done_commits_and_freezes_plan(harness_root: Path, deps) -> None:
    """`done` on a planning task commits, closes, and freezes the plan."""
    _start(harness_root, deps)
    _write_plan(deps)
    assert cmd_done(Namespace(), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.phase_status == "closed"
    assert state.plan_frozen is True
    assert state.plan_sha256 != ""
    assert state.plan_version == 1


@pytest.mark.slow
def test_done_commit_failure_restores_state(
    harness_root: Path, deps, broken_deps, capsys
) -> None:
    """A failed commit leaves state at the pre-done values."""
    _start(harness_root, deps)
    _write_plan(deps)
    before = load_state(deps.fs, harness_root)
    # broken_deps shares the same project root and clipboard.
    rc = cmd_done(Namespace(), broken_deps)
    assert rc == 2
    after = load_state(deps.fs, harness_root)
    assert after.phase_status == before.phase_status
    assert after.plan_frozen == before.plan_frozen
    assert "state was restored" in capsys.readouterr().err
