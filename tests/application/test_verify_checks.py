"""Tests for `application.verify_checks`."""

from __future__ import annotations

from dwch.application.verify_checks import (
    check_architecture_lock,
    check_compile,
    check_roadmap_changes,
    check_roadmap_interfaces,
    check_roadmap_step,
    compute_auto_deviations,
    run_configured,
)
from dwch.domain.models import (
    DeleteOp,
    MoveOp,
    ProcessResult,
    Roadmap,
    RoadmapInterface,
    RoadmapMeta,
    RoadmapStep,
    State,
    WriteOp,
)
from tests.fakes import InMemoryProcess


def _state(roadmap_step: int = 0) -> State:
    """A minimal state for roadmap-step tests."""
    return State(
        harness_version="",
        current_phase="p",
        phase_kind="development",
        current_step=0,
        last_commit="",
        last_commit_date="",
        roadmap_version=1,
        roadmap_step=roadmap_step,
        roadmap_frozen=True,
        rollback_count=0,
        last_opened="",
        last_closed="",
    )


def _roadmap(numbers: list[int]) -> Roadmap:
    """Build a roadmap with the given step numbers."""
    steps = tuple(
        RoadmapStep(
            number=n,
            title=f"s{n}",
            goal="",
            files=(),
            interfaces=(),
            acceptance=(),
            depends_on=(),
        )
        for n in numbers
    )
    return Roadmap(meta=RoadmapMeta(version=1, note=""), interfaces=(), steps=steps)


def _step(**overrides) -> RoadmapStep:
    """A step with sensible defaults; overrides any field."""
    data = dict(
        number=1,
        title="x",
        goal="",
        files=(),
        interfaces=(),
        acceptance=(),
        depends_on=(),
    )
    data.update(overrides)
    return RoadmapStep(**data)


# ---------------------------------------------------------------------------
# check_compile
# ---------------------------------------------------------------------------


def test_check_compile_no_python(deps) -> None:
    """A step with no `.py` files passes with a placeholder."""
    result = check_compile([WriteOp(path="README.md", content="")], deps)
    assert result.exit_code == 0
    assert "no python files" in result.stdout


def test_check_compile_ok(deps) -> None:
    """A valid Python file passes."""
    (deps.project_root / "a.py").write_text("x = 1\n", encoding="utf-8")
    result = check_compile([WriteOp(path="a.py", content="")], deps)
    assert result.exit_code == 0


def test_check_compile_syntax_error(deps) -> None:
    """A file with a syntax error fails and names the file."""
    (deps.project_root / "a.py").write_text("def (:\n", encoding="utf-8")
    result = check_compile([WriteOp(path="a.py", content="")], deps)
    assert result.exit_code == 1
    assert "a.py" in result.stdout


def test_check_compile_missing_file(deps) -> None:
    """A step that names a missing file fails."""
    result = check_compile([WriteOp(path="nope.py", content="")], deps)
    assert result.exit_code == 1


def test_check_compile_skips_delete(deps) -> None:
    """A DeleteOp path is not compiled: the file no longer exists."""
    result = check_compile([DeleteOp(path="gone.py")], deps)
    assert result.exit_code == 0
    assert "no python files" in result.stdout


def test_check_compile_move_uses_dst(deps) -> None:
    """A MoveOp is compiled at its destination."""
    (deps.project_root / "new.py").write_text("x = 1\n", encoding="utf-8")
    result = check_compile([MoveOp(src="old.py", dst="new.py")], deps)
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# check_roadmap_step
# ---------------------------------------------------------------------------


def test_check_roadmap_step_match() -> None:
    """A matching step number passes."""
    result = check_roadmap_step(2, _state(roadmap_step=1), _roadmap([1, 2, 3]))
    assert result.exit_code == 0


def test_check_roadmap_step_mismatch() -> None:
    """A non-matching step number fails."""
    result = check_roadmap_step(3, _state(roadmap_step=1), _roadmap([1, 2, 3]))
    assert result.exit_code == 1


