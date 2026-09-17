"""Git adapter backed by the `git` CLI.

Every method that can fail raises `GitError` with the command's
stderr. Reads that are expected to succeed on a well-formed
repository (branch, rev-parse) also raise on failure, because a
failure there indicates a broken environment rather than a routine
condition.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from ..shared.errors import GitError, ProcessError
from .process import SubprocessRunner


class CliGit:
    """`GitPort` implementation over the git command-line client."""

    def __init__(self, runner: SubprocessRunner) -> None:
        self._runner = runner

    def _run(self, cwd: Path, *args: str) -> str:
        try:
            result = self._runner.run(["git", *args], cwd=cwd, timeout=60.0)
        except ProcessError as exc:
            raise GitError(str(exc)) from exc
        if result.exit_code != 0:
            message = (result.stderr or result.stdout).strip()
            raise GitError(f"git {' '.join(args)}: {message}")
        return result.stdout

    def is_clean(self, cwd: Path) -> bool:
        try:
            out = self._run(cwd, "status", "--porcelain")
        except GitError:
            return False
        return not out.strip()

    def status_short(self, cwd: Path) -> list[str]:
        out = self._run(cwd, "status", "--short")
        return [line for line in out.splitlines() if line.strip()]

    def current_branch(self, cwd: Path) -> str:
        return self._run(cwd, "rev-parse", "--abbrev-ref", "HEAD").strip()

    def rev_parse(self, cwd: Path, ref: str) -> str:
        return self._run(cwd, "rev-parse", "--short", ref).strip()

    def commit_all(self, cwd: Path, message: str) -> str:
        self._run(cwd, "add", "-A")
        self._run(cwd, "commit", "-m", message)
        return self.rev_parse(cwd, "HEAD")

    def reset_hard(self, cwd: Path, ref: str) -> None:
        self._run(cwd, "reset", "--hard", ref)

    def tag(self, cwd: Path, name: str, message: str) -> None:
        self._run(cwd, "tag", "-a", name, "-m", message)

    def log_oneline(self, cwd: Path, n: int) -> list[str]:
        out = self._run(cwd, "log", f"-{n}", "--oneline")
        return [line for line in out.splitlines() if line.strip()]

    def checkout_paths(self, cwd: Path, ref: str, paths: list[str]) -> None:
        if not paths:
            return
        # Best-effort rollback: paths that did not exist in `ref`
        # cannot be restored by checkout, and that is not an error
        # the caller needs to see.
        with contextlib.suppress(GitError):
            self._run(cwd, "checkout", ref, "--", *paths)


__all__ = ["CliGit"]
