"""Tests for `application.state`."""

from __future__ import annotations

from pathlib import Path

import pytest

from dwch.adapters.filesystem import LocalFilesystem
from dwch.application.state import (
    initial_state,
    load_state,
    save_state,
    set_roadmap_frozen,
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


def test_save_is_atomic(tmp_path: Path) -> None:
    """A failing rename leaves the original state file unchanged."""
    root = _harness(tmp_path)
    fs = LocalFilesystem()
    save_state(fs, root, initial_state())
    original = (root / ".harness" / "state.toml").read_text(encoding="utf-8")

    broken = RenameFails()
    new_state = with_updates(initial_state(), current_phase="new-phase")
    with pytest.raises(FilesystemError):
        save_state(broken, root, new_state)

    after = (root / ".harness" / "state.toml").read_text(encoding="utf-8")
    assert after == original


def test_set_roadmap_frozen_resets_step(tmp_path: Path) -> None:
    """Freezing resets `roadmap_step` and records the version."""
    root = _harness(tmp_path)
    fs = LocalFilesystem()
    state = with_updates(initial_state(), roadmap_step=3)
    save_state(fs, root, state)

    updated = set_roadmap_frozen(fs, root, state, version=2)
    assert updated.roadmap_frozen
    assert updated.roadmap_version == 2
    assert updated.roadmap_step == 0

    assert load_state(fs, root) == updated


def test_with_updates_returns_copy() -> None:
    """`with_updates` returns a new object and leaves the original."""
    state = initial_state()
    updated = with_updates(state, current_step=5)
    assert state.current_step == 0
    assert updated.current_step == 5


def test_initial_state_shape() -> None:
    """A fresh state has the documented defaults."""
    state = initial_state()
    assert state.current_phase == "unset"
    assert state.phase_kind == "unset"
    assert state.current_step == 0
    assert state.roadmap_frozen is False
