"""Tests for `application.state`."""

from __future__ import annotations

from pathlib import Path

import pytest

from dwch.adapters.filesystem import LocalFilesystem
from dwch.application.state import (
    TIMESTAMP_TIMESPEC,
    advance_position,
    increment_rollback,
    initial_state,
    load_state,
    now_iso,
    reset_failure,
    reset_position,
    save_state,
    set_phase_abandoned,
    set_phase_closed,
    set_phase_open,
    set_plan_frozen,
    set_verify_fail,
    set_verify_ok,
    with_updates,
)
from dwch.shared.errors import FilesystemError, StateError
from tests.fakes import RenameFails


def _harness(root: Path) -> Path:
    """Create `.harness/` under `root` and return the root."""
    (root / ".harness").mkdir(parents=True, exist_ok=True)
    return root


def test_round_trip(tmp_path: Path) -> None:
    """State saved then loaded is identical."""
    root = _harness(tmp_path)
    fs = LocalFilesystem()
    state = initial_state()
    save_state(fs, root, state)
    assert load_state(fs, root) == state


def test_load_missing(tmp_path: Path) -> None:
    """A missing state file raises `StateError`."""
    root = _harness(tmp_path)
    with pytest.raises(StateError, match="state not found"):
        load_state(LocalFilesystem(), root)


def test_load_bad_toml(tmp_path: Path) -> None:
    """Malformed state TOML raises `StateError`."""
    root = _harness(tmp_path)
    (root / ".harness" / "state.toml").write_text("nope = ", encoding="utf-8")
    with pytest.raises(StateError, match="invalid TOML"):
        load_state(LocalFilesystem(), root)


def test_load_rejects_old_version(tmp_path: Path) -> None:
    """A state file written by an older harness is rejected."""
    root = _harness(tmp_path)
    fs = LocalFilesystem()
    save_state(fs, root, initial_state())
    path = root / ".harness" / "state.toml"
    body = path.read_text(encoding="utf-8").replace(
        'version = "0.4.0"', 'version = "0.3.0"'
    )
    path.write_text(body, encoding="utf-8")
    with pytest.raises(StateError, match="does not match"):
        load_state(fs, root)


def test_save_is_atomic(tmp_path: Path) -> None:
    """A failing rename leaves the original state file unchanged."""
    root = _harness(tmp_path)
    fs = LocalFilesystem()
    save_state(fs, root, initial_state())
    original = (root / ".harness" / "state.toml").read_text(encoding="utf-8")

    broken = RenameFails()
    new_state = with_updates(initial_state(), phase_name="new-phase")
    with pytest.raises(FilesystemError):
        save_state(broken, root, new_state)

    after = (root / ".harness" / "state.toml").read_text(encoding="utf-8")
    assert after == original


def test_set_phase_open(tmp_path: Path) -> None:
    """Opening a phase sets name, kind, status, and opened_at."""
    state = initial_state()
    fresh = set_phase_open(state, "p1", "planning", "2026-01-01T00:00:00+00:00")
    assert fresh.phase_name == "p1"
    assert fresh.phase_kind == "planning"
    assert fresh.phase_status == "open"
    assert fresh.phase_opened_at == "2026-01-01T00:00:00+00:00"
    assert fresh.phase_closed_at == ""


def test_set_phase_closed(tmp_path: Path) -> None:
    """Closing a phase sets status and closed_at."""
    state = with_updates(initial_state(), phase_status="open")
    fresh = set_phase_closed(state, "2026-01-02T00:00:00+00:00")
    assert fresh.phase_status == "closed"
    assert fresh.phase_closed_at == "2026-01-02T00:00:00+00:00"


def test_set_phase_abandoned(tmp_path: Path) -> None:
    """Abandoning a phase sets status and closed_at."""
    state = with_updates(initial_state(), phase_status="open")
    fresh = set_phase_abandoned(state, "2026-01-02T00:00:00+00:00")
    assert fresh.phase_status == "abandoned"


def test_set_verify_ok_clears_failure() -> None:
    """A successful verify clears failure fields."""
    state = with_updates(
        initial_state(),
        failure_task_id="t1",
        failure_check_name="compile",
        failure_excerpt="bad",
        failure_count=2,
    )
    fresh = set_verify_ok(state, "t1", "2026-01-01T00:00:00+00:00")
    assert fresh.verify_ok is True
    assert fresh.verify_task_id == "t1"
    assert fresh.failure_task_id == ""
    assert fresh.failure_count == 0


def test_set_verify_fail_increments_count() -> None:
    """Consecutive failures on the same task increment the count."""
    state = initial_state()
    s1 = set_verify_fail(state, "t1", "compile", "x", "at1")
    assert s1.failure_count == 1
    s2 = set_verify_fail(s1, "t1", "compile", "x", "at2")
    assert s2.failure_count == 2
    s3 = set_verify_fail(s2, "t1", "compile", "x", "at3")
    assert s3.failure_count == 3


def test_set_verify_fail_resets_on_different_task() -> None:
    """A failure on a different task resets the count to 1."""
    state = set_verify_fail(initial_state(), "t1", "compile", "x", "at1")
    state = set_verify_fail(state, "t1", "compile", "x", "at2")
    state = set_verify_fail(state, "t2", "compile", "x", "at3")
    assert state.failure_count == 1
    assert state.failure_task_id == "t2"


def test_reset_failure() -> None:
    """`reset_failure` clears every failure field."""
    state = with_updates(
        initial_state(),
        failure_task_id="t1",
        failure_check_name="compile",
        failure_excerpt="bad",
        failure_count=3,
    )
    fresh = reset_failure(state)
    assert fresh.failure_task_id == ""
    assert fresh.failure_count == 0


def test_advance_and_reset_position() -> None:
    """`advance_position` increments; `reset_position` zeroes."""
    state = initial_state()
    s1 = advance_position(state)
    assert s1.plan_position == 1
    s2 = advance_position(s1)
    assert s2.plan_position == 2
    assert reset_position(s2).plan_position == 0


def test_increment_rollback() -> None:
    """`increment_rollback` increments the counter."""
    assert increment_rollback(initial_state()).rollback_count == 1


def test_set_plan_frozen_resets_position() -> None:
    """Freezing resets `plan_position` and records version and hash."""
    state = with_updates(initial_state(), plan_position=3)
    fresh = set_plan_frozen(state, 2, "abcdef")
    assert fresh.plan_frozen
    assert fresh.plan_version == 2
    assert fresh.plan_sha256 == "abcdef"
    assert fresh.plan_position == 0


def test_with_updates_returns_copy() -> None:
    """`with_updates` returns a new object and leaves the original."""
    state = initial_state()
    updated = with_updates(state, plan_position=5)
    assert state.plan_position == 0
    assert updated.plan_position == 5


def test_initial_state_shape() -> None:
    """A fresh state has the documented defaults."""
    state = initial_state()
    assert state.phase_name == "unset"
    assert state.phase_kind == "unset"
    assert state.phase_status == "closed"
    assert state.plan_position == 0
    assert state.plan_frozen is False
    assert state.verify_ok is False
    assert state.failure_count == 0


def test_now_iso_has_microseconds() -> None:
    """`now_iso` uses the documented microsecond precision."""
    value = now_iso()
    assert "." in value
    fraction = value.split(".")[1].split("+")[0]
    assert len(fraction) == 6


def test_timestamp_timespec_is_microseconds() -> None:
    """The constant matches the invariant documented in the module."""
    assert TIMESTAMP_TIMESPEC == "microseconds"
