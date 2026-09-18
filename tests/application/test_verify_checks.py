"""Tests for `application.verify_checks`."""

from __future__ import annotations

from dwch.application.verify_checks import (
    check_compile,
    check_plan_structure,
    check_task_changes,
    check_task_interfaces,
    run_configured,
)
from dwch.domain.models import (
    DeleteOp,
    Interface,
    MoveOp,
    Plan,
    PlanMeta,
    ProcessResult,
    Task,
    WriteOp,
)
from tests.fakes import InMemoryProcess


def _task(task_id: str = "a", **overrides) -> Task:
    """A task with sensible defaults; overrides any field."""
    data = dict(
        id=task_id,
        title="x",
        goal="",
        files=(),
        interfaces=(),
        acceptance=(),
    )
    data.update(overrides)
    return Task(**data)


def _plan(tasks, interfaces=()) -> Plan:
    """A minimal plan for validation tests."""
    return Plan(
        meta=PlanMeta(version=1, note=""),
        interfaces=tuple(interfaces),
        tasks=tuple(tasks),
    )


def test_check_compile_no_python(deps) -> None:
    """A step with no `.py` files passes with a placeholder."""
    result = check_compile([WriteOp(path="README.md", content="")], deps)
    assert result.exit_code == 0
    assert "no python files" in result.stdout


def test_check_compile_ok(deps) -> None:
    """A valid Python file passes."""
    (deps.project_root / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert check_compile([WriteOp(path="a.py", content="")], deps).exit_code == 0


def test_check_compile_syntax_error(deps) -> None:
    """A file with a syntax error fails and names the file."""
    (deps.project_root / "a.py").write_text("def (:\n", encoding="utf-8")
    result = check_compile([WriteOp(path="a.py", content="")], deps)
    assert result.exit_code == 1
    assert "a.py" in result.stdout


def test_check_task_changes_match(deps) -> None:
    """A matching write set passes."""
    step = _task(files=("a.py",))
    result = check_task_changes([WriteOp(path="a.py", content="")], step)
    assert result.exit_code == 0


def test_check_task_changes_extra_file(deps) -> None:
    """An extra write fails and appears in the message."""
    step = _task(files=("a.py",))
    ops = [WriteOp(path="a.py", content=""), WriteOp(path="b.py", content="")]
    result = check_task_changes(ops, step)
    assert result.exit_code == 1
    assert "extra written" in result.stdout


def test_check_task_changes_missing_file(deps) -> None:
    """A missing file fails."""
    step = _task(files=("a.py", "b.py"))
    result = check_task_changes([WriteOp(path="a.py", content="")], step)
    assert result.exit_code == 1
    assert "missing written" in result.stdout


def test_check_task_changes_ignores_deviations(deps) -> None:
    """Deviation files are not counted as extra."""
    step = _task(files=("a.py",))
    ops = [
        WriteOp(path="a.py", content=""),
        WriteOp(path=".harness/deviations/a.toml", content=""),
    ]
    assert check_task_changes(ops, step).exit_code == 0


def test_check_task_changes_extra_removal(deps) -> None:
    """A delete not listed in `removes` fails."""
    step = _task()
    result = check_task_changes([DeleteOp(path="surprise.py")], step)
    assert result.exit_code == 1
    assert "extra deleted" in result.stdout


def test_check_task_changes_missing_removal(deps) -> None:
    """A file in `removes` that was not deleted fails."""
    step = _task(removes=("old.py",))
    result = check_task_changes([], step)
    assert result.exit_code == 1
    assert "missing deleted" in result.stdout


def test_check_task_changes_move_match(deps) -> None:
    """A move matching `moves` passes."""
    step = _task(moves=(("a.py", "b.py"),))
    result = check_task_changes([MoveOp(src="a.py", dst="b.py")], step)
    assert result.exit_code == 0


def test_check_task_changes_extra_move(deps) -> None:
    """A move not in `moves` fails."""
    step = _task()
    result = check_task_changes([MoveOp(src="a.py", dst="b.py")], step)
    assert result.exit_code == 1
    assert "extra moves" in result.stdout


def test_check_task_changes_missing_move(deps) -> None:
    """A pair in `moves` with no op fails."""
    step = _task(moves=(("a.py", "b.py"),))
    result = check_task_changes([], step)
    assert result.exit_code == 1
    assert "missing moves" in result.stdout


def test_check_task_interfaces_present(deps) -> None:
    """A declared interface found in the module passes."""
    (deps.project_root / "m.py").write_text("class X: pass\n", encoding="utf-8")
    iface = Interface(
        name="X", kind="class", module="m.py", signature="class X", doc=""
    )
    step = _task(files=("m.py",), interfaces=("X",))
    plan = _plan([step], interfaces=(iface,))
    result = check_task_interfaces(
        deps.fs,
        deps.project_root,
        [WriteOp(path="m.py", content="")],
        step,
        plan,
    )
    assert result.exit_code == 0


def test_check_task_interfaces_missing(deps) -> None:
    """A declared interface not found fails."""
    (deps.project_root / "m.py").write_text("class Y: pass\n", encoding="utf-8")
    iface = Interface(
        name="X", kind="class", module="m.py", signature="class X", doc=""
    )
    step = _task(files=("m.py",), interfaces=("X",))
    plan = _plan([step], interfaces=(iface,))
    result = check_task_interfaces(
        deps.fs,
        deps.project_root,
        [WriteOp(path="m.py", content="")],
        step,
        plan,
    )
    assert result.exit_code == 1


def test_check_task_interfaces_none() -> None:
    """A task without interfaces passes with a placeholder."""
    step = _task()
    plan = _plan([step])
    result = check_task_interfaces(None, None, [], step, plan)
    assert result.exit_code == 0


def test_check_plan_structure_ok() -> None:
    """A well-formed plan passes."""
    plan = _plan([_task("a")])
    result = check_plan_structure(plan, None)
    assert result.exit_code == 0


def test_check_plan_structure_bad() -> None:
    """A bad plan fails."""
    plan = _plan([_task("BadId")])
    result = check_plan_structure(plan, None)
    assert result.exit_code == 1


def test_run_configured_ok(deps) -> None:
    """A registered command returns its canned result."""
    proc = deps.process
    assert isinstance(proc, InMemoryProcess)
    proc.add(
        ["echo", "hi"],
        ProcessResult(exit_code=0, stdout="hi\n", stderr=""),
    )
    results = run_configured([{"name": "echo", "command": ["echo", "hi"]}], deps)
    assert results[0].exit_code == 0
    assert results[0].stdout == "hi\n"


def test_run_configured_empty_command(deps) -> None:
    """An empty command yields a failure result."""
    results = run_configured([{"name": "x", "command": []}], deps)
    assert results[0].exit_code == 1
    assert "no command" in results[0].stderr
