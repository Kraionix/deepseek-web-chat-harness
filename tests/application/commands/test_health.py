"""Tests for `application.commands.health`."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
from pathlib import Path

from dwch.application.commands.health import _check_git, cmd_health


def _preseed_tokenizer(root: Path) -> None:
    """Create a dummy tokenizer file so the check can pass."""
    data = root / ".harness" / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "deepseek_tokenizer.json").write_bytes(b"{}")


def _isolated_root(tmp_path: Path, deps):
    """Return a `Deps` whose project root is a git-free subdirectory."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    return replace(deps, project_root=workdir)


def test_health_reports_missing_tokenizer(harness_root: Path, deps, capsys) -> None:
    """A missing tokenizer file is a critical failure."""
    rc = cmd_health(Namespace(), deps)
    out = capsys.readouterr().out
    assert "tokenizer" in out
    assert "FAIL" in out
    assert rc == 1


def test_health_clean(harness_root: Path, deps, capsys) -> None:
    """A pre-seeded tokenizer passes health."""
    _preseed_tokenizer(harness_root)
    rc = cmd_health(Namespace(), deps)
    capsys.readouterr()
    assert rc == 0


def test_health_reports_plan_drift(harness_root: Path, deps, capsys) -> None:
    """A frozen plan whose file changed is reported, not raised."""
    _preseed_tokenizer(harness_root)
    from dwch.application.state import (
        load_state,
        save_state,
        set_plan_frozen,
    )

    plan_path = harness_root / ".harness" / "plan.toml"
    plan_path.write_text(
        '[meta]\nversion = 1\n\n[[tasks]]\nid = "t"\ntitle = "t"\n',
        encoding="utf-8",
    )
    state = load_state(deps.fs, harness_root)
    save_state(deps.fs, harness_root, set_plan_frozen(state, 1, "deadbeef"))
    rc = cmd_health(Namespace(), deps)
    out = capsys.readouterr().out
    assert "plan" in out
    # The plan check is non-critical.
    assert rc == 0


def test_check_git_missing_dot_git(tmp_path: Path, deps) -> None:
    """A missing `.git` entry is a failure."""
    other = _isolated_root(tmp_path, deps)
    name, ok, detail, critical = _check_git(other)
    assert name == "git"
    assert ok is False
    assert critical is True
    assert "no .git" in detail
