"""Tests for `application.handoff`."""

from __future__ import annotations

from pathlib import Path

from dwch.adapters.filesystem import LocalFilesystem
from dwch.application.handoff import update_metadata
from dwch.application.state import initial_state


def _write(root: Path, body: str) -> None:
    """Write `.harness/handoff.md` under `root`."""
    harness = root / ".harness"
    harness.mkdir(parents=True, exist_ok=True)
    (harness / "handoff.md").write_text(body, encoding="utf-8")


def test_rewrites_only_block(tmp_path: Path) -> None:
    """The prose around the harness block is preserved verbatim."""
    body = "intro\n<!-- harness:begin -->\nphase: old\n<!-- harness:end -->\noutro\n"
    _write(tmp_path, body)
    update_metadata(LocalFilesystem(), tmp_path, initial_state())
    result = (tmp_path / ".harness" / "handoff.md").read_text(encoding="utf-8")
    assert result.startswith("intro\n")
    assert result.endswith("outro\n")
    assert "phase: unset" in result


def test_noop_when_missing(tmp_path: Path) -> None:
    """A missing handoff file is not an error."""
    update_metadata(LocalFilesystem(), tmp_path, initial_state())
    assert not (tmp_path / ".harness" / "handoff.md").exists()


def test_noop_when_markers_missing(tmp_path: Path) -> None:
    """A handoff file without markers is left alone."""
    body = "no markers here\n"
    _write(tmp_path, body)
    update_metadata(LocalFilesystem(), tmp_path, initial_state())
    after = (tmp_path / ".harness" / "handoff.md").read_text(encoding="utf-8")
    assert after == body
