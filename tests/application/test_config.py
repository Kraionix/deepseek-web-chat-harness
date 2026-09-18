"""Tests for `application.config`."""

from __future__ import annotations

from pathlib import Path

import pytest

from dwch.adapters.filesystem import LocalFilesystem
from dwch.application.config import config_to_toml, load_config
from dwch.shared.errors import ConfigError


def _write(root: Path, body: str) -> None:
    """Write `.harness/config.toml` under `root`."""
    harness = root / ".harness"
    harness.mkdir(parents=True, exist_ok=True)
    (harness / "config.toml").write_text(body, encoding="utf-8")


def test_default_config_loads(tmp_path: Path) -> None:
    """`config_to_toml` output loads unchanged."""
    _write(tmp_path, config_to_toml("p"))
    cfg = load_config(LocalFilesystem(), tmp_path)
    assert cfg.project_name == "p"
    assert cfg.harness_version == "0.4.0"
    assert cfg.paths["steps"] == "steps"
    assert cfg.plan["path"] == ".harness/plan.toml"
    assert cfg.notes_path == ".harness/notes.md"


def test_config_format_version_is_0_4_0(tmp_path: Path) -> None:
    """The rendered config carries the 0.4.0 format version."""
    _write(tmp_path, config_to_toml("p"))
    cfg = load_config(LocalFilesystem(), tmp_path)
    assert cfg.harness_version == "0.4.0"


def test_default_config_has_no_roadmap_section(tmp_path: Path) -> None:
    """`[roadmap]` is gone; `[plan]` replaces it."""
    body = config_to_toml("p")
    assert "[roadmap]" not in body
    assert "[plan]" in body


def test_default_config_has_notes(tmp_path: Path) -> None:
    """`[context].notes` is present with the documented default."""
    _write(tmp_path, config_to_toml("p"))
    cfg = load_config(LocalFilesystem(), tmp_path)
    assert cfg.context["notes"] == ".harness/notes.md"


def test_bootstrap_max_tokens_is_5000(tmp_path: Path) -> None:
    """The default `max_tokens` dropped to 5000."""
    _write(tmp_path, config_to_toml("p"))
    cfg = load_config(LocalFilesystem(), tmp_path)
    assert cfg.bootstrap["max_tokens"] == 5000


def test_missing_config(tmp_path: Path) -> None:
    """A missing config file raises `ConfigError`."""
    with pytest.raises(ConfigError, match="config not found"):
        load_config(LocalFilesystem(), tmp_path)


def test_invalid_toml(tmp_path: Path) -> None:
    """Malformed TOML raises `ConfigError`."""
    _write(tmp_path, "not = ")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(LocalFilesystem(), tmp_path)


def test_version_mismatch(tmp_path: Path) -> None:
    """A config with a different format version is rejected."""
    body = config_to_toml("p").replace('version = "0.4.0"', 'version = "9.9.9"')
    _write(tmp_path, body)
    with pytest.raises(ConfigError, match="does not match"):
        load_config(LocalFilesystem(), tmp_path)


def test_path_value_not_a_string(tmp_path: Path) -> None:
    """A non-string path value is a `ConfigError`, not a `TypeError`."""
    body = config_to_toml("p").replace('steps = "steps"', "steps = 5")
    _write(tmp_path, body)
    with pytest.raises(ConfigError, match="paths.steps: expected a string"):
        load_config(LocalFilesystem(), tmp_path)


def test_path_is_absolute(tmp_path: Path) -> None:
    """An absolute path is rejected."""
    body = config_to_toml("p").replace('steps = "steps"', 'steps = "/abs"')
    _write(tmp_path, body)
    with pytest.raises(ConfigError, match="absolute path"):
        load_config(LocalFilesystem(), tmp_path)


def test_path_has_parent_traversal(tmp_path: Path) -> None:
    """A `..` path is rejected."""
    body = config_to_toml("p").replace('steps = "steps"', 'steps = "../x"')
    _write(tmp_path, body)
    with pytest.raises(ConfigError, match="parent traversal"):
        load_config(LocalFilesystem(), tmp_path)


def test_notes_path_is_validated(tmp_path: Path) -> None:
    """An absolute `context.notes` is rejected."""
    body = config_to_toml("p").replace(
        'notes = ".harness/notes.md"', 'notes = "/abs/notes.md"'
    )
    _write(tmp_path, body)
    with pytest.raises(ConfigError, match="context.notes"):
        load_config(LocalFilesystem(), tmp_path)


def test_plan_path_is_validated(tmp_path: Path) -> None:
    """An absolute `plan.path` is rejected."""
    body = config_to_toml("p").replace(
        'path = ".harness/plan.toml"', 'path = "/abs/plan.toml"'
    )
    _write(tmp_path, body)
    with pytest.raises(ConfigError, match="plan.path"):
        load_config(LocalFilesystem(), tmp_path)


def test_command_must_be_a_list(tmp_path: Path) -> None:
    """A string command is rejected at load time."""
    body = config_to_toml("p").replace(
        '{ name = "lint", command = ["ruff", "check", "."] }',
        '{ name = "lint", command = "ruff check" }',
    )
    _write(tmp_path, body)
    with pytest.raises(ConfigError, match="expected a list"):
        load_config(LocalFilesystem(), tmp_path)


def test_planning_command_must_be_a_list(tmp_path: Path) -> None:
    """A string in `planning_commands` is rejected."""
    body = config_to_toml("p").replace(
        "planning_commands = []",
        'planning_commands = [{ name = "x", command = "y" }]',
    )
    _write(tmp_path, body)
    with pytest.raises(ConfigError, match="expected a list"):
        load_config(LocalFilesystem(), tmp_path)
