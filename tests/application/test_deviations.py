"""Tests for `application.deviations`."""

from __future__ import annotations

from pathlib import Path

import pytest

from dwch.adapters.filesystem import LocalFilesystem
from dwch.application import deviations as dm
from dwch.domain.models import Deviation, DeviationType
from dwch.shared.errors import DeviationError

_FS = LocalFilesystem()


def test_parse_all_types() -> None:
    """Every declared deviation type parses."""
    for dtype in DeviationType:
        body = (
            "[[deviation]]\n"
            f'type = "{dtype.value}"\n'
            'affected = ["a.py"]\n'
            'reason = "r"\n'
            'detail = ""\n'
            "auto = false\n"
        )
        parsed = dm.parse(body, Path("x.toml"))
        assert parsed[0].type is dtype


def test_parse_unknown_type() -> None:
    """An unknown deviation type raises `DeviationError`."""
    body = '[[deviation]]\ntype = "nope"\n'
    with pytest.raises(DeviationError, match="unknown deviation type"):
        dm.parse(body, Path("x.toml"))


def test_parse_bad_toml() -> None:
    """Malformed TOML raises `DeviationError`."""
    with pytest.raises(DeviationError, match="invalid TOML"):
        dm.parse("not = ", Path("x.toml"))


def test_render_parse_round_trip() -> None:
    """Rendering then parsing preserves a reason with a newline."""
    devs = [
        Deviation(
            type=DeviationType.ASSUMPTION,
            affected=("a.py", "b.py"),
            reason="line one\nline two",
            detail="with\ttab",
            auto=False,
        )
    ]
    rendered = dm.render(devs)
    assert dm.parse(rendered, Path("x.toml")) == devs


def test_load_step_missing(tmp_path: Path) -> None:
    """A missing step file yields an empty list."""
    assert dm.load_step(_FS, tmp_path, 1) == []


def test_load_step_present(tmp_path: Path) -> None:
    """An existing step file is parsed."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "step-01.toml").write_text(
        '[[deviation]]\ntype = "assumption"\nreason = "r"\n',
        encoding="utf-8",
    )
    result = dm.load_step(_FS, tmp_path, 1)
    assert result[0].type is DeviationType.ASSUMPTION


def test_load_auto_step_missing(tmp_path: Path) -> None:
    """A missing auto file yields an empty list."""
    assert dm.load_auto_step(_FS, tmp_path, 1) == []


def test_load_recent_limits(tmp_path: Path) -> None:
    """`load_recent` returns at most `n` files, newest last."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    for i in (1, 2, 3):
        (tmp_path / f"step-{i:02d}.toml").write_text(
            f'[[deviation]]\ntype = "assumption"\nreason = "{i}"\n',
            encoding="utf-8",
        )
    result = dm.load_recent(_FS, tmp_path, 2)
    assert len(result) == 2
    assert result[-1].reason == "3"


def test_load_recent_missing_dir(tmp_path: Path) -> None:
    """A missing directory yields an empty list."""
    assert dm.load_recent(_FS, tmp_path / "nope", 5) == []


def test_write_auto_overwrites(tmp_path: Path) -> None:
    """`write_auto` overwrites an existing file."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    dev = Deviation(
        type=DeviationType.EXTRA_FILE,
        affected=("x.py",),
        reason="r",
        detail="",
        auto=True,
    )
    dm.write_auto(_FS, tmp_path, 1, [dev])
    dm.write_auto(_FS, tmp_path, 1, [dev])
    content = (tmp_path / "step-01-auto.toml").read_text(encoding="utf-8")
    assert "extra-file" in content


def test_write_auto_empty_noop(tmp_path: Path) -> None:
    """An empty list writes nothing."""
    dm.write_auto(_FS, tmp_path, 1, [])
    assert not (tmp_path / "step-01-auto.toml").exists()


def test_summarize_empty() -> None:
    """No deviations renders a placeholder."""
    assert "(none)" in dm.summarize([], 5)


def test_summarize_lists_recent() -> None:
    """The summary lists the last `n` deviations."""
    devs = [
        Deviation(
            type=DeviationType.ASSUMPTION,
            affected=(),
            reason=f"r{i}",
            detail="",
            auto=False,
        )
        for i in range(3)
    ]
    text = dm.summarize(devs, 2)
    assert "r1" in text
    assert "r2" in text
