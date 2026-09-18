"""Tests for `application.commands.log`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.log import cmd_log


def test_log_default(harness_root: Path, deps, capsys) -> None:
    """`log` prints at least the initial commit."""
    deps.git.commit_all(harness_root, "first")
    assert cmd_log(Namespace(n=5), deps) == 0
    assert "first" in capsys.readouterr().out


def test_log_zero_rejected(harness_root: Path, deps) -> None:
    """`log 0` exits 2."""
    assert cmd_log(Namespace(n=0), deps) == 2
