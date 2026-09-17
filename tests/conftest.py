"""Shared fixtures for the test suite.

The strategy comes from the 0.2.1 handoff: use real adapters on
`tmp_path` instead of building an in-memory filesystem. Three ports
are cheap enough to fake (clipboard, process, tokenizer); the
filesystem and git ports go through their real adapters.

`project_root` gives every test a real git repository with a first
commit. `harness_root` extends it with `.harness/config.toml` and a
fresh state. `deps` wraps a `project_root` in a `Deps` with the
three fakes wired in.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dwch.adapters.filesystem import LocalFilesystem
from dwch.adapters.git import CliGit
from dwch.adapters.process import SubprocessRunner
from dwch.application.deps import Deps
from dwch.application.state import initial_state, save_state
from tests.fakes import InMemoryClipboard, InMemoryCounter, InMemoryProcess

# Minimal config that `load_config` accepts. `verify.commands` and
# `verify.planning_commands` are empty so tests never shell out to
# ruff; a test that wants a command registers it in `InMemoryProcess`.
MINIMAL_CONFIG = """\
[harness]
version = "0.2.0"

[project]
name = "test-project"

[paths]
steps = "steps"
phases = "phases"

[context]
essential = []
references = []
architecture = ["docs/architecture.md"]
map_root = ""

[roadmap]
path = ".harness/roadmap.toml"
lock_path = ".harness/roadmap.lock"
deviations_path = ".harness/deviations"
lock_required = false

[verify]
commands = []
planning_commands = []

[bootstrap]
max_tokens = 10000
recent_reports = 1
recent_deviations = 10
include_module_map = false
truncate = true

[tokenizer]
url = "https://example.com/tokenizer.json"

[read]
max_tokens = 6000
"""


def _run_git(cwd: Path, *args: str) -> None:
    """Run a git command in `cwd`, raising on failure.

    `capture_output=True` keeps the git chatter out of the test's
    stdout; a failure still surfaces with the command's stderr in
    the traceback.
    """
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """A real git repository with a first commit.

    `core.autocrlf=false` keeps line endings stable across hosts,
    which matters for tests that compare file contents or hashes.
    """
    _run_git(tmp_path, "init", "-q")
    _run_git(tmp_path, "config", "user.email", "test@example.com")
    _run_git(tmp_path, "config", "user.name", "Test")
    _run_git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / "README.md").write_text("# project\n", encoding="utf-8")
    _run_git(tmp_path, "add", "-A")
    _run_git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


@pytest.fixture
def harness_root(project_root: Path) -> Path:
    """`project_root` with a minimal `.harness/` and a fresh state.

    Writes a config `load_config` accepts, a stub `handoff.md`, and
    a state file. Does not run `init`: no tokenizer is downloaded
    and no templates are copied, because most tests do not need
    either.
    """
    harness = project_root / ".harness"
    harness.mkdir(exist_ok=True)
    (harness / "config.toml").write_text(MINIMAL_CONFIG, encoding="utf-8")
    (harness / "handoff.md").write_text(
        "<!-- harness:begin -->\n<!-- harness:end -->\n",
        encoding="utf-8",
    )
    save_state(LocalFilesystem(), project_root, initial_state())
    return project_root


@pytest.fixture
def deps(project_root: Path) -> Deps:
    """`Deps` with real fs and git, fakes for clipboard/process/counter.

    `CliGit` always gets a real subprocess runner: git operations
    must be exercised for real. `deps.process` is the fake, so
    configured verify commands do not shell out.
    """
    return Deps(
        fs=LocalFilesystem(),
        clipboard=InMemoryClipboard(),
        process=InMemoryProcess(),
        git=CliGit(SubprocessRunner()),
        counter=InMemoryCounter(),
        project_root=project_root,
    )
