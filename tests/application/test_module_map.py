"""Tests for `application.module_map`."""

from __future__ import annotations

from pathlib import Path

from dwch.adapters.filesystem import LocalFilesystem
from dwch.application.module_map import (
    build_module_map,
    extract_public_symbols,
    render_module_map,
)

_FS = LocalFilesystem()


_SAMPLE = '''\
"""A module."""

CONST = 1
ANNOTATED: int = 2
_PRIVATE = 3


def public_fn(a, b=1) -> int:
    return a + b


def _private_fn():
    pass


class Public:
    pass


class _Hidden:
    pass
'''


def test_build_module_map(tmp_path: Path) -> None:
    """Every public symbol appears; privates do not."""
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "mod.py").write_text(_SAMPLE, encoding="utf-8")
    modules = build_module_map(_FS, tmp_path)
    paths = [m.path for m in modules]
    assert "pkg/mod.py" in paths
    mod = next(m for m in modules if m.path == "pkg/mod.py")
    symbols = {s.name for s in mod.symbols}
    assert "public_fn" in symbols
    assert "Public" in symbols
    assert "CONST" in symbols
    assert "ANNOTATED" in symbols
    assert "_private_fn" not in symbols
    assert "_Hidden" not in symbols
    assert "_PRIVATE" not in symbols


def test_build_module_map_missing_root(tmp_path: Path) -> None:
    """A missing root yields no modules."""
    assert build_module_map(_FS, tmp_path / "nope") == []


def test_build_module_map_skips_syntax_error(tmp_path: Path) -> None:
    """A file with a syntax error is skipped."""
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    modules = build_module_map(_FS, tmp_path)
    assert [m.path for m in modules] == ["ok.py"]


def test_build_module_map_include_private(tmp_path: Path) -> None:
    """`include_private` surfaces private symbols too."""
    (tmp_path / "mod.py").write_text(_SAMPLE, encoding="utf-8")
    modules = build_module_map(_FS, tmp_path, include_private=True)
    symbols = {s.name for s in modules[0].symbols}
    assert "_private_fn" in symbols


def test_extract_public_symbols(tmp_path: Path) -> None:
    """Extraction returns a set of public names."""
    p = tmp_path / "mod.py"
    p.write_text(_SAMPLE, encoding="utf-8")
    names = extract_public_symbols(_FS, p)
    assert {"public_fn", "Public", "CONST", "ANNOTATED"} <= names


def test_extract_public_symbols_missing(tmp_path: Path) -> None:
    """A missing file yields an empty set."""
    assert extract_public_symbols(_FS, tmp_path / "nope.py") == set()


def test_render_brief(tmp_path: Path) -> None:
    """Brief rendering omits the docstring but shows signatures."""
    (tmp_path / "m.py").write_text(_SAMPLE, encoding="utf-8")
    modules = build_module_map(_FS, tmp_path)
    text = render_module_map(modules, full=False)
    assert "def public_fn" in text
    assert "A module." not in text


def test_render_full(tmp_path: Path) -> None:
    """Full rendering includes the module docstring."""
    (tmp_path / "m.py").write_text(_SAMPLE, encoding="utf-8")
    modules = build_module_map(_FS, tmp_path)
    text = render_module_map(modules, full=True)
    assert "A module." in text


def test_render_empty() -> None:
    """No modules renders a placeholder."""
    assert render_module_map([]) == "(no modules)\n"
