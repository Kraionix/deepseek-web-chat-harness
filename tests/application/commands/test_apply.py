"""Tests for `application.commands.apply`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.new_phase import cmd_new_phase

_STEP = "<<<FILE:src/a.py>>>\nx = 1\n<<<END>>>\n"


def _args(step: str = "01", from_file: str | None = None) -> Namespace:
    """Minimal namespace for `cmd_apply`."""
    return Namespace(step=step, from_file=from_file)


def _summary_args(from_file: str | None = None) -> Namespace:
    """`apply summary` uses the same namespace with `step='summary'`."""
    return Namespace(step="summary", from_file=from_file)


def _phase(root: Path, deps, name: str = "p1", kind: str = "planning") -> None:
    """Start a phase so that apply has somewhere to write."""
    assert cmd_new_phase(Namespace(name=name, kind=kind), deps) == 0


def _commit(deps, root: Path, message: str = "checkpoint") -> None:
    """Commit the tree so DELETE preconditions can see tracked files."""
    deps.git.commit_all(root, message)


# ---------------------------------------------------------------------------
# FILE ops
# ---------------------------------------------------------------------------


def test_apply_writes_files(harness_root: Path, deps) -> None:
    """A valid step message writes its files and the raw log."""
    _phase(harness_root, deps)
    deps.clipboard.text = _STEP
    assert cmd_apply(_args("01"), deps) == 0
    assert (harness_root / "src" / "a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (harness_root / "steps" / "p1" / "step-01.txt").is_file()


def test_apply_canonicalizes_single_digit_step(harness_root: Path, deps) -> None:
    """`apply 1` writes `step-01.txt`, matching what `verify 01` looks for."""
    _phase(harness_root, deps)
    deps.clipboard.text = _STEP
    assert cmd_apply(_args("1"), deps) == 0
    assert (harness_root / "steps" / "p1" / "step-01.txt").is_file()


def test_apply_canonicalizes_three_digit_step(harness_root: Path, deps) -> None:
    """`apply 001` writes `step-01.txt`."""
    _phase(harness_root, deps)
    deps.clipboard.text = _STEP
    assert cmd_apply(_args("001"), deps) == 0
    assert (harness_root / "steps" / "p1" / "step-01.txt").is_file()


def test_apply_rejects_zero_step(harness_root: Path, deps) -> None:
    """`apply 0` exits 2."""
    _phase(harness_root, deps)
    deps.clipboard.text = _STEP
    assert cmd_apply(_args("0"), deps) == 2


def test_apply_no_phase(harness_root: Path, deps) -> None:
    """Without an active phase, `apply` refuses."""
    deps.clipboard.text = _STEP
    assert cmd_apply(_args("01"), deps) == 2


def test_apply_empty_clipboard(harness_root: Path, deps) -> None:
    """An empty clipboard is an error."""
    _phase(harness_root, deps)
    assert cmd_apply(_args("01"), deps) == 2


def test_apply_from_file_relative_to_root(harness_root: Path, deps) -> None:
    """`--from-file` resolves against the project root."""
    _phase(harness_root, deps)
    (harness_root / "step.txt").write_text(_STEP, encoding="utf-8")
    assert cmd_apply(_args("01", from_file="step.txt"), deps) == 0
    assert (harness_root / "src" / "a.py").is_file()


def test_apply_bad_step(harness_root: Path, deps) -> None:
    """A non-integer step argument exits 2."""
    _phase(harness_root, deps)
    deps.clipboard.text = _STEP
    assert cmd_apply(_args("abc"), deps) == 2


def test_apply_duplicate_path(harness_root: Path, deps) -> None:
    """A duplicate path in the message exits 1 and saves the raw text."""
    _phase(harness_root, deps)
    deps.clipboard.text = (
        "<<<FILE:a.py>>>\n1\n<<<END>>>\n<<<FILE:a.py>>>\n2\n<<<END>>>\n"
    )
    assert cmd_apply(_args("01"), deps) == 1
    assert (harness_root / "steps" / "p1" / "step-01.txt").is_file()


def test_apply_invalid_path_writes_nothing(harness_root: Path, deps) -> None:
    """An unsafe path in the message means no file is written."""
    _phase(harness_root, deps)
    deps.clipboard.text = (
        "<<<FILE:src/a.py>>>\n1\n<<<END>>>\n<<<FILE:../escape.py>>>\n2\n<<<END>>>\n"
    )
    assert cmd_apply(_args("01"), deps) == 1
    assert not (harness_root / "src" / "a.py").exists()


def test_apply_rollback_on_write_failure(harness_root: Path, deps) -> None:
    """A write failure part-way rolls back the files already written."""
    _phase(harness_root, deps)
    # A directory where a file is expected: the second write fails.
    conflict = harness_root / "src" / "b.py"
    conflict.parent.mkdir(parents=True, exist_ok=True)
    conflict.mkdir()
    deps.clipboard.text = (
        "<<<FILE:src/a.py>>>\n1\n<<<END>>>\n<<<FILE:src/b.py>>>\n2\n<<<END>>>\n"
    )
    assert cmd_apply(_args("01"), deps) == 1
    assert not (harness_root / "src" / "a.py").exists()


# ---------------------------------------------------------------------------
# DELETE ops
# ---------------------------------------------------------------------------


def test_apply_delete_removes_tracked_file(harness_root: Path, deps) -> None:
    """A DELETE op removes a file that git tracks."""
    _phase(harness_root, deps)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "old.py").write_text("x = 1\n", encoding="utf-8")
    _commit(deps, harness_root)
    deps.clipboard.text = "<<<DELETE:src/old.py>>>\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 0
    assert not (harness_root / "src" / "old.py").exists()


def test_apply_delete_untracked_refused(harness_root: Path, deps, capsys) -> None:
    """Deleting an untracked file is refused before any write."""
    _phase(harness_root, deps)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "loose.py").write_text("x = 1\n", encoding="utf-8")
    deps.clipboard.text = "<<<DELETE:src/loose.py>>>\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 1
    assert (harness_root / "src" / "loose.py").exists()
    assert "untracked" in capsys.readouterr().err


def test_apply_delete_directory_refused(harness_root: Path, deps) -> None:
    """A DELETE targeting a directory is refused."""
    _phase(harness_root, deps)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    deps.clipboard.text = "<<<DELETE:src>>>\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 1
    assert (harness_root / "src").is_dir()


def test_apply_delete_protected_refused(harness_root: Path, deps, capsys) -> None:
    """A DELETE targeting a protected path is refused."""
    _phase(harness_root, deps)
    deps.clipboard.text = "<<<DELETE:.harness/state.toml>>>\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 1
    assert "protected" in capsys.readouterr().err


def test_apply_delete_with_non_empty_body(harness_root: Path, deps) -> None:
    """A DELETE block with a printable body is refused."""
    _phase(harness_root, deps)
    deps.clipboard.text = "<<<DELETE:src/old.py>>>\nfoo\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 1


def test_apply_log_records_delete(harness_root: Path, deps) -> None:
    """The apply log lists the deleted path."""
    _phase(harness_root, deps)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "old.py").write_text("x = 1\n", encoding="utf-8")
    _commit(deps, harness_root)
    deps.clipboard.text = "<<<DELETE:src/old.py>>>\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 0
    log = (harness_root / "steps" / "p1" / "apply-01.log").read_text(encoding="utf-8")
    assert "deleted src/old.py" in log


# ---------------------------------------------------------------------------
# MOVE ops
# ---------------------------------------------------------------------------


def test_apply_move_renames_file(harness_root: Path, deps) -> None:
    """A MOVE op renames the file and preserves its content."""
    _phase(harness_root, deps)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "old.py").write_text("x = 1\n", encoding="utf-8")
    _commit(deps, harness_root)
    deps.clipboard.text = "<<<MOVE:src/old.py:src/new.py>>>\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 0
    assert not (harness_root / "src" / "old.py").exists()
    assert (harness_root / "src" / "new.py").read_text(encoding="utf-8") == "x = 1\n"


def test_apply_move_dst_exists_refused(harness_root: Path, deps, capsys) -> None:
    """A MOVE whose destination exists is refused."""
    _phase(harness_root, deps)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "a.py").write_text("a\n", encoding="utf-8")
    (harness_root / "src" / "b.py").write_text("b\n", encoding="utf-8")
    _commit(deps, harness_root)
    deps.clipboard.text = "<<<MOVE:src/a.py:src/b.py>>>\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 1
    assert (harness_root / "src" / "a.py").exists()
    assert "already exists" in capsys.readouterr().err


def test_apply_move_src_missing_refused(harness_root: Path, deps) -> None:
    """A MOVE whose source does not exist is refused."""
    _phase(harness_root, deps)
    deps.clipboard.text = "<<<MOVE:src/ghost.py:src/new.py>>>\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 1


def test_apply_move_protected_refused(harness_root: Path, deps, capsys) -> None:
    """A MOVE whose source is protected is refused."""
    _phase(harness_root, deps)
    deps.clipboard.text = (
        "<<<MOVE:.harness/roadmap.toml:src/roadmap_backup.toml>>>\n<<<END>>>\n"
    )
    assert cmd_apply(_args("01"), deps) == 1
    assert "protected" in capsys.readouterr().err


def test_apply_log_records_move(harness_root: Path, deps) -> None:
    """The apply log lists the moved pair."""
    _phase(harness_root, deps)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "old.py").write_text("x\n", encoding="utf-8")
    _commit(deps, harness_root)
    deps.clipboard.text = "<<<MOVE:src/old.py:src/new.py>>>\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 0
    log = (harness_root / "steps" / "p1" / "apply-01.log").read_text(encoding="utf-8")
    assert "moved src/old.py → src/new.py" in log


# ---------------------------------------------------------------------------
# Dirty tracked files
# ---------------------------------------------------------------------------


def test_apply_refuses_dirty_tracked_file(harness_root: Path, deps, capsys) -> None:
    """A step touching a modified tracked file is refused."""
    _phase(harness_root, deps)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "a.py").write_text("v1\n", encoding="utf-8")
    _commit(deps, harness_root)
    # Modify without committing.
    (harness_root / "src" / "a.py").write_text("v2\n", encoding="utf-8")
    deps.clipboard.text = "<<<FILE:src/a.py>>>\nnew\n<<<END>>>\n"
    assert cmd_apply(_args("01"), deps) == 1
    err = capsys.readouterr().err
    assert "uncommitted changes" in err
    # File content on disk is unchanged.
    assert (harness_root / "src" / "a.py").read_text(encoding="utf-8") == "v2\n"


# ---------------------------------------------------------------------------
# Summary form
# ---------------------------------------------------------------------------


def test_apply_summary_ok(harness_root: Path, deps) -> None:
    """A single block for the current phase's summary is written."""
    _phase(harness_root, deps)
    deps.clipboard.text = (
        "<<<FILE:.harness/summaries/p1.md>>>\nphase one done\n<<<END>>>\n"
    )
    assert cmd_apply(_summary_args(), deps) == 0
    body = (harness_root / ".harness" / "summaries" / "p1.md").read_text(
        encoding="utf-8"
    )
    assert body == "phase one done\n"


