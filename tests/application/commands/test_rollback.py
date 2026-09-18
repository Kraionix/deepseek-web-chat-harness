"""Tests for `application.commands.rollback`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from dwch.application.commands.rollback import cmd_rollback
from dwch.application.commands.start import cmd_start
from dwch.application.state import load_state, save_state, with_updates

pytestmark = pytest.mark.slow


def test_rollback_requires_yes(harness_root: Path, deps) -> None:
    """Without `--yes`, rollback is refused."""
    assert cmd_rollback(Namespace(yes=False), deps) == 2


def test_rollback_rejects_lifecycle_head(harness_root: Path, deps, capsys) -> None:
    """A phase-start commit is not rolled back."""
    cmd_start(Namespace(goal="p", kind="planning"), deps)
    # Force state and a commit that is not a task commit.
    state = load_state(deps.fs, harness_root)
    save_state(deps.fs, harness_root, with_updates(state, plan_position=1))
    deps.git.commit_all(harness_root, "chore: adjust state for test")

    assert cmd_rollback(Namespace(yes=True), deps) == 2
    assert "not a task commit" in capsys.readouterr().err


def test_rollback_no_phase(harness_root: Path, deps) -> None:
    """Without a phase, the guard refuses before touching git."""
    assert cmd_rollback(Namespace(yes=True), deps) == 2
