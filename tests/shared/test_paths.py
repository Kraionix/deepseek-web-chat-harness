"""Tests for `shared.paths`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from dwch.shared.errors import FormatError
from dwch.shared.paths import check_safe_root, normalize_rel, safe_path


def test_normalize_rel_collapses_backslashes() -> None:
    """Backslashes become forward slashes."""
    assert normalize_rel("a\\b\\c") == "a/b/c"


def test_normalize_rel_collapses_double_slashes() -> None:
    """Repeated slashes collapse to one."""
    assert normalize_rel("a//b///c") == "a/b/c"


def test_normalize_rel_strips_trailing_slash() -> None:
    """A trailing slash is removed."""
    assert normalize_rel("a/b/") == "a/b"


def test_normalize_rel_preserves_single_slash() -> None:
    """A lone slash is left alone."""
    assert normalize_rel("/") == "/"


def test_check_safe_root_accepts_project_dir(tmp_path: Path) -> None:
    """A fresh project directory is accepted."""
    root = tmp_path / "proj"
    root.mkdir()
    assert check_safe_root(root) is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_check_safe_root_refuses_drive_root() -> None:
    """`C:\\` is refused on Windows."""
    assert check_safe_root(Path("C:/")) is not None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_check_safe_root_refuses_users() -> None:
    """`C:\\Users` is refused on Windows."""
    assert check_safe_root(Path("C:/Users")) is not None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
def test_check_safe_root_refuses_posix_root() -> None:
    """`/` is refused on POSIX."""
    assert check_safe_root(Path("/")) is not None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
def test_check_safe_root_refuses_etc() -> None:
    """`/etc` is refused on POSIX."""
    assert check_safe_root(Path("/etc")) is not None


def test_check_safe_root_accepts_inside_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project inside the home directory is accepted."""
    fake_home = tmp_path / "fakehome"
    project = fake_home / "proj"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    assert check_safe_root(project) is None


def test_check_safe_root_refuses_home_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The home directory itself is refused."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    assert check_safe_root(fake_home) is not None


def test_safe_path_accepts_normal_relative(tmp_path: Path) -> None:
    """A normal relative path resolves under the root."""
    root = tmp_path.resolve()
    assert safe_path("src/app.py", root) == root / "src" / "app.py"


def test_safe_path_accepts_nested(tmp_path: Path) -> None:
    """A deeply nested path is accepted."""
    root = tmp_path.resolve()
    assert safe_path("a/b/c/d.py", root) == root / "a" / "b" / "c" / "d.py"


def test_safe_path_normalizes_backslashes(tmp_path: Path) -> None:
    """Backslashes in the input are normalized to forward slashes."""
    root = tmp_path.resolve()
    assert safe_path("a\\b\\c.py", root) == root / "a" / "b" / "c.py"


def test_safe_path_accepts_dot_harness(tmp_path: Path) -> None:
    """A leading-dot directory such as `.harness/` is accepted."""
    root = tmp_path.resolve()
    assert safe_path(".harness/state.toml", root) == root / ".harness" / "state.toml"


def test_safe_path_accepts_dotfile(tmp_path: Path) -> None:
    """A leading-dot filename such as `.gitignore` is accepted."""
    root = tmp_path.resolve()
    assert safe_path(".gitignore", root) == root / ".gitignore"


def test_safe_path_rejects_empty(tmp_path: Path) -> None:
    """An empty string is refused."""
    with pytest.raises(FormatError, match="empty path"):
        safe_path("", tmp_path)


def test_safe_path_rejects_whitespace_only(tmp_path: Path) -> None:
    """A whitespace-only string is refused."""
    with pytest.raises(FormatError, match="empty path"):
        safe_path("   ", tmp_path)


def test_safe_path_rejects_absolute(tmp_path: Path) -> None:
    """A leading slash is refused."""
    with pytest.raises(FormatError, match="absolute path"):
        safe_path("/etc/passwd", tmp_path)


def test_safe_path_rejects_drive_relative(tmp_path: Path) -> None:
    """`C:foo` is drive-relative and is refused."""
    with pytest.raises(FormatError, match="drive-relative"):
        safe_path("C:foo", tmp_path)


def test_safe_path_rejects_parent_traversal(tmp_path: Path) -> None:
    """`..` components are refused."""
    with pytest.raises(FormatError, match="invalid path component"):
        safe_path("a/../b", tmp_path)


def test_safe_path_rejects_dot_component(tmp_path: Path) -> None:
    """A `.` component is refused, not normalized away."""
    with pytest.raises(FormatError, match="invalid path component"):
        safe_path("a/./b", tmp_path)


def test_safe_path_rejects_colon(tmp_path: Path) -> None:
    """`:` inside a component is refused."""
    with pytest.raises(FormatError, match="contains ':'"):
        safe_path("src/a:b.py", tmp_path)


def test_safe_path_rejects_control_character(tmp_path: Path) -> None:
    """A control character in a component is refused."""
    with pytest.raises(FormatError, match="control character"):
        safe_path("a\x01b/c.py", tmp_path)


@pytest.mark.parametrize("name", ["CON", "con.txt", "NUL", "COM1", "LPT9"])
def test_safe_path_rejects_reserved_windows_names(tmp_path: Path, name: str) -> None:
    """A Windows reserved name is refused, case-insensitive."""
    with pytest.raises(FormatError, match="reserved Windows name"):
        safe_path(f"src/{name}", tmp_path)


@pytest.mark.parametrize("ch", ["<", ">", '"', "|", "?", "*"])
def test_safe_path_rejects_invalid_chars(tmp_path: Path, ch: str) -> None:
    """Every reserved Windows character is refused."""
    with pytest.raises(FormatError, match="contains"):
        safe_path(f"src/a{ch}b.py", tmp_path)


def test_safe_path_rejects_leading_space(tmp_path: Path) -> None:
    """A leading space in a component is refused."""
    with pytest.raises(FormatError, match="leading or trailing"):
        safe_path("src/ a.py", tmp_path)


def test_safe_path_rejects_trailing_space(tmp_path: Path) -> None:
    """A trailing space in a component is refused."""
    with pytest.raises(FormatError, match="leading or trailing"):
        safe_path("src/a.py ", tmp_path)


def test_safe_path_rejects_trailing_dot(tmp_path: Path) -> None:
    """A trailing dot in a component is refused."""
    with pytest.raises(FormatError, match="leading or trailing"):
        safe_path("src/a./b.py", tmp_path)


def test_safe_path_rejects_long_component(tmp_path: Path) -> None:
    """A component longer than 255 bytes is refused."""
    long_name = "a" * 256 + ".py"
    with pytest.raises(FormatError, match="longer than 255 bytes"):
        safe_path(f"src/{long_name}", tmp_path)


def _symlink_or_skip(src: Path, dst: Path) -> None:
    """Create a symlink; skip the test when the platform refuses."""
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")


def test_safe_path_refuses_symlink_component(tmp_path: Path) -> None:
    """A path whose resolution changes is refused."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link"
    _symlink_or_skip(outside, link)
    with pytest.raises(FormatError, match="symlinks are not supported"):
        safe_path("link/file.py", root.resolve())


def test_safe_path_refuses_broken_symlink(tmp_path: Path) -> None:
    """A broken symlink is reported, not silently followed."""
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "nonexistent"
    link = root / "link"
    _symlink_or_skip(target, link)
    with pytest.raises(FormatError, match="symlinks are not supported"):
        safe_path("link/file.py", root.resolve())
