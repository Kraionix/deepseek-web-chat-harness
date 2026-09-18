"""Tests for `application.handoff`.

Covers `ensure_metadata`, the 0.3.0 replacement for
`update_metadata`, and the 0.3.1 robustness fixes: stray markers
are cleaned up, duplicate markers are collapsed, and the block is
always exactly one.
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


def _read(root: Path) -> str:
    """Read `.harness/handoff.md` under `root`."""
    return (root / ".harness" / "handoff.md").read_text(encoding="utf-8")


def test_rewrites_only_block(tmp_path: Path) -> None:
    """The prose around the harness block is preserved verbatim."""
    body = f"intro\n{BEGIN}\nphase: old\n{END}\noutro\n"
    _write(tmp_path, body)
    ensure_metadata(LocalFilesystem(), tmp_path, initial_state())
    result = _read(tmp_path)
    assert result.startswith("intro\n")
    assert result.endswith("outro\n")
    assert "phase: unset" in result


def test_noop_when_missing(tmp_path: Path) -> None:
    """A missing handoff file is not an error."""
    ensure_metadata(LocalFilesystem(), tmp_path, initial_state())
    assert not (tmp_path / ".harness" / "handoff.md").exists()


def test_inserts_block_when_markers_missing(tmp_path: Path) -> None:
    """A handoff without markers gets the block prepended."""
    _write(tmp_path, "no markers here\n")
    ensure_metadata(LocalFilesystem(), tmp_path, initial_state())
    after = _read(tmp_path)
    assert after.startswith(BEGIN)
    assert END in after
    assert after.endswith("no markers here\n")


def test_inserts_block_reflects_state(tmp_path: Path) -> None:
    """The inserted block carries values from the given state."""
    _write(tmp_path, "prose only\n")
    state = initial_state()
    ensure_metadata(LocalFilesystem(), tmp_path, state)
    after = _read(tmp_path)
    assert f"phase: {state.current_phase}" in after
    assert f"kind: {state.phase_kind}" in after


def test_repairs_stray_begin(tmp_path: Path) -> None:
    """A stray `BEGIN` with no `END` is removed, and a fresh block is added."""
    _write(tmp_path, f"intro\n{BEGIN}\nprose\n")
    ensure_metadata(LocalFilesystem(), tmp_path, initial_state())
    after = _read(tmp_path)
    assert after.count(BEGIN) == 1
    assert after.count(END) == 1
    # `intro` and `prose` survive, the stray marker is gone.
    assert "intro" in after
    assert "prose" in after
    # Only one full block.
    assert after.index(BEGIN) < after.index(END)


def test_repairs_stray_end(tmp_path: Path) -> None:
    """A stray `END` with no `BEGIN` is removed, and a fresh block is added."""
    _write(tmp_path, f"intro\n{END}\nprose\n")
    ensure_metadata(LocalFilesystem(), tmp_path, initial_state())
    after = _read(tmp_path)
    assert after.count(BEGIN) == 1
    assert after.count(END) == 1
    assert "intro" in after
    assert "prose" in after


def test_collapses_duplicate_begin(tmp_path: Path) -> None:
    """Two `BEGIN` and one `END` collapse to a single fresh block."""
    body = f"X\n{BEGIN}\nA\n{BEGIN}\nB\n{END}\nC\n"
    _write(tmp_path, body)
    ensure_metadata(LocalFilesystem(), tmp_path, initial_state())
    after = _read(tmp_path)
    assert after.count(BEGIN) == 1
    assert after.count(END) == 1
    assert "X" in after
    assert "C" in after


def test_repeated_calls_do_not_accumulate(tmp_path: Path) -> None:
    """Repeated `ensure_metadata` calls never grow the file's block count."""
    _write(tmp_path, f"prose\n{BEGIN}\nold\n{END}\n")
    fs = LocalFilesystem()
    state = initial_state()
    for _ in range(5):
        ensure_metadata(fs, tmp_path, state)
    after = _read(tmp_path)
    assert after.count(BEGIN) == 1
    assert after.count(END) == 1
