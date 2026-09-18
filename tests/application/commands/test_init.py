"""Tests for `application.commands.init`."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from dwch.application.commands.init import cmd_init


class _FakeResponse:
    """Minimal stand-in for the object returned by `urlopen`."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        """Return the canned body."""
        return self._data

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args) -> None:
        return None


@pytest.fixture
def fake_urlopen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace `urllib.request.urlopen` with a fake tokenizer blob."""
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _FakeResponse(b'{"fake": true}'),
    )


def _args(force: bool = False) -> Namespace:
    """Minimal namespace for `cmd_init`."""
    return Namespace(force=force)


def test_init_creates_layout(project_root: Path, deps, fake_urlopen) -> None:
    """`init` creates `.harness/`, `steps/`, and `contract.md`."""
    assert cmd_init(_args(), deps) == 0
    assert (project_root / ".harness" / "config.toml").is_file()
    assert (project_root / ".harness" / "state.toml").is_file()
    assert (project_root / ".harness" / "contract.md").is_file()
    assert (project_root / "steps" / ".gitignore").is_file()


def test_init_copies_only_contract(project_root: Path, deps, fake_urlopen) -> None:
    """Only `contract.md` is shipped as a template."""
    assert cmd_init(_args(), deps) == 0
    harness = project_root / ".harness"
    assert (harness / "contract.md").is_file()
    assert not (harness / "session-protocol.md").exists()
    assert not (harness / "toolbox.md").exists()
    assert not (harness / "step-format.md").exists()


def test_init_refuses_existing(project_root: Path, deps, fake_urlopen) -> None:
    """A second `init` without `--force` is refused."""
    assert cmd_init(_args(), deps) == 0
    assert cmd_init(_args(), deps) == 2


def test_init_force_overwrites_config(project_root: Path, deps, fake_urlopen) -> None:
    """`--force` regenerates a config that the user broke."""
    assert cmd_init(_args(), deps) == 0
    cfg = project_root / ".harness" / "config.toml"
    cfg.write_text('[harness]\nversion = "9.9.9"\n', encoding="utf-8")
    assert cmd_init(_args(force=True), deps) == 0
    assert 'version = "0.4.0"' in cfg.read_text(encoding="utf-8")


def test_init_keeps_state_on_force(project_root: Path, deps, fake_urlopen) -> None:
    """`--force` does not overwrite `state.toml`."""
    assert cmd_init(_args(), deps) == 0
    state = project_root / ".harness" / "state.toml"
    state.write_text("user data\n", encoding="utf-8")
    assert cmd_init(_args(force=True), deps) == 0
    assert state.read_text(encoding="utf-8") == "user data\n"


def test_init_force_overwrites_contract(project_root: Path, deps, fake_urlopen) -> None:
    """`--force` regenerates the shipped contract."""
    assert cmd_init(_args(), deps) == 0
    contract = project_root / ".harness" / "contract.md"
    contract.write_text("user edited\n", encoding="utf-8")
    assert cmd_init(_args(force=True), deps) == 0
    body = contract.read_text(encoding="utf-8")
    assert "user edited" not in body
    assert "Harness contract" in body