def test_apply_summary_refuses_overwrite(harness_root: Path, deps, capsys) -> None:
    """A second summary for the same phase is refused."""
    _phase(harness_root, deps)
    deps.clipboard.text = "<<<FILE:.harness/summaries/p1.md>>>\nfirst\n<<<END>>>\n"
    assert cmd_apply(_summary_args(), deps) == 0
    deps.clipboard.text = "<<<FILE:.harness/summaries/p1.md>>>\nsecond\n<<<END>>>\n"
    assert cmd_apply(_summary_args(), deps) == 2
    body = (harness_root / ".harness" / "summaries" / "p1.md").read_text(
        encoding="utf-8"
    )
    assert body == "first\n"
    assert "already exists" in capsys.readouterr().err


def test_apply_summary_wrong_path(harness_root: Path, deps) -> None:
    """A block targeting a different phase's summary is refused."""
    _phase(harness_root, deps)
    deps.clipboard.text = "<<<FILE:.harness/summaries/other.md>>>\nbody\n<<<END>>>\n"
    assert cmd_apply(_summary_args(), deps) == 1


def test_apply_summary_multiple_blocks(harness_root: Path, deps) -> None:
    """More than one block is refused."""
    _phase(harness_root, deps)
    deps.clipboard.text = (
        "<<<FILE:.harness/summaries/p1.md>>>\nbody\n<<<END>>>\n"
        "<<<FILE:other.txt>>>\nx\n<<<END>>>\n"
    )
    assert cmd_apply(_summary_args(), deps) == 1


def test_apply_summary_delete_block_refused(harness_root: Path, deps) -> None:
    """A summary consisting of a DELETE block is refused."""
    _phase(harness_root, deps)
    deps.clipboard.text = "<<<DELETE:.harness/summaries/p1.md>>>\n<<<END>>>\n"
    assert cmd_apply(_summary_args(), deps) == 1


def test_apply_summary_no_phase(harness_root: Path, deps) -> None:
    """Without an active phase, `apply summary` refuses."""
    deps.clipboard.text = "<<<FILE:.harness/summaries/x.md>>>\nbody\n<<<END>>>\n"
    assert cmd_apply(_summary_args(), deps) == 2


def test_apply_summary_saves_raw(harness_root: Path, deps) -> None:
    """The raw summary message is saved to `steps/{phase}/summary.txt`."""
    _phase(harness_root, deps)
    text = "<<<FILE:.harness/summaries/p1.md>>>\nbody\n<<<END>>>\n"
    deps.clipboard.text = text
    assert cmd_apply(_summary_args(), deps) == 0
    raw = (harness_root / "steps" / "p1" / "summary.txt").read_text(encoding="utf-8")
    assert raw == text
