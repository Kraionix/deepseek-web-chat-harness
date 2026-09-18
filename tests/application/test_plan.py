"""Tests for `application.plan`."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from dwch.adapters.filesystem import LocalFilesystem
from dwch.application import plan as pm
from dwch.domain.models import (
    Interface,
    Plan,
    PlanMeta,
    State,
    Task,
)
from dwch.shared.errors import PlanError

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

[[tasks]]
id = "models"
title = "Models"
goal = "Write Task."
files = ["src/todo.py"]
interfaces = ["Task"]
acceptance = []
depends_on = []
"""


def _write(root: Path, body: str) -> Path:
    """Write a plan file under `root` and return its path."""
    path = root / ".harness" / "plan.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_load_valid(tmp_path: Path) -> None:
    """A well-formed plan loads with all sections populated."""
    path = _write(tmp_path, _VALID)
    plan = pm.load(_FS, path)
    assert plan.meta.version == 1
    assert plan.meta.note == "demo"
    assert len(plan.tasks) == 1
    assert plan.tasks[0].id == "models"


def test_load_missing(tmp_path: Path) -> None:
    """A missing plan raises `PlanError`."""
    with pytest.raises(PlanError, match="not found"):
        pm.load(_FS, tmp_path / "nope.toml")


def test_load_bad_toml(tmp_path: Path) -> None:
    """Malformed TOML raises `PlanError`."""
    path = _write(tmp_path, "not = ")
    with pytest.raises(PlanError, match="invalid TOML"):
        pm.load(_FS, path)


def test_load_no_meta(tmp_path: Path) -> None:
    """A plan without `[meta]` is rejected."""
    path = _write(tmp_path, '[[tasks]]\nid = "x"\ntitle = "x"\n')
    with pytest.raises(PlanError, match=r"missing \[meta\]"):
        pm.load(_FS, path)


def test_load_no_tasks(tmp_path: Path) -> None:
    """A plan without `[[tasks]]` is rejected."""
    path = _write(tmp_path, "[meta]\nversion = 1\n")
    with pytest.raises(PlanError, match=r"missing \[\[tasks\]\]"):
        pm.load(_FS, path)


def test_load_bad_version(tmp_path: Path) -> None:
    """A version below 1 is rejected."""
    body = _VALID.replace("version = 1", "version = 0")
    path = _write(tmp_path, body)
    with pytest.raises(PlanError, match="version must be >= 1"):
        pm.load(_FS, path)


def test_load_interface_missing_name(tmp_path: Path) -> None:
    """An interface without a `name` is rejected."""
    body = _VALID.replace('name = "Task"\nkind = "class"', 'kind = "class"', 1)
    path = _write(tmp_path, body)
    with pytest.raises(PlanError, match="missing `name`"):
        pm.load(_FS, path)


def test_load_task_missing_id(tmp_path: Path) -> None:
    """A task without an `id` is rejected."""
    body = _VALID.replace('id = "models"\n', "")
    path = _write(tmp_path, body)
    with pytest.raises(PlanError, match="missing `id`"):
        pm.load(_FS, path)


def test_load_task_missing_title(tmp_path: Path) -> None:
    """A task without a `title` is rejected."""
    body = _VALID.replace('title = "Models"', "")
    path = _write(tmp_path, body)
    with pytest.raises(PlanError, match="missing `title`"):
        pm.load(_FS, path)


def test_load_tasks_string_raises(tmp_path: Path) -> None:
    """A string `tasks` field is a `PlanError`, not an `AttributeError`."""
    body = 'tasks = "abc"\n\n[meta]\nversion = 1\n'
    path = _write(tmp_path, body)
    with pytest.raises(PlanError, match="expected a list of tables"):
        pm.load(_FS, path)


def test_load_task_files_string_raises(tmp_path: Path) -> None:
    """A string `files` field on a task is a `PlanError`."""
    body = _VALID.replace('files = ["src/todo.py"]', 'files = "src/todo.py"')
    path = _write(tmp_path, body)
    with pytest.raises(PlanError, match="expected a list of strings"):
        pm.load(_FS, path)


def test_load_task_depends_on_string_raises(tmp_path: Path) -> None:
    """A string `depends_on` field is a `PlanError`."""
    body = _VALID.replace("depends_on = []", 'depends_on = "1"')
    path = _write(tmp_path, body)
    with pytest.raises(PlanError, match="depends_on"):
        pm.load(_FS, path)


