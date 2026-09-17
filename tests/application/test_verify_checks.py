"""Tests for `application.verify_checks`."""

from __future__ import annotations

from dwch.application.verify_checks import (
    check_architecture_lock,
    check_compile,
    check_roadmap_files,
    check_roadmap_interfaces,
    check_roadmap_step,
    compute_auto_deviations,
    run_configured,
)
from dwch.domain.models import (
    FileSpec,
    ProcessResult,
    Roadmap,
    RoadmapInterface,
    RoadmapMeta,
    RoadmapStep,
    State,
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


def test_check_compile_no_python(deps) -> None:
    """A step with no `.py` files passes with a placeholder."""
    result = check_compile([FileSpec(path="README.md", content="")], deps)
    assert result.exit_code == 0
    assert "no python files" in result.stdout


def test_check_compile_ok(deps) -> None:
    """A valid Python file passes."""
    (deps.project_root / "a.py").write_text("x = 1\n", encoding="utf-8")
    result = check_compile([FileSpec(path="a.py", content="")], deps)
    assert result.exit_code == 0


def test_check_compile_syntax_error(deps) -> None:
    """A file with a syntax error fails and names the file."""
    (deps.project_root / "a.py").write_text("def (:\n", encoding="utf-8")
    result = check_compile([FileSpec(path="a.py", content="")], deps)
    assert result.exit_code == 1
    assert "a.py" in result.stdout


def test_check_compile_missing_file(deps) -> None:
    """A step that names a missing file fails."""
    result = check_compile([FileSpec(path="nope.py", content="")], deps)
    assert result.exit_code == 1


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


def test_check_roadmap_files_match() -> None:
    """Matching file sets pass."""
    step = RoadmapStep(
        number=1,
        title="x",
        goal="",
        files=("a.py",),
        interfaces=(),
        acceptance=(),
        depends_on=(),
    )
    result = check_roadmap_files([FileSpec(path="a.py", content="")], step)
    assert result.exit_code == 0


def test_check_roadmap_files_extra() -> None:
    """An extra file fails and appears in the message."""
    step = RoadmapStep(
        number=1,
        title="x",
        goal="",
        files=("a.py",),
        interfaces=(),
        acceptance=(),
        depends_on=(),
    )
    specs = [
        FileSpec(path="a.py", content=""),
        FileSpec(path="b.py", content=""),
    ]
    result = check_roadmap_files(specs, step)
    assert result.exit_code == 1
    assert "b.py" in result.stdout


def test_check_roadmap_files_missing() -> None:
    """A missing file fails and appears in the message."""
    step = RoadmapStep(
        number=1,
        title="x",
        goal="",
        files=("a.py", "b.py"),
        interfaces=(),
        acceptance=(),
        depends_on=(),
    )
    result = check_roadmap_files([FileSpec(path="a.py", content="")], step)
    assert result.exit_code == 1
    assert "missing" in result.stdout


def test_check_roadmap_files_ignores_deviations() -> None:
    """Deviation files are not counted as extra."""
    step = RoadmapStep(
        number=1,
        title="x",
        goal="",
        files=("a.py",),
        interfaces=(),
        acceptance=(),
        depends_on=(),
    )
    specs = [
        FileSpec(path="a.py", content=""),
        FileSpec(path=".harness/deviations/step-01.toml", content=""),
    ]
    assert check_roadmap_files(specs, step).exit_code == 0


def test_check_roadmap_interfaces_present(deps) -> None:
    """A declared interface found in the module passes."""
    (deps.project_root / "m.py").write_text("class X: pass\n", encoding="utf-8")
    iface = RoadmapInterface(
        name="X", kind="class", module="m.py", signature="class X", doc=""
    )
    step = RoadmapStep(
        number=1,
        title="",
        goal="",
        files=("m.py",),
        interfaces=("X",),
        acceptance=(),
        depends_on=(),
    )
    roadmap = Roadmap(
        meta=RoadmapMeta(version=1, note=""),
        interfaces=(iface,),
        steps=(step,),
    )
    result = check_roadmap_interfaces(
        deps.fs,
        deps.project_root,
        [FileSpec(path="m.py", content="")],
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
    step = RoadmapStep(
        number=1,
        title="",
        goal="",
        files=("m.py",),
        interfaces=("X",),
        acceptance=(),
        depends_on=(),
    )
    roadmap = Roadmap(
        meta=RoadmapMeta(version=1, note=""),
        interfaces=(iface,),
        steps=(step,),
    )
    result = check_roadmap_interfaces(
        deps.fs,
        deps.project_root,
        [FileSpec(path="m.py", content="")],
        step,
        roadmap,
    )
    assert result.exit_code == 1


def test_check_roadmap_interfaces_none() -> None:
    """A step without interfaces passes with a placeholder."""
    step = RoadmapStep(
        number=1,
        title="",
        goal="",
        files=(),
        interfaces=(),
        acceptance=(),
        depends_on=(),
    )
    roadmap = Roadmap(
        meta=RoadmapMeta(version=1, note=""),
        interfaces=(),
        steps=(step,),
    )
    # No filesystem access is needed when the step declares no
    # interfaces; passing placeholders proves that.
    result = check_roadmap_interfaces(None, None, [], step, roadmap)
    assert result.exit_code == 0


def test_check_architecture_lock_none() -> None:
    """No lock means no check."""
    assert check_architecture_lock(None, None, None, None, [], required=False) is None


def test_compute_auto_deviations_extra_and_missing() -> None:
    """Extra and missing files each produce an auto deviation."""
    step = RoadmapStep(
        number=1,
        title="",
        goal="",
        files=("a.py", "b.py"),
        interfaces=(),
        acceptance=(),
        depends_on=(),
    )
    specs = [
        FileSpec(path="a.py", content=""),
        FileSpec(path="c.py", content=""),
    ]
    devs = compute_auto_deviations(specs, step)
    types = {d.type.value for d in devs}
    assert "extra-file" in types
    assert "missing-file" in types
    assert all(d.auto for d in devs)


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
