"""Tests for `application.commands.read`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.read import cmd_read


def _args(path: str, clipboard: bool = False) -> Namespace:
    """Minimal namespace for `cmd_read`."""
    return Namespace(path=path, clipboard=clipboard)


def test_read_single_file(harness_root: Path, deps, capsys) -> None:
    """A file is wrapped in step markers with a token header."""
    (harness_root / "x.py").write_text("x = 1\n", encoding="utf-8")
    assert cmd_read(_args("x.py"), deps) == 0
    out = capsys.readouterr().out
    assert "<<<FILE:x.py>>>" in out
    assert "<<<END>>>" in out
    assert "<!-- x.py" in out


def test_read_missing(harness_root: Path, deps) -> None:
    """A missing path exits 2."""
    assert cmd_read(_args("nope.py"), deps) == 2


def test_read_directory(harness_root: Path, deps, capsys) -> None:
    """A directory reads its `.py` and `.md` files."""
    d = harness_root / "pkg"
    d.mkdir()
    (d / "a.py").write_text("x = 1\n", encoding="utf-8")
    (d / "b.md").write_text("hi\n", encoding="utf-8")
    assert cmd_read(_args("pkg"), deps) == 0
    out = capsys.readouterr().out
    assert "a.py" in out
    assert "b.md" in out


def test_read_absolute_glob_rejected(harness_root: Path, deps, capsys) -> None:
    """An absolute glob pattern fails with a specific message."""
    assert cmd_read(_args("/tmp/*.py"), deps) == 2
    err = capsys.readouterr().err
    assert "absolute glob" in err


def test_read_oversize_warning_uses_rel_path(harness_root: Path, deps, capsys) -> None:
    """The oversize warning names the relative path, not the basename."""
    sub = harness_root / "pkg"
    sub.mkdir()
    # `InMemoryCounter` returns `len(text)`. Config max is 6000.
    (sub / "big.py").write_text("x" * 7000, encoding="utf-8")
    assert cmd_read(_args("pkg/big.py"), deps) == 0
    err = capsys.readouterr().err
    assert "pkg/big.py" in err


def test_read_glob_still_works(harness_root: Path, deps, capsys) -> None:
    """A relative glob pattern still expands."""
    (harness_root / "a.py").write_text("a\n", encoding="utf-8")
    (harness_root / "b.py").write_text("b\n", encoding="utf-8")
    assert cmd_read(_args("*.py"), deps) == 0
    out = capsys.readouterr().out
    assert "a.py" in out
    assert "b.py" in out
