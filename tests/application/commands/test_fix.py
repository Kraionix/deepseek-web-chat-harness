"""Tests for `application.commands.fix`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.fix import cmd_fix
from dwch.application.commands.start import cmd_start


def test_fix_no_failure(harness_root: Path, deps, capsys) -> None:
    """Without a recorded failure, `fix` exits 2."""
    cmd_start(Namespace(goal="p", kind="planning"), deps)
    assert cmd_fix(Namespace(), deps) == 2
    assert "no recorded failure" in capsys.readouterr().err


def test_fix_bootstrap_contains_failure(harness_root: Path, deps) -> None:
    """A recorded failure yields a fix-bootstrap with a failure section."""
    cmd_start(Namespace(goal="p", kind="planning"), deps)
    from dwch.application.state import (
        load_state,
        save_state,
        set_verify_fail,
    )

    state = load_state(deps.fs, harness_root)
    save_state(
        deps.fs,
        harness_root,
        set_verify_fail(state, "planning", "compile", "a.py: bad", "at"),
    )
    deps.clipboard.text = ""
    assert cmd_fix(Namespace(), deps) == 0
    assert "section: failure" in deps.clipboard.text
    assert "a.py: bad" in deps.clipboard.text
