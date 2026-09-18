"""Shared fixtures for the test suite.

The strategy comes from the 0.2.1 handoff: use real adapters on
`tmp_path` instead of building an in-memory filesystem. Three ports
are cheap enough to fake (clipboard, process, tokenizer); the
filesystem and git ports go through their real adapters.

Speed comes from three choices, all introduced in 0.3.2:

- Git identity is set through environment variables at conftest
  import time, so no test pays for `git config user.email`.
- A session-scoped template repository is created once and
  `copytree`-d into each test's `tmp_path`, replacing the six
  subprocesses (`init`, three `config`, `add`, `commit`) that used
  to run per test.
- `core.autocrlf=false` is applied through `GIT_CONFIG_*` rather
  than written to each repository.

`broken_deps` is `deps` with a git port whose `commit_all` always
raises: used by tests that assert a lifecycle command restores
state when the commit fails.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
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
    """Add one `git -c` style setting to the inherited environment.

    `GIT_CONFIG_COUNT` + `GIT_CONFIG_KEY_<n>` + `GIT_CONFIG_VALUE_<n>`
    is the mechanism git 2.31 and later use to read config from the
    environment. Appending rather than overwriting respects any
    `GIT_CONFIG_*` the user already exported.
    """
    count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    os.environ["GIT_CONFIG_COUNT"] = str(count + 1)
    os.environ[f"GIT_CONFIG_KEY_{count}"] = key
    os.environ[f"GIT_CONFIG_VALUE_{count}"] = value


def _configure_git_env() -> None:
    """Configure git for the whole test session via environment.

    Runs once, at conftest import. Every `subprocess.run(["git", ...])`
    the tests spawn inherits these, so no test calls `git config`.
    `setdefault` leaves a user's own identity alone when they run the
    suite locally.
    """
    os.environ.setdefault("GIT_AUTHOR_NAME", "Test")
    os.environ.setdefault("GIT_AUTHOR_EMAIL", "test@example.com")
    os.environ.setdefault("GIT_COMMITTER_NAME", "Test")
    os.environ.setdefault("GIT_COMMITTER_EMAIL", "test@example.com")
    # Line endings must be stable across hosts: the suite compares
    # file contents and hashes.
    _append_git_config("core.autocrlf", "false")


_configure_git_env()


# Minimal config that `load_config` accepts. `verify.commands` and
# `verify.planning_commands` are empty so tests never shell out to
# ruff; a test that wants a command registers it in `InMemoryProcess`.
#
# The 0.3.0 format replaces `bootstrap.recent_reports` with
# `bootstrap.reports_current_phase`. 0.3.1 removes `paths.phases`.
MINIMAL_CONFIG = """\
[harness]
version = "0.3.0"

[project]
name = "test-project"

[paths]
steps = "steps"

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
    """Run a git command in `cwd`, raising on failure.

    `capture_output=True` keeps the git chatter out of the test's
    stdout; a failure still surfaces with the command's stderr in
    the traceback. Identity and `core.autocrlf` come from the
    environment, not from the repository.
    """
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def _git_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A git repository with one commit, built once per session.

    `project_root` copies this directory into each test's
    `tmp_path`. Four subprocesses per session replace six per test;
    the per-test cost drops to a `shutil.copytree`.
    """
    root = tmp_path_factory.mktemp("git-template")
    _run_git(root, "init", "-q")
    (root / "README.md").write_text("# project\n", encoding="utf-8")
    _run_git(root, "add", "-A")
    _run_git(root, "commit", "-q", "-m", "init")
    return root


def _make_writable(root: Path) -> None:
    """Clear read-only bits left by `copytree`.

    Git creates loose objects as read-only on POSIX. On Windows,
    `shutil.copytree` preserves that bit, and a later `git add` or
    `git reset` may refuse to touch the copy. Clearing the bit is
    cheap and keeps the tests portable.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            with contextlib.suppress(OSError):
                os.chmod(os.path.join(dirpath, name), 0o755)
        for name in filenames:
            with contextlib.suppress(OSError):
                os.chmod(os.path.join(dirpath, name), 0o644)


@pytest.fixture
def project_root(tmp_path: Path, _git_template: Path) -> Path:
    """A real git repository with a first commit.

    Copies the session-scoped template into `tmp_path / "repo"`.
    The subdirectory keeps the path short on Windows and leaves
    `tmp_path` free for tests that want to create sibling
    directories (`test_health` does).
    """
    dest = tmp_path / "repo"
    shutil.copytree(_git_template, dest)
    _make_writable(dest)
    return dest


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


@pytest.fixture
def broken_deps(deps: Deps) -> Deps:
    """`deps` with a git port whose `commit_all` always raises.

    Every other method is the real implementation: reads
    (`is_clean`, `status_short`, `try_head`, `last_commit_subject`)
    behave as they do in production. Only the write that the
    lifecycle commands perform is broken.
    """
    return Deps(
        fs=deps.fs,
        clipboard=deps.clipboard,
        process=deps.process,
        git=CommitFails(SubprocessRunner()),
        counter=deps.counter,
        project_root=deps.project_root,
    )
