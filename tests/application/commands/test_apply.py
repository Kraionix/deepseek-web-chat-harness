"""Tests for `application.commands.apply`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.start import cmd_start

_STEP = "<<<FILE:src/a.py>>>\nx = 1\n<<<END>>>\n"


def _args(from_file: str | None = None) -> Namespace:
    """Minimal namespace for `cmd_apply`."""
    return Namespace(from_file=from_file)


def _start(root: Path, deps) -> None:
    """Start a planning phase so apply has somewhere to write."""
    assert cmd_start(Namespace(goal="plan", kind="planning"), deps) == 0


def _phase_dir(harness_root: Path) -> Path:
    """Return the single phase directory created by `_start`."""
    steps_root = harness_root / "steps"
    dirs = [p for p in steps_root.iterdir() if p.is_dir()]
    assert len(dirs) == 1, f"expected one phase directory, got {dirs}"
    return dirs[0]


def test_apply_writes_files(harness_root: Path, deps) -> None:
    """A valid message writes its files and the raw log."""
    _start(harness_root, deps)
    deps.clipboard.text = _STEP
    assert cmd_apply(_args(), deps) == 0
    assert (harness_root / "src" / "a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (_phase_dir(harness_root) / "planning" / "message.txt").is_file()


def test_apply_no_phase(harness_root: Path, deps) -> None:
    """Without an active phase, `apply` refuses."""
    deps.clipboard.text = _STEP
    assert cmd_apply(_args(), deps) == 2


def test_apply_empty_clipboard(harness_root: Path, deps) -> None:
    """An empty clipboard is an error."""
    _start(harness_root, deps)
    assert cmd_apply(_args(), deps) == 2


def test_apply_from_file_relative_to_root(harness_root: Path, deps) -> None:
    """`--from-file` resolves against the project root."""
    _start(harness_root, deps)
    (harness_root / "step.txt").write_text(_STEP, encoding="utf-8")
    assert cmd_apply(_args(from_file="step.txt"), deps) == 0
    assert (harness_root / "src" / "a.py").is_file()


def test_apply_duplicate_path(harness_root: Path, deps) -> None:
    """A duplicate path in the message exits 1."""
    _start(harness_root, deps)
    deps.clipboard.text = (
        "<<<FILE:a.py>>>\n1\n<<<END>>>\n<<<FILE:a.py>>>\n2\n<<<END>>>\n"
    )
    assert cmd_apply(_args(), deps) == 1


def test_apply_invalid_path_writes_nothing(harness_root: Path, deps) -> None:
    """An unsafe path means no file is written."""
    _start(harness_root, deps)
    deps.clipboard.text = (
        "<<<FILE:src/a.py>>>\n1\n<<<END>>>\n<<<FILE:../escape.py>>>\n2\n<<<END>>>\n"
    )
    assert cmd_apply(_args(), deps) == 1
    assert not (harness_root / "src" / "a.py").exists()


def test_apply_delete_protected_refused(harness_root: Path, deps, capsys) -> None:
    """A DELETE targeting a protected path is refused."""
    _start(harness_root, deps)
    deps.clipboard.text = "<<<DELETE:.harness/state.toml>>>\n<<<END>>>\n"
    assert cmd_apply(_args(), deps) == 1
    assert "protected" in capsys.readouterr().err


def test_apply_resets_verify_ok(harness_root: Path, deps) -> None:
    """A successful apply resets `state.verify.ok`."""
    from dwch.application.state import load_state, save_state, set_verify_ok

    _start(harness_root, deps)
    state = load_state(deps.fs, harness_root)
    save_state(
        deps.fs,
        harness_root,
        set_verify_ok(state, "planning", "2026-01-01T00:00:00+00:00"),
    )
    deps.clipboard.text = _STEP
    assert cmd_apply(_args(), deps) == 0
    after = load_state(deps.fs, harness_root)
    assert after.verify_ok is False