def test_load_task_removes_and_moves(tmp_path: Path) -> None:
    """`removes` and `moves` parse into the model."""
    body = _VALID.replace(
        'files = ["src/todo.py"]',
        'files = ["src/todo.py"]\n'
        'removes = ["src/legacy.py"]\n'
        "moves = [\n"
        '  { from = "src/models.py", to = "src/models/__init__.py" },\n'
        "]",
    )
    path = _write(tmp_path, body)
    plan = pm.load(_FS, path)
    assert plan.tasks[0].removes == ("src/legacy.py",)
    assert plan.tasks[0].moves == (("src/models.py", "src/models/__init__.py"),)


def test_load_task_missing_removes_moves_default_empty(tmp_path: Path) -> None:
    """An older plan without the keys still parses."""
    path = _write(tmp_path, _VALID)
    plan = pm.load(_FS, path)
    assert plan.tasks[0].removes == ()
    assert plan.tasks[0].moves == ()


def test_load_task_moves_item_missing_field_raises(tmp_path: Path) -> None:
    """A `moves` item without `to` is a `PlanError`."""
    body = _VALID.replace(
        'files = ["src/todo.py"]',
        'files = ["src/todo.py"]\nmoves = [{ from = "src/a.py" }]',
    )
    path = _write(tmp_path, body)
    with pytest.raises(PlanError, match="must both be strings"):
        pm.load(_FS, path)


def _plan(
    tasks: list[Task],
    interfaces: tuple[Interface, ...] = (),
) -> Plan:
    """Build an in-memory plan for validation tests."""
    return Plan(
        meta=PlanMeta(version=1, note=""),
        interfaces=interfaces,
        tasks=tuple(tasks),
    )


def _task(task_id: str, **overrides) -> Task:
    """Build a task with sensible defaults for the given id."""
    data = dict(
        id=task_id,
        title=f"task {task_id}",
        goal="",
        files=(),
        interfaces=(),
        acceptance=(),
        depends_on=(),
    )
    data.update(overrides)
    return Task(**data)


def test_validate_ok() -> None:
    """A trivial plan has no problems."""
    assert pm.validate(_plan([_task("a")])) == []


def test_validate_bad_id() -> None:
    """A task id not matching the slug regex is reported."""
    problems = pm.validate(_plan([_task("BadId")]))
    assert any("does not match" in p for p in problems)


def test_validate_long_id() -> None:
    """A task id longer than 40 chars is reported."""
    problems = pm.validate(_plan([_task("a" * 41)]))
    assert any("longer than" in p for p in problems)


def test_validate_duplicate_id() -> None:
    """Duplicate task ids are reported."""
    problems = pm.validate(_plan([_task("a"), _task("a")]))
    assert any("not unique" in p for p in problems)


def test_validate_unknown_dep() -> None:
    """A dependency on an unknown id is reported."""
    problems = pm.validate(_plan([_task("a", depends_on=("b",))]))
    assert any("unknown id" in p for p in problems)


def test_validate_self_dep() -> None:
    """A dependency on itself is reported."""
    problems = pm.validate(_plan([_task("a", depends_on=("a",))]))
    assert any("depends_on itself" in p for p in problems)


def test_validate_cycle() -> None:
    """A cycle in the dependency graph is reported."""
    plan = _plan(
        [
            _task("a", depends_on=("b",)),
            _task("b", depends_on=("a",)),
        ]
    )
    problems = pm.validate(plan)
    assert any("cycle" in p for p in problems)


def test_validate_unused_interface() -> None:
    """An interface not used by any task is reported."""
    iface = Interface(
        name="X", kind="class", module="m.py", signature="class X", doc=""
    )
    problems = pm.validate(_plan([_task("a")], interfaces=(iface,)))
    assert any("not used" in p for p in problems)


def test_validate_interface_module_unsafe() -> None:
    """An absolute module path is reported."""
    iface = Interface(
        name="X", kind="class", module="/abs.py", signature="class X", doc=""
    )
    problems = pm.validate(_plan([_task("a", interfaces=("X",))], interfaces=(iface,)))
    assert any("absolute path" in p for p in problems)


def test_validate_removes_intersects_files() -> None:
    """`removes` overlapping `files` is reported."""
    step = _task("a", files=("a.py",), removes=("a.py",))
    problems = pm.validate(_plan([step]))
    assert any("removes intersects files" in p for p in problems)


def test_validate_moves_from_intersects_files() -> None:
    """`moves.from` overlapping `files` is reported."""
    step = _task("a", files=("a.py",), moves=(("a.py", "b.py"),))
    problems = pm.validate(_plan([step]))
    assert any("moves.from intersects files" in p for p in problems)


def test_validate_moves_to_intersects_files() -> None:
    """`moves.to` overlapping `files` is reported."""
    step = _task("a", files=("b.py",), moves=(("a.py", "b.py"),))
    problems = pm.validate(_plan([step]))
    assert any("moves.to intersects files" in p for p in problems)


