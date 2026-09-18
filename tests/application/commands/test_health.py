"""Tests for `application.commands.health`."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
from pathlib import Path

from dwch.application.commands.health import _check_git, cmd_health
from dwch.application.state import load_state, save_state, with_updates


def _preseed_tokenizer(root: Path) -> None:
    """Create a dummy tokenizer file so the check can pass."""
    data = root / ".harness" / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "deepseek_tokenizer.json").write_bytes(b"{}")


def _isolated_root(tmp_path: Path, deps) -> object:
    """Return a `Deps` whose `project_root` is a fresh, git-free subdir.

    `tmp_path` in a test is the *same* directory as `project_root`:
    both are the per-test `tmp_path`. So `tmp_path` already contains
    the `.git` created by the `project_root` fixture. To exercise the
    "no `.git` here" branches of `_check_git`, the test must point
    `Deps` at a subdirectory that was never initialized as a repo.
    """
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


def test_health_survives_malformed_lock(harness_root: Path, deps, capsys) -> None:
    """A malformed lock is reported, not raised."""
    _preseed_tokenizer(harness_root)
    (harness_root / ".harness" / "roadmap.toml").write_text(
        '[meta]\nversion = 1\n\n[[steps]]\nnumber = 1\ntitle = "x"\n',
        encoding="utf-8",
    )
    (harness_root / ".harness" / "roadmap.lock").write_text("not = ", encoding="utf-8")
    rc = cmd_health(Namespace(), deps)
    out = capsys.readouterr().out
    assert "invalid lock" in out
    # The roadmap check is non-critical, so it does not change the
    # exit code when every critical check passes.
    assert rc == 0


def test_health_reports_missing_summary_file(harness_root: Path, deps, capsys) -> None:
    """A state that names a missing summary file is reported."""
    _preseed_tokenizer(harness_root)
    state = load_state(deps.fs, harness_root)
    save_state(
        deps.fs,
        harness_root,
        with_updates(state, summary_phase="ghost", summary_written_at="t"),
    )
    rc = cmd_health(Namespace(), deps)
    out = capsys.readouterr().out
    assert "summary" in out
    assert "file missing" in out
    # The summary check is non-critical.
    assert rc == 0


def test_check_git_dot_git_file(tmp_path: Path, deps) -> None:
    """A `.git` file (worktree, submodule) is not reported as missing.

    The `.git` entry may be a directory (common case) or a file
    (linked worktree, submodule). Both are valid git repositories.
    Only a missing entry is a failure. This test asserts the `git`
    check does not report the worktree case as "no .git".
    """
    other = _isolated_root(tmp_path, deps)
    (other.project_root / ".git").write_text("gitdir: /nonexistent\n", encoding="utf-8")

    name, _ok, detail, _critical = _check_git(other)
    assert name == "git"
    # The `.git` presence check passes; the git command may then
    # fail because the worktree pointer is broken, but that is a
    # different message.
    assert "no .git directory or file" not in detail


def test_check_git_missing_dot_git(tmp_path: Path, deps) -> None:
    """A missing `.git` entry is still a failure."""
    other = _isolated_root(tmp_path, deps)
    name, ok, detail, critical = _check_git(other)
    assert name == "git"
    assert ok is False
    assert critical is True
    assert "no .git" in detail
