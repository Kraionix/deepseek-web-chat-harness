"""Tests for `application.commands.health`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.health import cmd_health
from dwch.application.state import load_state, save_state, with_updates


def _preseed_tokenizer(root: Path) -> None:
    """Create a dummy tokenizer file so the check can pass."""
    data = root / ".harness" / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "deepseek_tokenizer.json").write_bytes(b"{}")


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
