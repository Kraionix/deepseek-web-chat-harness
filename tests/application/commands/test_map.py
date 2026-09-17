"""Tests for `application.commands.map`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.map import cmd_map


def _args(
    root: str | None = None,
    full: bool = False,
    tree: bool = False,
    private: bool = False,
    clipboard: bool = False,
) -> Namespace:
    """Minimal namespace for `cmd_map`."""
    return Namespace(
        root=root,
        full=full,
        tree=tree,
        private=private,
        clipboard=clipboard,
    )


def test_map_no_root(harness_root: Path, deps) -> None:
    """Without `--root` and no `map_root`, `map` exits 2."""
    assert cmd_map(_args(), deps) == 2


def test_map_root_option(harness_root: Path, deps, capsys) -> None:
    """`--root` selects the tree to map."""
    src = harness_root / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert cmd_map(_args(root="src"), deps) == 0
    out = capsys.readouterr().out
    assert "a.py" in out
