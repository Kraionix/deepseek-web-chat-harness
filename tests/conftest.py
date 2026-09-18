"""Shared fixtures for the test suite.

Real adapters on `tmp_path` for filesystem and git; small fakes for
clipboard, process, and tokenizer. Git identity and `core.autocrlf`
come from environment variables set at conftest import time, and a
session-scoped template repository is `copytree`-d into each test,
so no test pays for `git init` or `git config`.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

from dwch.adapters.filesystem import LocalFilesystem
from dwch.adapters.git import CliGit
from dwch.adapters.process import SubprocessRunner
from dwch.application.deps import Deps
from dwch.application.state import initial_state, save_state
from tests.fakes import (
    CommitFails,
    InMemoryClipboard,
    InMemoryCounter,
    InMemoryProcess,
)


def _append_git_config(key: str, value: str) -> None:
    """Add one `git -c` style setting to the inherited environment."""
    count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    os.environ["GIT_CONFIG_COUNT"] = str(count + 1)
    os.environ[f"GIT_CONFIG_KEY_{count}"] = key
    os.environ[f"GIT_CONFIG_VALUE_{count}"] = value


def _configure_git_env() -> None:
    """Configure git for the whole test session via environment."""
    os.environ.setdefault("GIT_AUTHOR_NAME", "Test")
    os.environ.setdefault("GIT_AUTHOR_EMAIL", "test@example.com")
    os.environ.setdefault("GIT_COMMITTER_NAME", "Test")
    os.environ.setdefault("GIT_COMMITTER_EMAIL", "test@example.com")
    _append_git_config("core.autocrlf", "false")


_configure_git_env()


# Minimal config that `load_config` accepts. `verify.commands` and
# `verify.planning_commands` are empty so tests never shell out to
# ruff; a test that wants a command registers it in
# `InMemoryProcess`. `bootstrap.max_tokens` is huge so a full
# bootstrap fits without truncation; tests that exercise truncation
# override it.
MINIMAL_CONFIG = """\
[harness]
version = "0.4.0"

[project]
name = "test-project"

[paths]
steps = "steps"

[context]
essential = []
references = []
architecture = ["docs/architecture.md"]
map_root = ""
notes = ".harness/notes.md"

[plan]
path = ".harness/plan.toml"
deviations_path = ".harness/deviations"

[verify]
commands = []
planning_commands = []

[bootstrap]
max_tokens = 50000
reports_current_phase = 1
recent_deviations = 10
include_module_map = false
truncate = true

[tokenizer]
url = "https://example.com/tokenizer.json"

[read]
max_tokens = 6000
"""


def _run_git(cwd: Path, *args: str) -> None:
    """Run a git command in `cwd`, raising on failure."""
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture(scope="session")
def _git_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A git repository with one commit, built once per session."""
    root = tmp_path_factory.mktemp("git-template")
    _run_git(root, "init", "-q")
    (root / "README.md").write_text("# project\n", encoding="utf-8")
    _run_git(root, "add", "-A")
    _run_git(root, "commit", "-q", "-m", "init")
    return root


def _make_writable(root: Path) -> None:
    """Clear read-only bits left by `copytree`."""
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            with contextlib.suppress(OSError):
                os.chmod(os.path.join(dirpath, name), 0o755)
        for name in filenames:
            with contextlib.suppress(OSError):
                os.chmod(os.path.join(dirpath, name), 0o644)


@pytest.fixture
def project_root(tmp_path: Path, _git_template: Path) -> Path:
    """A real git repository with a first commit."""
    dest = tmp_path / "repo"
    shutil.copytree(_git_template, dest)
    _make_writable(dest)
    return dest


@pytest.fixture
def harness_root(project_root: Path) -> Path:
    """`project_root` with a minimal `.harness/` and a fresh state.

    Writes a config `load_config` accepts, the real `contract.md`
    from the package, and a state file. Does not run `init`: no
    tokenizer is downloaded.
    """
    harness = project_root / ".harness"
    harness.mkdir(exist_ok=True)
    (harness / "config.toml").write_text(MINIMAL_CONFIG, encoding="utf-8")
    contract = files("dwch.templates") / "contract.md"
    (harness / "contract.md").write_text(
        contract.read_text(encoding="utf-8"), encoding="utf-8"
    )
    save_state(LocalFilesystem(), project_root, initial_state())
    return project_root


@pytest.fixture
def deps(project_root: Path) -> Deps:
    """`Deps` with real fs and git, fakes for clipboard/process/counter."""
    return Deps(
        fs=LocalFilesystem(),
        clipboard=InMemoryClipboard(),
        process=InMemoryProcess(),
        git=CliGit(SubprocessRunner()),
        counter=InMemoryCounter(),
        project_root=project_root,
    )


@pytest.fixture
def broken_deps(deps: Deps) -> Deps:
    """`deps` with a git port whose `commit_all` always raises."""
    return Deps(
        fs=deps.fs,
        clipboard=deps.clipboard,
        process=deps.process,
        git=CommitFails(SubprocessRunner()),
        counter=deps.counter,
        project_root=deps.project_root,
    )
