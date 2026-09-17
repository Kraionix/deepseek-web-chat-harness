"""Tests for `application.lock`."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from dwch.adapters.filesystem import LocalFilesystem
from dwch.application import lock as lm
from dwch.domain.models import Lock
from dwch.shared.errors import LockError

_FS = LocalFilesystem()


def _setup(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    """Create a roadmap and one architecture file; return their paths."""
    roadmap = tmp_path / ".harness" / "roadmap.toml"
    roadmap.parent.mkdir(parents=True, exist_ok=True)
    roadmap.write_text("[meta]\nversion = 1\n", encoding="utf-8")
    arch = tmp_path / "docs" / "architecture.md"
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("A\n", encoding="utf-8")
    return roadmap, tmp_path / ".harness" / "roadmap.lock", [arch]


def test_write_and_load_round_trip(tmp_path: Path) -> None:
    """Writing then loading a lock preserves every field."""
    roadmap, lock_path, arch = _setup(tmp_path)
    lock = lm.write(
        _FS,
        lock_path,
        tmp_path,
        roadmap,
        arch,
        at="2026-01-01T00:00:00+00:00",
        phase="phase-01",
        commit="abc1234",
        version=1,
    )
    loaded = lm.load(_FS, lock_path)
    assert loaded is not None
    assert loaded == lock


def test_load_missing(tmp_path: Path) -> None:
    """A missing lock returns None."""
    assert lm.load(_FS, tmp_path / "nope.lock") is None


def test_load_bad_toml(tmp_path: Path) -> None:
    """Malformed TOML raises `LockError`."""
    p = tmp_path / "x.lock"
    p.write_text("not = ", encoding="utf-8")
    with pytest.raises(LockError, match="invalid TOML"):
        lm.load(_FS, p)


def test_load_missing_section(tmp_path: Path) -> None:
    """A file without `[lock]` raises `LockError`."""
    p = tmp_path / "x.lock"
    p.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(LockError, match="missing \\[lock\\]"):
        lm.load(_FS, p)


def test_check_clean(tmp_path: Path) -> None:
    """A lock written from the current state has no problems."""
    roadmap, lock_path, arch = _setup(tmp_path)
    lock = lm.write(
        _FS,
        lock_path,
        tmp_path,
        roadmap,
        arch,
        at="",
        phase="",
        commit="",
        version=1,
    )
    assert lm.check(_FS, lock, tmp_path, roadmap, arch) == []


def test_check_detects_roadmap_drift(tmp_path: Path) -> None:
    """Changing the roadmap after freezing reports it."""
    roadmap, lock_path, arch = _setup(tmp_path)
    lock = lm.write(
        _FS,
        lock_path,
        tmp_path,
        roadmap,
        arch,
        at="",
        phase="",
        commit="",
        version=1,
    )
    roadmap.write_text("[meta]\nversion = 2\n", encoding="utf-8")
    problems = lm.check(_FS, lock, tmp_path, roadmap, arch)
    assert any("roadmap" in p for p in problems)


def test_check_detects_architecture_drift(tmp_path: Path) -> None:
    """Changing a frozen architecture file reports it."""
    roadmap, lock_path, arch = _setup(tmp_path)
    lock = lm.write(
        _FS,
        lock_path,
        tmp_path,
        roadmap,
        arch,
        at="",
        phase="",
        commit="",
        version=1,
    )
    arch[0].write_text("B\n", encoding="utf-8")
    assert lm.check(_FS, lock, tmp_path, roadmap, arch) == ["docs/architecture.md"]


def test_check_detects_missing_file(tmp_path: Path) -> None:
    """A missing frozen file is reported."""
    roadmap, lock_path, arch = _setup(tmp_path)
    lock = lm.write(
        _FS,
        lock_path,
        tmp_path,
        roadmap,
        arch,
        at="",
        phase="",
        commit="",
        version=1,
    )
    arch[0].unlink()
    assert "docs/architecture.md" in lm.check(_FS, lock, tmp_path, roadmap, arch)


def test_check_detects_extra_file(tmp_path: Path) -> None:
    """A new architecture file not in the lock is reported."""
    roadmap, lock_path, arch = _setup(tmp_path)
    lock = lm.write(
        _FS,
        lock_path,
        tmp_path,
        roadmap,
        arch,
        at="",
        phase="",
        commit="",
        version=1,
    )
    extra = tmp_path / "docs" / "extra.md"
    extra.write_text("E\n", encoding="utf-8")
    assert "docs/extra.md" in lm.check(_FS, lock, tmp_path, roadmap, [*arch, extra])


def test_render_escapes_strings() -> None:
    """Rendering a lock with control characters stays parseable."""
    lock = Lock(
        at="a\nb",
        phase="p",
        commit="c",
        version=1,
        roadmap_sha256="h",
        architecture=(),
    )
    text = lm.render(lock)
    assert "\\n" in text
    assert tomllib.loads(text)["lock"]["at"] == "a\nb"
