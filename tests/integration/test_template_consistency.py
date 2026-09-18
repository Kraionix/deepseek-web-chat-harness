"""Tests that the renderers produce parseable files of the right shape.

A regression test asserts that every field of `Task`, `Plan`,
`Deviation`, and `State` appears in `contract.md`.
"""

from __future__ import annotations

import dataclasses
import tomllib
from importlib.resources import files

import pytest

from dwch.application.config import config_to_toml
from dwch.application.state import _render_state, initial_state
from dwch.domain.models import (
    Deviation,
    Plan,
    State,
    Task,
)


def test_render_state_parses() -> None:
    """`_render_state(initial_state())` is valid TOML."""
    data = tomllib.loads(_render_state(initial_state()))
    assert data["phase"]["name"] == "unset"
    assert data["phase"]["kind"] == "unset"
    assert data["phase"]["status"] == "closed"
    assert data["plan"]["frozen"] is False


def test_render_state_has_expected_sections() -> None:
    """The rendered state has every documented section."""
    data = tomllib.loads(_render_state(initial_state()))
    for section in (
        "harness",
        "phase",
        "plan",
        "verify",
        "failure",
        "rollback",
        "session",
    ):
        assert section in data


def test_config_to_toml_parses() -> None:
    """`config_to_toml` output parses as TOML with the expected shape."""
    data = tomllib.loads(config_to_toml("demo"))
    assert data["harness"]["version"] == "0.4.0"
    assert data["project"]["name"] == "demo"
    assert data["plan"]["path"] == ".harness/plan.toml"
    assert data["context"]["notes"] == ".harness/notes.md"
    assert data["bootstrap"]["max_tokens"] == 5000


def test_state_written_by_save_matches_render(tmp_path) -> None:
    """The state file on disk is exactly what `_render_state` produces."""
    from dwch.adapters.filesystem import LocalFilesystem
    from dwch.application.state import save_state

    (tmp_path / ".harness").mkdir()
    state = initial_state()
    save_state(LocalFilesystem(), tmp_path, state)
    on_disk = (tmp_path / ".harness" / "state.toml").read_text(encoding="utf-8")
    assert on_disk == _render_state(state)


def _contract_text() -> str:
    """Return the shipped `contract.md`."""
    return (files("dwch.templates") / "contract.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "cls",
    [Task, Plan, Deviation, State],
    ids=["Task", "Plan", "Deviation", "State"],
)
def test_contract_covers_every_field(cls) -> None:
    """Every dataclass field name appears in `contract.md`."""
    contract = _contract_text()
    missing: list[str] = []
    for field in dataclasses.fields(cls):
        if field.name not in contract:
            missing.append(field.name)
    assert not missing, f"{cls.__name__} fields missing from contract.md: {missing}"
