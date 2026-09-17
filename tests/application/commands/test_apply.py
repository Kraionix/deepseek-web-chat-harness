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


def _phase(root: Path, deps, name: str = "p1", kind: str = "planning") -> None:
    """Start a phase so that apply has somewhere to write."""
    assert cmd_new_phase(Namespace(name=name, kind=kind), deps) == 0


def test_apply_writes_files(harness_root: Path, deps) -> None:
    """A valid step message writes its files and the raw log."""
    _phase(harness_root, deps)
    deps.clipboard.text = _STEP
    assert cmd_apply(_args("01"), deps) == 0
    assert (harness_root / "src" / "a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (harness_root / "steps" / "p1" / "step-01.txt").is_file()


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
    assert cmd_apply(_args("01"), deps) == 2
    assert not (harness_root / "src" / "a.py").exists()
