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
    """Every deviation type parses."""
    for dtype in DeviationType:
        body = (
            "[[deviation]]\n"
            f'type = "{dtype.value}"\n'
            'affected = ["a.py"]\n'
            'reason = "r"\n'
            'detail = ""\n'
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


def test_parse_deviation_string_raises() -> None:
    """A string `deviation` field is a `DeviationError`."""
    with pytest.raises(DeviationError, match="expected a list of tables"):
        dm.parse('deviation = "abc"\n', Path("x.toml"))


def test_parse_affected_string_raises() -> None:
    """A bare string `affected` is rejected, not split into characters."""
    body = '[[deviation]]\ntype = "assumption"\naffected = "src/x.py"\nreason = "r"\n'
    with pytest.raises(DeviationError, match="expected a list of strings"):
        dm.parse(body, Path("x.toml"))


def test_render_parse_round_trip() -> None:
    """Rendering then parsing preserves a reason with a newline."""
    devs = [
        Deviation(
            type=DeviationType.ASSUMPTION,
            affected=("a.py", "b.py"),
            reason="line one\nline two",
            detail="with\ttab",
        )
    ]
    rendered = dm.render(devs)
    assert dm.parse(rendered, Path("x.toml")) == devs


def test_load_missing(tmp_path: Path) -> None:
    """A missing task file yields an empty list."""
    assert dm.load(_FS, tmp_path, "t1") == []


def test_load_present(tmp_path: Path) -> None:
    """An existing task file is parsed."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "t1.toml").write_text(
        '[[deviation]]\ntype = "assumption"\nreason = "r"\n',
        encoding="utf-8",
    )
    result = dm.load(_FS, tmp_path, "t1")
    assert result[0].type is DeviationType.ASSUMPTION


def test_write_creates_file(tmp_path: Path) -> None:
    """`write` creates `{task_id}.toml`."""
    dev = Deviation(
        type=DeviationType.ASSUMPTION,
        affected=("x.py",),
        reason="r",
        detail="",
    )
    dm.write(_FS, tmp_path, "t1", [dev])
    assert (tmp_path / "t1.toml").is_file()


def test_write_empty_noop(tmp_path: Path) -> None:
    """An empty list writes nothing."""
    dm.write(_FS, tmp_path, "t1", [])
    assert not (tmp_path / "t1.toml").exists()


def test_load_recent_limits(tmp_path: Path) -> None:
    """`load_recent` returns at most `n` files, newest last."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    for i in (1, 2, 3):
        (tmp_path / f"t{i}.toml").write_text(
            f'[[deviation]]\ntype = "assumption"\nreason = "{i}"\n',
            encoding="utf-8",
        )
    result = dm.load_recent(_FS, tmp_path, 2)
    assert len(result) == 2
    assert result[-1].reason == "3"


def test_load_recent_zero_returns_empty(tmp_path: Path) -> None:
    """`n == 0` returns an empty list, not the whole set."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "t1.toml").write_text(
        '[[deviation]]\ntype = "assumption"\nreason = "r"\n',
        encoding="utf-8",
    )
    assert dm.load_recent(_FS, tmp_path, 0) == []


def test_load_recent_missing_dir(tmp_path: Path) -> None:
    """A missing directory yields an empty list."""
    assert dm.load_recent(_FS, tmp_path / "nope", 5) == []


def test_summarize_empty() -> None:
    """No deviations renders a placeholder."""
    assert "(none)" in dm.summarize([], 5)


def test_summarize_zero_returns_placeholder() -> None:
    """`n == 0` renders the placeholder, not the whole list."""
    devs = [
        Deviation(
            type=DeviationType.ASSUMPTION,
            affected=(),
            reason="r",
            detail="",
        )
    ]
    assert "(none)" in dm.summarize(devs, 0)


def test_summarize_lists_recent() -> None:
    """The summary lists the last `n` deviations."""
    devs = [
        Deviation(
            type=DeviationType.ASSUMPTION,
            affected=(),
            reason=f"r{i}",
            detail="",
        )
        for i in range(3)
    ]
    text = dm.summarize(devs, 2)
    assert "r1" in text
    assert "r2" in text
