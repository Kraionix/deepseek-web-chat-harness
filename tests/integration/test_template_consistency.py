"""Tests that the renderers produce parseable files of the right shape."""

from __future__ import annotations

import tomllib

from dwch.application.config import config_to_toml
from dwch.application.state import _render_state, initial_state


def test_render_state_parses() -> None:
    """`_render_state(initial_state())` is valid TOML."""
    data = tomllib.loads(_render_state(initial_state()))
    assert data["phase"]["current"] == "unset"
    assert data["phase"]["kind"] == "unset"
    assert data["roadmap"]["frozen"] is False


def test_render_state_has_expected_sections() -> None:
    """The rendered state has every documented section, including summary."""
    data = tomllib.loads(_render_state(initial_state()))
    for section in (
        "harness",
        "phase",
        "step",
        "roadmap",
        "rollback",
        "session",
        "summary",
    ):
        assert section in data


def test_render_state_summary_is_empty_on_init() -> None:
    """A fresh state renders an empty `[summary]` section."""
    data = tomllib.loads(_render_state(initial_state()))
    assert data["summary"]["phase"] == ""
    assert data["summary"]["written_at"] == ""


def test_config_to_toml_parses() -> None:
    """`config_to_toml` output parses as TOML with the expected shape."""
    data = tomllib.loads(config_to_toml("demo"))
    assert data["harness"]["version"] == "0.3.0"
    assert data["project"]["name"] == "demo"
    assert data["paths"]["steps"] == "steps"
    assert data["roadmap"]["path"] == ".harness/roadmap.toml"
    assert data["bootstrap"]["reports_current_phase"] == 1


def test_config_to_toml_has_no_phases_key() -> None:
    """`paths.phases` is gone."""
    data = tomllib.loads(config_to_toml("demo"))
    assert "phases" not in data["paths"]


def test_state_written_by_save_matches_render(tmp_path) -> None:
    """The state file on disk is exactly what `_render_state` produces."""
    from dwch.adapters.filesystem import LocalFilesystem
    from dwch.application.state import save_state

    (tmp_path / ".harness").mkdir()
    state = initial_state()
    save_state(LocalFilesystem(), tmp_path, state)
    on_disk = (tmp_path / ".harness" / "state.toml").read_text(encoding="utf-8")
    assert on_disk == _render_state(state)