def test_check_roadmap_step_past_end() -> None:
    """A step past the end of the roadmap fails with an explanation."""
    result = check_roadmap_step(4, _state(roadmap_step=3), _roadmap([1, 2, 3]))
    assert result.exit_code == 1
    assert "does not exist" in result.stdout


# ---------------------------------------------------------------------------
# check_roadmap_changes — written
# ---------------------------------------------------------------------------


def test_check_roadmap_changes_written_match() -> None:
    """A matching write set passes."""
    step = _step(files=("a.py",))
    result = check_roadmap_changes([WriteOp(path="a.py", content="")], step)
    assert result.exit_code == 0


def test_check_roadmap_changes_extra_file() -> None:
    """An extra write fails and appears in the message."""
    step = _step(files=("a.py",))
    ops = [WriteOp(path="a.py", content=""), WriteOp(path="b.py", content="")]
    result = check_roadmap_changes(ops, step)
    assert result.exit_code == 1
    assert "b.py" in result.stdout
    assert "extra written" in result.stdout


def test_check_roadmap_changes_missing_file() -> None:
    """A missing file fails and appears in the message."""
    step = _step(files=("a.py", "b.py"))
    result = check_roadmap_changes([WriteOp(path="a.py", content="")], step)
    assert result.exit_code == 1
    assert "missing written" in result.stdout


def test_check_roadmap_changes_ignores_deviations() -> None:
    """Deviation files are not counted as extra."""
    step = _step(files=("a.py",))
    ops = [
        WriteOp(path="a.py", content=""),
        WriteOp(path=".harness/deviations/step-01.toml", content=""),
    ]
    assert check_roadmap_changes(ops, step).exit_code == 0


# ---------------------------------------------------------------------------
# check_roadmap_changes — deleted
# ---------------------------------------------------------------------------


def test_check_roadmap_changes_delete_match() -> None:
    """A delete set matching `removes` passes."""
    step = _step(removes=("old.py",))
    result = check_roadmap_changes([DeleteOp(path="old.py")], step)
    assert result.exit_code == 0


def test_check_roadmap_changes_extra_removal() -> None:
    """A delete not listed in `removes` fails."""
    step = _step()
    result = check_roadmap_changes([DeleteOp(path="surprise.py")], step)
    assert result.exit_code == 1
    assert "extra deleted" in result.stdout


def test_check_roadmap_changes_missing_removal() -> None:
    """A file in `removes` that was not deleted fails."""
    step = _step(removes=("old.py",))
    result = check_roadmap_changes([], step)
    assert result.exit_code == 1
    assert "missing deleted" in result.stdout


# ---------------------------------------------------------------------------
# check_roadmap_changes — moves
# ---------------------------------------------------------------------------


def test_check_roadmap_changes_move_match() -> None:
    """A move matching `moves` passes."""
    step = _step(moves=(("a.py", "b.py"),))
    result = check_roadmap_changes([MoveOp(src="a.py", dst="b.py")], step)
    assert result.exit_code == 0


def test_check_roadmap_changes_extra_move() -> None:
    """A move not in `moves` fails."""
    step = _step()
    result = check_roadmap_changes([MoveOp(src="a.py", dst="b.py")], step)
    assert result.exit_code == 1
    assert "extra moves" in result.stdout


def test_check_roadmap_changes_missing_move() -> None:
    """A pair in `moves` with no corresponding op fails."""
    step = _step(moves=(("a.py", "b.py"),))
    result = check_roadmap_changes([], step)
    assert result.exit_code == 1
    assert "missing moves" in result.stdout


# ---------------------------------------------------------------------------
# check_roadmap_interfaces
# ---------------------------------------------------------------------------


