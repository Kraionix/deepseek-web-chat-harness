"""Tests for `application.commands.tree`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.tree import cmd_tree


def test_tree_default_root(harness_root: Path, deps, capsys) -> None:
    """`tree` with no argument uses `map_root` or the project root."""
    (harness_root / "src").mkdir()
    (harness_root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert cmd_tree(Namespace(root="src"), deps) == 0
    assert "a.py" in capsys.readouterr().out


def test_tree_missing_root(harness_root: Path, deps) -> None:
    """A missing root exits 2."""
    assert cmd_tree(Namespace(root="nope"), deps) == 2
