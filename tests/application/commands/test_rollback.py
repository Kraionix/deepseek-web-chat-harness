"""Tests for `application.commands.rollback`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.new_phase import cmd_new_phase
from dwch.application.commands.rollback import cmd_rollback
from dwch.application.commands.verify import cmd_verify
from dwch.application.state import load_state, save_state, with_updates

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


def test_rollback_rejects_lifecycle_head(harness_root: Path, deps, capsys) -> None:
    """A phase-start commit is not rolled back."""
    cmd_new_phase(Namespace(name="p", kind="planning"), deps)
    # Force current_step > 0 without a verify commit. This is the
    # shape a resumed development phase has right after new-phase:
    # current_step = state.roadmap_step > 0, and HEAD is the
    # phase-start commit.
    state = load_state(deps.fs, harness_root)
    save_state(
        deps.fs,
        harness_root,
        with_updates(state, current_step=3),
    )
    deps.git.commit_all(harness_root, "chore: adjust state for test")

    assert cmd_rollback(_args(), deps) == 2
    err = capsys.readouterr().err
    assert "not a verify commit" in err
    # The phase is untouched.
    after = load_state(deps.fs, harness_root)
    assert after.current_step == 3


def test_rollback_uses_microsecond_timestamp(harness_root: Path, deps) -> None:
    """The rollback marker commit uses `now_iso` (microseconds)."""
    cmd_new_phase(Namespace(name="p", kind="planning"), deps)
    deps.clipboard.text = _STEP
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)
    assert cmd_rollback(_args(), deps) == 0
    after = load_state(deps.fs, harness_root)
    # Microsecond ISO 8601 has a dot and a 6-digit fraction.
    assert "." in after.last_commit_date
    fraction = after.last_commit_date.split(".")[1].split("+")[0]
    assert len(fraction) == 6
