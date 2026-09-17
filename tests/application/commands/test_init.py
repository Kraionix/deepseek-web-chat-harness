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
    """`init` creates `.harness/`, `steps/`, and the shipped templates."""
    assert cmd_init(_args(), deps) == 0
    assert (project_root / ".harness" / "config.toml").is_file()
    assert (project_root / ".harness" / "state.toml").is_file()
    assert (project_root / ".harness" / ".gitignore").is_file()
    assert (project_root / ".harness" / "session-protocol.md").is_file()
    assert (project_root / "steps" / ".gitignore").is_file()
    assert (project_root / ".harness" / "data" / "deepseek_tokenizer.json").is_file()


def test_init_refuses_existing(project_root: Path, deps, fake_urlopen) -> None:
    """A second `init` without `--force` is refused."""
    assert cmd_init(_args(), deps) == 0
    assert cmd_init(_args(), deps) == 2


def test_init_force_overwrites(project_root: Path, deps, fake_urlopen) -> None:
    """`--force` re-runs `init` over an existing harness."""
    assert cmd_init(_args(), deps) == 0
    assert cmd_init(_args(force=True), deps) == 0
