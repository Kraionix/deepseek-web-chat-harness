"""Tests for `application.commands.verify` in a development phase.

Every test here runs a full planning phase first (`_plan_and_freeze`)
so that the development phase has a frozen roadmap to check
against. That setup, plus `verify`'s own git calls, makes all the
tests slow; the whole file is marked as such.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from dwch.application.commands.apply import cmd_apply
from dwch.application.commands.close import cmd_close
from dwch.application.commands.new_phase import cmd_new_phase
from dwch.application.commands.verify import cmd_verify
from dwch.application.state import load_state

pytestmark = pytest.mark.slow

_ROADMAP = """\
[meta]
version = 1
note = "demo"

[[interfaces]]
name = "greet"
kind = "function"
module = "src/app.py"
signature = "def greet(name)"
doc = ""

[[steps]]
number = 1
title = "Greet"
goal = "Write greet."
files = ["src/app.py"]
interfaces = ["greet"]
acceptance = []
depends_on = []
"""

_ROADMAP_CHANGES = """\
[meta]
version = 1
note = "demo"

[[steps]]
number = 1
title = "Move and delete"
goal = "..."
files = ["src/app.py"]
removes = ["src/legacy.py"]
moves = [
  { from = "src/old.py", to = "src/new.py" },
]
interfaces = []
acceptance = []
depends_on = []
"""

_GREET = "def greet(name):\n    return name\n"


def _plan_and_freeze(root: Path, deps, roadmap: str = _ROADMAP) -> None:
    """Run a short planning phase to produce a frozen roadmap."""
    assert cmd_new_phase(Namespace(name="plan", kind="planning"), deps) == 0
    deps.clipboard.text = "<<<FILE:.harness/roadmap.toml>>>\n" + roadmap + "<<<END>>>\n"
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)
    arch = root / "docs" / "architecture.md"
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("Architecture\n", encoding="utf-8")

    deps.clipboard.text = (
        "<<<FILE:.harness/summaries/plan.md>>>\nplanning done\n<<<END>>>\n"
    )
    assert cmd_apply(Namespace(step="summary", from_file=None), deps) == 0

    assert cmd_close(Namespace(tag=False, freeze=True), deps) == 0
    assert cmd_new_phase(Namespace(name="dev", kind="development"), deps) == 0


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_development_happy_path(harness_root: Path, deps) -> None:
    """A matching step passes and advances `roadmap_step`."""
    _plan_and_freeze(harness_root, deps)
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    assert cmd_apply(Namespace(step="01", from_file=None), deps) == 0
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.roadmap_step == 1


def test_development_delete_happy_path(harness_root: Path, deps) -> None:
    """A step whose DELETE matches `removes` passes and advances.

    The moved file must itself be valid Python: `check_compile`
    reads `MoveOp.dst` after the rename, and a rename of a
    non-Python body would fail the compile check.
    """
    _plan_and_freeze(harness_root, deps, roadmap=_ROADMAP_CHANGES)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "legacy.py").write_text("old = 1\n", encoding="utf-8")
    (harness_root / "src" / "old.py").write_text("x = 1\n", encoding="utf-8")
    deps.git.commit_all(harness_root, "seed")

    deps.clipboard.text = (
        "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
        "<<<MOVE:src/old.py:src/new.py>>>\n<<<END>>>\n"
        "<<<DELETE:src/legacy.py>>>\n<<<END>>>\n"
    )
    assert cmd_apply(Namespace(step="01", from_file=None), deps) == 0
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.roadmap_step == 1


def test_development_blocker_does_not_advance(harness_root: Path, deps) -> None:
    """A blocker deviation is committed but does not advance the plan."""
    _plan_and_freeze(harness_root, deps)
    blocker = (
        ".harness/deviations/step-01.toml",
        '[[deviation]]\ntype = "blocker"\nreason = "nope"\n',
    )
    deps.clipboard.text = f"<<<FILE:{blocker[0]}>>>\n{blocker[1]}<<<END>>>\n"
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)
    state = load_state(deps.fs, harness_root)
    assert state.roadmap_step == 0


# ---------------------------------------------------------------------------
# Auto-deviations for delete / move
# ---------------------------------------------------------------------------


def test_development_extra_removal_deviation(harness_root: Path, deps) -> None:
    """An extra DELETE produces an `extra-removal` auto-deviation."""
    _plan_and_freeze(harness_root, deps)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "app.py").write_text(_GREET, encoding="utf-8")
    (harness_root / "src" / "surprise.py").write_text("x = 1\n", encoding="utf-8")
    deps.git.commit_all(harness_root, "seed")

    deps.clipboard.text = (
        "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
        "<<<DELETE:src/surprise.py>>>\n<<<END>>>\n"
    )
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)

    auto = harness_root / ".harness" / "deviations" / "step-01-auto.toml"
    assert auto.is_file()
    body = auto.read_text(encoding="utf-8")
    assert "extra-removal" in body


def test_development_missing_removal_deviation(harness_root: Path, deps) -> None:
    """A file in `removes` not deleted produces a `missing-removal`."""
    _plan_and_freeze(harness_root, deps, roadmap=_ROADMAP_CHANGES)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "legacy.py").write_text("old = 1\n", encoding="utf-8")
    (harness_root / "src" / "old.py").write_text("x = 1\n", encoding="utf-8")
    deps.git.commit_all(harness_root, "seed")

    # Deliver only the file write; skip the DELETE and MOVE.
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)

    auto = harness_root / ".harness" / "deviations" / "step-01-auto.toml"
    body = auto.read_text(encoding="utf-8")
    assert "missing-removal" in body
    assert "missing-move" in body


def test_development_extra_move_deviation(harness_root: Path, deps) -> None:
    """A MOVE not listed in `moves` produces an `extra-move` deviation."""
    _plan_and_freeze(harness_root, deps)
    (harness_root / "src").mkdir(parents=True, exist_ok=True)
    (harness_root / "src" / "app.py").write_text(_GREET, encoding="utf-8")
    (harness_root / "src" / "surprise.py").write_text("x = 1\n", encoding="utf-8")
    deps.git.commit_all(harness_root, "seed")

    deps.clipboard.text = (
        "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
        "<<<MOVE:src/surprise.py:src/renamed.py>>>\n<<<END>>>\n"
    )
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)

    auto = harness_root / ".harness" / "deviations" / "step-01-auto.toml"
    body = auto.read_text(encoding="utf-8")
    assert "extra-move" in body


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def test_development_past_end_of_roadmap(harness_root: Path, deps) -> None:
    """A step past the end of the roadmap fails."""
    _plan_and_freeze(harness_root, deps)
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    cmd_apply(Namespace(step="01", from_file=None), deps)
    cmd_verify(Namespace(step="01", clipboard=False), deps)

    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    cmd_apply(Namespace(step="02", from_file=None), deps)
    assert cmd_verify(Namespace(step="02", clipboard=False), deps) == 1


def test_development_bad_step_argument(harness_root: Path, deps) -> None:
    """A non-integer step argument exits 2."""
    _plan_and_freeze(harness_root, deps)
    assert cmd_verify(Namespace(step="abc", clipboard=False), deps) == 2


def test_development_single_digit_step_matches_two_digit(
    harness_root: Path, deps
) -> None:
    """`apply 1` + `verify 1` resolve to the same step file."""
    _plan_and_freeze(harness_root, deps)
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    assert cmd_apply(Namespace(step="1", from_file=None), deps) == 0
    assert cmd_verify(Namespace(step="1", clipboard=False), deps) == 0
    state = load_state(deps.fs, harness_root)
    assert state.roadmap_step == 1


def test_development_frozen_but_missing_roadmap(
    harness_root: Path, deps, capsys
) -> None:
    """state.frozen with no roadmap file fails with `roadmap-missing`."""
    _plan_and_freeze(harness_root, deps)
    (harness_root / ".harness" / "roadmap.toml").unlink()

    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    assert cmd_apply(Namespace(step="01", from_file=None), deps) == 0
    rc = cmd_verify(Namespace(step="01", clipboard=False), deps)
    assert rc == 1

    report = (harness_root / "steps" / "dev" / "report-01.txt").read_text(
        encoding="utf-8"
    )
    assert "roadmap-missing" in report
    assert "not committed" in report


def test_development_commit_failure_restores_state(
    harness_root: Path, deps, broken_deps, capsys
) -> None:
    """A failed commit leaves state at the pre-verify values."""
    _plan_and_freeze(harness_root, deps)
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    assert cmd_apply(Namespace(step="01", from_file=None), deps) == 0

    before = load_state(deps.fs, harness_root)
    rc = cmd_verify(Namespace(step="01", clipboard=False), broken_deps)
    assert rc != 0

    after = load_state(deps.fs, harness_root)
    assert after.roadmap_step == before.roadmap_step
    assert after.current_step == before.current_step
    assert after.last_commit_date == before.last_commit_date

    err = capsys.readouterr().err
    assert "commit failed" in err
    assert "state was restored" in err

    report = (harness_root / "steps" / "dev" / "report-01.txt").read_text(
        encoding="utf-8"
    )
    assert "not committed" in report


def test_development_rejects_step_file_with_unsafe_path(
    harness_root: Path, deps
) -> None:
    """A hand-edited step file with `..` is rejected by verify."""
    _plan_and_freeze(harness_root, deps)
    deps.clipboard.text = "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
    assert cmd_apply(Namespace(step="01", from_file=None), deps) == 0

    step_file = harness_root / "steps" / "dev" / "step-01.txt"
    step_file.write_text(
        "<<<FILE:src/app.py>>>\n" + _GREET + "<<<END>>>\n"
        "<<<FILE:../escape.py>>>\nx\n<<<END>>>\n",
        encoding="utf-8",
    )
    assert cmd_verify(Namespace(step="01", clipboard=False), deps) == 2
