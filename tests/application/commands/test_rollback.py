"""Tests for `application.commands.rollback`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.new_phase import cmd_new_phase
from dwch.application.commands.rollback import cmd_rollback
from dwch.application.commands.verify import cmd_verify
from dwch.application.state import load_state

_STEP = "<<<FILE:src/a.py>>>\nx = 1\n<<<END>>>\n"


def _args(yes: bool = True) -> Namespace:
    """Minimal namespace for `cmd_rollback`."""
    return Namespace(yes=yes)


def test_rollback_requires_yes(harness_root: Path, deps) -> None:
    """Without `--yes`, rollback is refused."""
    assert cmd_rollback(_args(yes=False), deps) == 2


def test_rollback_increments_count(harness_root: Path, deps) -> None:
    """A successful rollback increments `rollback_count`."""
    cmd_new_phase(Namespace(name="p", kind="planning"), deps)
    deps.clipboard.text = _STEP
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)

    before = load_state(deps.fs, harness_root)
    assert cmd_rollback(_args(), deps) == 0
    after = load_state(deps.fs, harness_root)
    assert after.rollback_count == before.rollback_count + 1


def test_rollback_no_step(harness_root: Path, deps) -> None:
    """Without a step to roll back, rollback refuses."""
    cmd_new_phase(Namespace(name="p", kind="planning"), deps)
    assert cmd_rollback(_args(), deps) == 2
