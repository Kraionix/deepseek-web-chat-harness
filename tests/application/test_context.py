"""Tests for `application.context`."""

from __future__ import annotations

from pathlib import Path

from dwch.application import plan as plan_mod
from dwch.application.context import build_bootstrap
from dwch.application.state import load_state, save_state, with_updates

_PLAN_TOML = """\
[meta]
version = 1
note = "x"

[[tasks]]
id = "models"
title = "Models"
goal = "Write Task."
files = ["src/todo.py"]
interfaces = []
acceptance = []
depends_on = []

[[tasks]]
id = "storage"
title = "Storage"
goal = "Write load/save."
files = ["src/storage.py"]
interfaces = []
acceptance = []
depends_on = ["models"]
"""


def _make_plan(root: Path, deps):
    """Write and load a two-task plan."""
    path = root / ".harness" / "plan.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_PLAN_TOML, encoding="utf-8")
    return plan_mod.load(deps.fs, path)


def _set_state(root: Path, deps, **kwargs):
    """Load state, apply updates, save it, and return the result."""
    state = load_state(deps.fs, root)
    fresh = with_updates(state, **kwargs)
    save_state(deps.fs, root, fresh)
    return fresh


def test_bootstrap_has_all_six_layers(harness_root: Path, deps) -> None:
    """A normal bootstrap contains L0-L6 section markers."""
    plan = _make_plan(harness_root, deps)
    state = _set_state(
        harness_root,
        deps,
        phase_name="p1",
        phase_kind="development",
        phase_status="open",
    )
    result = build_bootstrap(deps, _config(deps, harness_root), state, plan)
    for marker in (
        "section: meta",
        "section: contract",
        "section: tools",
        "section: session",
        "section: task",
    ):
        assert marker in result.text


def test_bootstrap_l1_always_present(harness_root: Path, deps) -> None:
    """The contract layer is always present."""
    plan = _make_plan(harness_root, deps)
    state = load_state(deps.fs, harness_root)
    result = build_bootstrap(deps, _config(deps, harness_root), state, plan)
    assert "section: contract" in result.text
    assert "Harness contract" in result.text


def test_bootstrap_l6_truncates_first(harness_root: Path, deps) -> None:
    """Notes are dropped before essential context."""
    plan = _make_plan(harness_root, deps)
    state = _set_state(
        harness_root,
        deps,
        phase_name="p1",
        phase_kind="development",
        phase_status="open",
    )
    notes_path = harness_root / ".harness" / "notes.md"
    notes_path.write_text("notes body " * 200, encoding="utf-8")
    config = _config(deps, harness_root, max_tokens=1500)

    result = build_bootstrap(deps, config, state, plan)
    assert result.truncated
    assert "section: notes" not in result.text
    assert "section: contract" in result.text


def test_bootstrap_fix_mode_has_failure_section(harness_root: Path, deps) -> None:
    """Fix mode replaces the task layer with a failure block."""
    plan = _make_plan(harness_root, deps)
    state = _set_state(
        harness_root,
        deps,
        phase_name="p1",
        phase_kind="development",
        phase_status="open",
        failure_task_id="models",
        failure_check_name="compile",
        failure_excerpt="a.py: syntax error",
        failure_count=1,
    )
    result = build_bootstrap(deps, _config(deps, harness_root), state, plan, mode="fix")
    assert "section: failure" in result.text
    assert "Task: models (FAILED, attempt 1)" in result.text
    assert "a.py: syntax error" in result.text


def test_bootstrap_warning_at_three_failures(harness_root: Path, deps) -> None:
    """L0 gains a warning line at three consecutive failures."""
    plan = _make_plan(harness_root, deps)
    state = _set_state(
        harness_root,
        deps,
        phase_name="p1",
        phase_kind="development",
        phase_status="open",
        failure_task_id="models",
        failure_count=3,
    )
    result = build_bootstrap(deps, _config(deps, harness_root), state, plan, mode="fix")
    assert "warning:" in result.text
    assert "models" in result.text


def _config(deps, root: Path, max_tokens: int = 50000):
    """Load config and override `max_tokens`."""
    from dwch.application.config import load_config

    cfg = load_config(deps.fs, root)
    if max_tokens != 50000:
        new_bootstrap = dict(cfg.bootstrap)
        new_bootstrap["max_tokens"] = max_tokens
        from dataclasses import replace

        cfg = replace(cfg, bootstrap=new_bootstrap)
    return cfg
