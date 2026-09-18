"""Tests for `application.handoff`.

Covers `ensure_metadata`, the 0.3.0 replacement for
`update_metadata`. Three paths: rewrite the existing block, no-op
when the file is missing, and insert the block at the top when the
markers are missing.
"""

from __future__ import annotations

from pathlib import Path

from dwch.adapters.filesystem import LocalFilesystem
from dwch.application.handoff import BEGIN, END, ensure_metadata
from dwch.application.state import initial_state


def _write(root: Path, body: str) -> None:
    """Write `.harness/handoff.md` under `root`."""
    harness = root / ".harness"
    harness.mkdir(parents=True, exist_ok=True)
    (harness / "handoff.md").write_text(body, encoding="utf-8")


def test_rewrites_only_block(tmp_path: Path) -> None:
    """The prose around the harness block is preserved verbatim."""
    body = f"intro\n{BEGIN}\nphase: old\n{END}\noutro\n"
    _write(tmp_path, body)
    ensure_metadata(LocalFilesystem(), tmp_path, initial_state())
    result = (tmp_path / ".harness" / "handoff.md").read_text(encoding="utf-8")
    assert result.startswith("intro\n")
    assert result.endswith("outro\n")
    assert "phase: unset" in result


def test_noop_when_missing(tmp_path: Path) -> None:
    """A missing handoff file is not an error."""
    ensure_metadata(LocalFilesystem(), tmp_path, initial_state())
    assert not (tmp_path / ".harness" / "handoff.md").exists()


def test_inserts_block_when_markers_missing(tmp_path: Path) -> None:
    """A handoff without markers gets the block prepended."""
    body = "no markers here\n"
    _write(tmp_path, body)
    ensure_metadata(LocalFilesystem(), tmp_path, initial_state())
    after = (tmp_path / ".harness" / "handoff.md").read_text(encoding="utf-8")
    assert after.startswith(BEGIN)
    assert END in after
    assert after.endswith("no markers here\n")


def test_inserts_block_reflects_state(tmp_path: Path) -> None:
    """The inserted block carries values from the given state."""
    _write(tmp_path, "prose only\n")
    state = initial_state()
    ensure_metadata(LocalFilesystem(), tmp_path, state)
    after = (tmp_path / ".harness" / "handoff.md").read_text(encoding="utf-8")
    assert f"phase: {state.current_phase}" in after
    assert f"kind: {state.phase_kind}" in after