def test_check_roadmap_interfaces_present(deps) -> None:
    """A declared interface found in the module passes."""
    (deps.project_root / "m.py").write_text("class X: pass\n", encoding="utf-8")
    iface = RoadmapInterface(
        name="X", kind="class", module="m.py", signature="class X", doc=""
    )
    step = _step(files=("m.py",), interfaces=("X",))
    roadmap = Roadmap(
        meta=RoadmapMeta(version=1, note=""),
        interfaces=(iface,),
        steps=(step,),
    )
    result = check_roadmap_interfaces(
        deps.fs,
        deps.project_root,
        [WriteOp(path="m.py", content="")],
        step,
        roadmap,
    )
    assert result.exit_code == 0


def test_check_roadmap_interfaces_missing(deps) -> None:
    """A declared interface not found fails."""
    (deps.project_root / "m.py").write_text("class Y: pass\n", encoding="utf-8")
    iface = RoadmapInterface(
        name="X", kind="class", module="m.py", signature="class X", doc=""
    )
    step = _step(files=("m.py",), interfaces=("X",))
    roadmap = Roadmap(
        meta=RoadmapMeta(version=1, note=""),
        interfaces=(iface,),
        steps=(step,),
    )
    result = check_roadmap_interfaces(
        deps.fs,
        deps.project_root,
        [WriteOp(path="m.py", content="")],
        step,
        roadmap,
    )
    assert result.exit_code == 1


def test_check_roadmap_interfaces_none() -> None:
    """A step without interfaces passes with a placeholder."""
    step = _step()
    roadmap = Roadmap(
        meta=RoadmapMeta(version=1, note=""),
        interfaces=(),
        steps=(step,),
    )
    result = check_roadmap_interfaces(None, None, [], step, roadmap)
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# check_architecture_lock
# ---------------------------------------------------------------------------


def test_check_architecture_lock_none() -> None:
    """No lock means no check."""
    assert check_architecture_lock(None, None, None, None, [], required=False) is None


# ---------------------------------------------------------------------------
# compute_auto_deviations
# ---------------------------------------------------------------------------


def test_compute_auto_deviations_extra_and_missing_files() -> None:
    """Extra and missing written files each produce an auto deviation."""
    step = _step(files=("a.py", "b.py"))
    ops = [WriteOp(path="a.py", content=""), WriteOp(path="c.py", content="")]
    devs = compute_auto_deviations(ops, step)
    types = {d.type.value for d in devs}
    assert "extra-file" in types
    assert "missing-file" in types
    assert all(d.auto for d in devs)


def test_compute_auto_deviations_extra_removal() -> None:
    """A delete not in `removes` produces an `extra-removal` deviation."""
    step = _step()
    ops = [DeleteOp(path="surprise.py")]
    devs = compute_auto_deviations(ops, step)
    types = {d.type.value for d in devs}
    assert "extra-removal" in types


def test_compute_auto_deviations_missing_removal() -> None:
    """A file in `removes` that was not deleted produces a deviation."""
    step = _step(removes=("old.py",))
    devs = compute_auto_deviations([], step)
    types = {d.type.value for d in devs}
    assert "missing-removal" in types


def test_compute_auto_deviations_extra_move() -> None:
    """A move not in `moves` produces an `extra-move` deviation."""
    step = _step()
    ops = [MoveOp(src="a.py", dst="b.py")]
    devs = compute_auto_deviations(ops, step)
    types = {d.type.value for d in devs}
    assert "extra-move" in types


def test_compute_auto_deviations_missing_move() -> None:
    """A pair in `moves` with no op produces a `missing-move` deviation."""
    step = _step(moves=(("a.py", "b.py"),))
    devs = compute_auto_deviations([], step)
    types = {d.type.value for d in devs}
    assert "missing-move" in types


def test_compute_auto_deviations_none_when_matching() -> None:
    """A perfect match produces no deviations."""
    step = _step(
        files=("a.py",),
        removes=("old.py",),
        moves=(("x.py", "y.py"),),
    )
    ops = [
        WriteOp(path="a.py", content=""),
        DeleteOp(path="old.py"),
        MoveOp(src="x.py", dst="y.py"),
    ]
    assert compute_auto_deviations(ops, step) == []


# ---------------------------------------------------------------------------
# run_configured
# ---------------------------------------------------------------------------


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