def test_validate_moves_from_intersects_removes() -> None:
    """`moves.from` overlapping `removes` is reported."""
    step = _task("a", removes=("a.py",), moves=(("a.py", "b.py"),))
    problems = pm.validate(_plan([step]))
    assert any("moves.from intersects removes" in p for p in problems)


def test_validate_moves_duplicate_from() -> None:
    """Duplicate `moves.from` values are reported."""
    step = _task("a", moves=(("a.py", "b.py"), ("a.py", "c.py")))
    problems = pm.validate(_plan([step]))
    assert any("moves.from values are not unique" in p for p in problems)


def test_validate_moves_duplicate_to() -> None:
    """Duplicate `moves.to` values are reported."""
    step = _task("a", moves=(("a.py", "c.py"), ("b.py", "c.py")))
    problems = pm.validate(_plan([step]))
    assert any("moves.to values are not unique" in p for p in problems)


def test_validate_moves_from_equals_to() -> None:
    """A move with `from == to` is reported."""
    step = _task("a", moves=(("a.py", "a.py"),))
    problems = pm.validate(_plan([step]))
    assert any("identical from and to" in p for p in problems)


def test_validate_moves_chain() -> None:
    """A chained move (`a→b`, `b→c`) is reported."""
    step = _task("a", moves=(("a.py", "b.py"), ("b.py", "c.py")))
    problems = pm.validate(_plan([step]))
    assert any("chained moves" in p for p in problems)


def test_validate_unsafe_path_in_removes() -> None:
    """An absolute path in `removes` is reported."""
    step = _task("a", removes=("/abs.py",))
    problems = pm.validate(_plan([step]))
    assert any("removes" in p and "absolute path" in p for p in problems)


def test_validate_safe_path_with_root(tmp_path: Path) -> None:
    """With a project root, reserved names in `removes` are reported."""
    step = _task("a", removes=("src/CON",))
    problems = pm.validate(_plan([step]), tmp_path)
    assert any("removes" in p for p in problems)


def test_find_task() -> None:
    """`find_task` returns the task with the given id."""
    plan = _plan([_task("a"), _task("b")])
    assert pm.find_task(plan, "b").id == "b"
    assert pm.find_task(plan, "c") is None


def test_position_of() -> None:
    """`position_of` returns the index, or -1."""
    plan = _plan([_task("a"), _task("b")])
    assert pm.position_of(plan, "a") == 0
    assert pm.position_of(plan, "b") == 1
    assert pm.position_of(plan, "z") == -1


def test_sha256_matches_hashlib(tmp_path: Path) -> None:
    """`sha256` matches `hashlib` on the same bytes."""
    p = tmp_path / "x"
    p.write_bytes(b"hello")
    assert pm.sha256(_FS, p) == hashlib.sha256(b"hello").hexdigest()


def test_render_summary() -> None:
    """The summary marks done, current, and pending tasks."""
    plan = _plan([_task("a"), _task("b"), _task("c")])
    state = State(
        harness_version="",
        phase_name="",
        phase_kind="development",
        phase_status="open",
        phase_opened_at="",
        phase_closed_at="",
        plan_version=1,
        plan_sha256="",
        plan_position=1,
        plan_frozen=True,
        verify_ok=False,
        verify_task_id="",
        verify_at="",
        failure_task_id="",
        failure_check_name="",
        failure_excerpt="",
        failure_count=0,
        rollback_count=0,
        last_commit="",
        last_commit_date="",
    )
    text = pm.render_summary(plan, state)
    assert "*done*" in text
    assert "*current*" in text
    assert "*pending*" in text


def test_render_task_includes_removes_and_moves() -> None:
    """`render_task` shows removes and moves when present."""
    step = _task(
        "a",
        title="Move",
        goal="go",
        files=("a.py",),
        removes=("old.py",),
        moves=(("x.py", "y.py"),),
    )
    text = pm.render_task(step)
    assert "Removes:" in text
    assert "old.py" in text
    assert "Moves:" in text
    assert "x.py → y.py" in text


def test_render_interfaces_empty() -> None:
    """An empty interface list renders a placeholder."""
    assert "(none declared)" in pm.render_interfaces(_plan([_task("a")]))


def test_render_interfaces_full() -> None:
    """Interfaces render with signature and module."""
    iface = Interface(
        name="X",
        kind="class",
        module="a.py",
        signature="class X",
        doc="a thing",
    )
    text = pm.render_interfaces(_plan([_task("a")], interfaces=(iface,)))
    assert "class X" in text
    assert "a.py" in text
    assert "a thing" in text
