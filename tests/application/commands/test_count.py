"""Tests for `application.commands.count`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.count import cmd_count


def _args(path: str) -> Namespace:
    """Minimal namespace for `cmd_count`."""
    return Namespace(path=path)


def test_count_file(harness_root: Path, deps, capsys) -> None:
    """A file prints one line with its count."""
    (harness_root / "x.py").write_text("x = 1\n", encoding="utf-8")
    assert cmd_count(_args("x.py"), deps) == 0
    assert "x.py: " in capsys.readouterr().out


def test_count_missing(harness_root: Path, deps) -> None:
    """A missing path exits 2."""
    assert cmd_count(_args("nope.py"), deps) == 2


def test_count_directory(harness_root: Path, deps, capsys) -> None:
    """A directory prints per-file counts and a total."""
    d = harness_root / "pkg"
    d.mkdir()
    (d / "a.py").write_text("a\n", encoding="utf-8")
    (d / "b.md").write_text("bb\n", encoding="utf-8")
    assert cmd_count(_args("pkg"), deps) == 0
    assert "TOTAL:" in capsys.readouterr().out
