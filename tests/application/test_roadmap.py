"""Tests for `application.roadmap`."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from dwch.adapters.filesystem import LocalFilesystem
from dwch.application import roadmap as rm
from dwch.domain.models import (
    Roadmap,
    RoadmapInterface,
    RoadmapMeta,
    RoadmapStep,
    State,
)
from dwch.shared.errors import RoadmapError

_FS = LocalFilesystem()


_VALID = """\
[meta]
version = 1
note = "demo"

[[interfaces]]
name = "Task"
kind = "class"
module = "src/todo.py"
signature = "class Task"
doc = ""

[[steps]]
number = 1
title = "Models"
goal = "Write Task."
files = ["src/todo.py"]
interfaces = ["Task"]
acceptance = []
depends_on = []
"""


def _write(root: Path, body: str) -> Path:
    """Write a roadmap file under `root` and return its path."""
    path = root / ".harness" / "roadmap.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_load_valid(tmp_path: Path) -> None:
    """A well-formed roadmap loads with all sections populated."""
    path = _write(tmp_path, _VALID)
    roadmap = rm.load(_FS, path)
    assert roadmap.meta.version == 1
    assert roadmap.meta.note == "demo"
    assert len(roadmap.steps) == 1
    assert roadmap.steps[0].number == 1


def test_load_missing(tmp_path: Path) -> None:
    """A missing roadmap raises `RoadmapError`."""
    with pytest.raises(RoadmapError, match="not found"):
        rm.load(_FS, tmp_path / "nope.toml")


def test_load_bad_toml(tmp_path: Path) -> None:
    """Malformed TOML raises `RoadmapError`."""
    path = _write(tmp_path, "not = ")
    with pytest.raises(RoadmapError, match="invalid TOML"):
        rm.load(_FS, path)


def test_load_no_meta(tmp_path: Path) -> None:
    """A roadmap without `[meta]` is rejected."""
    path = _write(tmp_path, '[[steps]]\nnumber = 1\ntitle = "x"\n')
    with pytest.raises(RoadmapError, match="missing \\[meta\\]"):
        rm.load(_FS, path)


def test_load_no_steps(tmp_path: Path) -> None:
    """A roadmap without `[[steps]]` is rejected."""
    path = _write(tmp_path, "[meta]\nversion = 1\n")
    with pytest.raises(RoadmapError, match="missing \\[\\[steps\\]\\]"):
        rm.load(_FS, path)


def test_load_bad_version(tmp_path: Path) -> None:
    """A version below 1 is rejected."""
    body = _VALID.replace("version = 1", "version = 0")
    path = _write(tmp_path, body)
    with pytest.raises(RoadmapError, match="version must be >= 1"):
        rm.load(_FS, path)


def test_load_interface_missing_name(tmp_path: Path) -> None:
    """An interface without a `name` is rejected."""
    body = _VALID.replace('name = "Task"\nkind = "class"', 'kind = "class"', 1)
    path = _write(tmp_path, body)
    with pytest.raises(RoadmapError, match="missing `name`"):
        rm.load(_FS, path)


def test_load_step_missing_title(tmp_path: Path) -> None:
    """A step without a `title` is rejected."""
    body = _VALID.replace('title = "Models"', "")
    path = _write(tmp_path, body)
    with pytest.raises(RoadmapError, match="missing `title`"):
        rm.load(_FS, path)


def test_load_step_bad_number(tmp_path: Path) -> None:
    """A non-positive step number is rejected."""
    body = _VALID.replace("number = 1", "number = 0")
    path = _write(tmp_path, body)
    with pytest.raises(RoadmapError, match="invalid number"):
        rm.load(_FS, path)


def _roadmap(
    steps: list[RoadmapStep],
    interfaces: tuple[RoadmapInterface, ...] = (),
) -> Roadmap:
    """Build an in-memory roadmap for validation tests."""
    return Roadmap(
        meta=RoadmapMeta(version=1, note=""),
        interfaces=interfaces,
        steps=tuple(steps),
    )


def _step(number: int, **overrides) -> RoadmapStep:
    """Build a step with sensible defaults for the given number."""
    data = dict(
        number=number,
        title=f"step {number}",
        goal="",
        files=(),
        interfaces=(),
        acceptance=(),
        depends_on=(),
    )
    data.update(overrides)
    return RoadmapStep(**data)


def test_validate_ok() -> None:
    """A trivial roadmap has no problems."""
    assert rm.validate(_roadmap([_step(1)])) == []


def test_validate_duplicate_number() -> None:
    """Duplicate step numbers are reported."""
    problems = rm.validate(_roadmap([_step(1), _step(1)]))
    assert any("not unique" in p for p in problems)


def test_validate_gap_in_numbers() -> None:
    """A gap in step numbers is reported."""
    problems = rm.validate(_roadmap([_step(1), _step(3)]))
    assert any("must be 1.." in p for p in problems)


def test_validate_unknown_interface() -> None:
    """An interface reference not declared elsewhere is reported."""
    problems = rm.validate(_roadmap([_step(1, interfaces=("X",))]))
    assert any("unknown interface" in p for p in problems)


def test_validate_duplicate_interface_name() -> None:
    """Duplicate interface names are reported."""
    iface = RoadmapInterface(
        name="X",
        kind="class",
        module="a.py",
        signature="class X",
        doc="",
    )
    problems = rm.validate(_roadmap([_step(1)], interfaces=(iface, iface)))
    assert any("interface names are not unique" in p for p in problems)


def test_validate_depends_on_forward() -> None:
    """A dependency on a later step is reported."""
    problems = rm.validate(_roadmap([_step(1, depends_on=(2,)), _step(2)]))
    assert any("not an earlier step" in p for p in problems)


def test_validate_depends_on_missing() -> None:
    """A dependency on a nonexistent step is reported."""
    problems = rm.validate(_roadmap([_step(2, depends_on=(1,)), _step(3)]))
    assert any("does not exist" in p for p in problems)


def test_validate_interface_module_unsafe() -> None:
    """An absolute module path is reported."""
    iface = RoadmapInterface(
        name="X",
        kind="class",
        module="/abs.py",
        signature="class X",
        doc="",
    )
    problems = rm.validate(_roadmap([_step(1)], interfaces=(iface,)))
    assert any("absolute path" in p for p in problems)


def test_find_step() -> None:
    """`find_step` returns the step with the given number."""
    roadmap = _roadmap([_step(1), _step(2)])
    assert rm.find_step(roadmap, 2).number == 2
    assert rm.find_step(roadmap, 3) is None


def test_sha256_matches_hashlib(tmp_path: Path) -> None:
    """`sha256` matches `hashlib` on the same bytes."""
    p = tmp_path / "x"
    p.write_bytes(b"hello")
    assert rm.sha256(_FS, p) == hashlib.sha256(b"hello").hexdigest()


def test_render_summary() -> None:
    """The summary marks done, current, and pending steps."""
    roadmap = _roadmap([_step(1), _step(2), _step(3)])
    state = State(
        harness_version="",
        current_phase="",
        phase_kind="development",
        current_step=0,
        last_commit="",
        last_commit_date="",
        roadmap_version=1,
        roadmap_step=1,
        roadmap_frozen=True,
        rollback_count=0,
        last_opened="",
        last_closed="",
    )
    text = rm.render_summary(roadmap, state)
    assert "*done*" in text
    assert "*current*" in text
    assert "*pending*" in text


def test_render_current() -> None:
    """`render_current` lists files, interfaces, and acceptance."""
    step = _step(
        1,
        title="Models",
        goal="Write code",
        files=("a.py",),
        interfaces=("X",),
        acceptance=("works",),
    )
    text = rm.render_current(step)
    assert "## Current step 1: Models" in text
    assert "a.py" in text
    assert "works" in text


def test_render_interfaces_empty() -> None:
    """An empty interface list renders a placeholder."""
    assert "(none declared)" in rm.render_interfaces(_roadmap([_step(1)]))


def test_render_interfaces_full() -> None:
    """Interfaces render with signature and module."""
    iface = RoadmapInterface(
        name="X",
        kind="class",
        module="a.py",
        signature="class X",
        doc="a thing",
    )
    text = rm.render_interfaces(_roadmap([_step(1)], interfaces=(iface,)))
    assert "class X" in text
    assert "a.py" in text
    assert "a thing" in text
