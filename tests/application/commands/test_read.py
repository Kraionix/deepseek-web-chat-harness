"""Tests for `application.commands.read`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.read import cmd_read


def _args(path: str, clipboard: bool = False) -> Namespace:
    """Minimal namespace for `cmd_read`."""
    return Namespace(path=path, clipboard=clipboard)


def test_read_single_file(harness_root: Path, deps, capsys) -> None:
    """A file is wrapped in block markers with a token header."""
    (harness_root / "x.py").write_text("x = 1\n", encoding="utf-8")
    assert cmd_read(_args("x.py"), deps) == 0
    out = capsys.readouterr().out
    assert "<<<FILE:x.py>>>" in out
    assert "<<<END>>>" in out
    assert "<!-- x.py" in out


def test_read_missing(harness_root: Path, deps) -> None:
    """A missing path exits 2."""
    assert cmd_read(_args("nope.py"), deps) == 2


def test_read_absolute_glob_rejected(harness_root: Path, deps, capsys) -> None:
    """An absolute glob pattern fails with a specific message."""
    assert cmd_read(_args("/tmp/*.py"), deps) == 2
    assert "absolute glob" in capsys.readouterr().err
