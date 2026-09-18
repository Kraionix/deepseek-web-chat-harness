"""Tests for `application.commands.bootstrap`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from dwch.application.commands.bootstrap import cmd_bootstrap
from dwch.application.commands.new_phase import cmd_new_phase
from dwch.application.handoff import BEGIN, END
from dwch.application.state import load_state, save_state, with_updates


def _args(clipboard: bool = False) -> Namespace:
    """Minimal namespace for `cmd_bootstrap`."""
    return Namespace(clipboard=clipboard)


def test_bootstrap_planning(harness_root: Path, deps, capsys) -> None:
    """A planning bootstrap contains header, progress, and protocol."""
    cmd_new_phase(Namespace(name="p", kind="planning"), deps)
    assert cmd_bootstrap(_args(), deps) == 0
    out = capsys.readouterr().out
    assert "section: header" in out
    assert "section: progress" in out
    assert "section: protocol" in out


def test_bootstrap_development_has_header_and_progress(
    harness_root: Path, deps, capsys
) -> None:
    """A development bootstrap (no roadmap) still has the header and progress."""
    cmd_new_phase(Namespace(name="d", kind="development"), deps)
    assert cmd_bootstrap(_args(), deps) == 0
    out = capsys.readouterr().out
    assert "section: header" in out
    assert "section: progress" in out


def test_bootstrap_omits_summary_section_when_empty(
    harness_root: Path, deps, capsys
) -> None:
    """With no recorded summary, the previous_summary section is absent."""
    cmd_new_phase(Namespace(name="p", kind="planning"), deps)
    assert cmd_bootstrap(_args(), deps) == 0
    out = capsys.readouterr().out
    assert "section: previous_summary" not in out


def test_bootstrap_shows_previous_summary(harness_root: Path, deps, capsys) -> None:
    """A recorded summary appears as the previous_summary section."""
    summaries = harness_root / ".harness" / "summaries"
    summaries.mkdir(parents=True, exist_ok=True)
    (summaries / "00-planning.md").write_text(
        "phase 00 designed the API\n", encoding="utf-8"
    )
    state = load_state(deps.fs, harness_root)
    save_state(
        deps.fs,
        harness_root,
        with_updates(state, summary_phase="00-planning", summary_written_at="t"),
    )
    cmd_new_phase(Namespace(name="01-dev", kind="development"), deps)
    assert cmd_bootstrap(_args(), deps) == 0
    out = capsys.readouterr().out
    assert "section: previous_summary" in out
    assert "phase 00 designed the API" in out


def test_bootstrap_reports_scoped_to_current_phase(
    harness_root: Path, deps, capsys
) -> None:
    """Only the current phase's reports appear in the bootstrap."""
    cmd_new_phase(Namespace(name="dev", kind="development"), deps)
    steps = harness_root / "steps"
    cur = steps / "dev"
    cur.mkdir(parents=True, exist_ok=True)
    (cur / "report-01.txt").write_text("current-phase-body\n", encoding="utf-8")
    other = steps / "other"
    other.mkdir(parents=True, exist_ok=True)
    (other / "report-01.txt").write_text("other-phase-body\n", encoding="utf-8")

    assert cmd_bootstrap(_args(), deps) == 0
    out = capsys.readouterr().out
    assert "current-phase-body" in out
    assert "other-phase-body" not in out


def test_bootstrap_strips_harness_block_from_task(
    harness_root: Path, deps, capsys
) -> None:
    """The `harness:begin`/`harness:end` block is stripped from `task`."""
    cmd_new_phase(Namespace(name="p", kind="planning"), deps)
    # The template already contains a block. After new-phase + ensure_metadata
    # the block is present. It must not appear in the task section body:
    # the header already shows the same fields.
    handoff_text = (harness_root / ".harness" / "handoff.md").read_text(
        encoding="utf-8"
    )
    # Sanity check: template carries both markers.
    assert BEGIN in handoff_text
    assert END in handoff_text

    assert cmd_bootstrap(_args(), deps) == 0
    out = capsys.readouterr().out
    # The header section legitimately prints phase and kind, but the raw
    # `harness:begin` marker is not part of the task section.
    # Locate the task section body and check the marker is not there.
    task_start = out.index("<!-- section: task -->")
    task_end = out.index("<!-- section:", task_start + 1)
    task_body = out[task_start:task_end]
    assert BEGIN not in task_body
    assert END not in task_body
