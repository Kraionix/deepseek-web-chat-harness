"""Port protocols for external world access.

Every external dependency of the harness is expressed as a
`Protocol` here. Adapters in `dwch.adapters` implement these
protocols structurally — no inheritance required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..domain.models import ProcessResult


class FilesystemPort(Protocol):
    """Filesystem access.

    All paths are `pathlib.Path` instances. Reads and writes are
    UTF-8 by default; binary operations use `read_bytes` /
    `write_bytes`.
    """

    def read_text(self, path: Path) -> str: ...
    def write_text(self, path: Path, text: str) -> None: ...
    def read_bytes(self, path: Path) -> bytes: ...
    def write_bytes(self, path: Path, data: bytes) -> None: ...
    def exists(self, path: Path) -> bool: ...
    def is_dir(self, path: Path) -> bool: ...
    def is_file(self, path: Path) -> bool: ...
    def mkdir(self, path: Path, *, parents: bool = False) -> None: ...
    def glob(self, root: Path, pattern: str) -> list[Path]: ...
    def listdir(self, path: Path) -> list[Path]: ...
    def unlink(self, path: Path) -> None: ...

    def rename(self, src: Path, dst: Path) -> None:
        """Atomically move `src` to `dst`, replacing `dst` if present.

        Implementations must use an OS-level atomic rename (POSIX
        `rename(2)` or Windows `MoveFileEx` with replace). Used by
        `save_state` so a crash mid-write leaves the destination
        either fully old or fully new, never partial.
        """
        ...


class ClipboardPort(Protocol):
    """System clipboard access.

    `read()` returns empty string when the clipboard is empty or
    unsupported. `write()` returns True on success and False when
    the clipboard is unavailable; the caller decides whether that is
    fatal.
    """

    def read(self) -> str: ...
    def write(self, text: str) -> bool: ...


class ProcessPort(Protocol):
    """Subprocess execution.

    Runs a command in the given working directory, with a timeout,
    capturing stdout and stderr. Raises `ProcessError` on a start
    failure or timeout; returns a result for any exit code.
    """

    def run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        timeout: float = 60.0,
    ) -> ProcessResult: ...


class GitPort(Protocol):
    """Git operations needed by the harness.

    All methods take an explicit working directory. Methods that
    would fail on a non-zero git exit raise `GitError` with the
    command's stderr.
    """

    def is_clean(self, cwd: Path) -> bool:
        """True when `git status --porcelain` is empty.

        Untracked files count as dirty. Use this before operations
        that assume a known working tree and will not sweep the tree
        into a commit (notably `rollback`). For operations that
        commit everything anyway, use `is_clean_tracked`.
        """
        ...

    def is_clean_tracked(self, cwd: Path) -> bool:
        """True when no tracked file is modified or deleted.

        Untracked files do not count. Use this for bookkeeping
        transitions (`new-phase`, `close`) that will commit the
        whole tree via `commit_all`: untracked files are expected
        to be swept in, so their presence is not an error.
        """
        ...

    def status_short(self, cwd: Path) -> list[str]:
        """Return `git status --short` output as a list of lines.

        Each non-empty line has the form `XY path`, where `X` is
        the index status and `Y` is the worktree status. Untracked
        files begin with `??`. An empty list means the tree is
        clean.
        """
        ...

    def current_branch(self, cwd: Path) -> str: ...
    def rev_parse(self, cwd: Path, ref: str) -> str: ...

    def try_head(self, cwd: Path) -> str:
        """Return the short hash of HEAD, or "" on failure.

        A repository with no commits is not an error for this
        method: it returns an empty string. Callers that need a
        commit hash unconditionally call `rev_parse` instead.
        """
        ...

    def commit_all(self, cwd: Path, message: str) -> str: ...
    def reset_hard(self, cwd: Path, ref: str) -> None: ...
    def tag(self, cwd: Path, name: str, message: str) -> None: ...
    def log_oneline(self, cwd: Path, n: int) -> list[str]: ...
    def checkout_paths(self, cwd: Path, ref: str, paths: list[str]) -> None: ...


class TokenCounterPort(Protocol):
    """Token counting for accurate context sizing.

    Uses the real DeepSeek BPE tokenizer. `count_batch` may run in
    parallel internally; the caller does not need to thread.
    """

    def count(self, text: str) -> int: ...
    def count_batch(self, texts: list[str]) -> list[int]: ...


__all__ = [
    "ClipboardPort",
    "FilesystemPort",
    "GitPort",
    "ProcessPort",
    "TokenCounterPort",
]
