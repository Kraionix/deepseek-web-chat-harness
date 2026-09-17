"""Fakes for ports that are cheap to replace in tests.

Only three ports get fakes: clipboard, process, and tokenizer. The
filesystem and git ports are used through their real adapters on
`tmp_path`, because the tests need real file I/O and real git
semantics (`rollback` uses `git reset --hard`).

`RenameFails` subclasses `LocalFilesystem` rather than implementing
the port from scratch: it exercises the real adapter and only
overrides the one method that must fail for the atomicity test.
"""

from __future__ import annotations

from pathlib import Path

from dwch.adapters.filesystem import LocalFilesystem
from dwch.domain.models import ProcessResult
from dwch.shared.errors import FilesystemError


class InMemoryClipboard:
    """Clipboard whose contents live in an attribute.

    `text` starts empty. `read()` returns it; `write()` stores the
    argument and returns True. Tests set `clipboard.text = "..."`.
    """

    def __init__(self) -> None:
        self.text = ""

    def read(self) -> str:
        """Return the stored text."""
        return self.text

    def write(self, text: str) -> bool:
        """Store `text` and report success."""
        self.text = text
        return True


class InMemoryProcess:
    """Process runner that returns canned results keyed by command.

    An unknown command returns exit code 127 with a short stderr
    message, so a test that forgets to register a command sees a
    clear failure instead of an exception.
    """

    def __init__(self) -> None:
        self._results: dict[tuple[str, ...], ProcessResult] = {}

    def add(self, cmd: list[str], result: ProcessResult) -> None:
        """Register a canned result for `cmd`."""
        self._results[tuple(cmd)] = result

    def run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        timeout: float = 60.0,
    ) -> ProcessResult:
        """Return the registered result, or an in-memory 127."""
        key = tuple(cmd)
        if key in self._results:
            return self._results[key]
        return ProcessResult(
            exit_code=127,
            stdout="",
            stderr=f"in-memory: no result for {key!r}",
        )


class InMemoryCounter:
    """Tokenizer stand-in that counts characters, not BPE tokens.

    Exact token counts do not matter for behaviour tests; ordering
    and relative sizes do. Using `len` keeps the fake deterministic
    and fast, and it never needs a tokenizer file on disk.
    """

    def count(self, text: str) -> int:
        """Return the character length of `text`."""
        return len(text)

    def count_batch(self, texts: list[str]) -> list[int]:
        """Return character lengths, one per input."""
        return [len(t) for t in texts]


class RenameFails(LocalFilesystem):
    """`LocalFilesystem` whose `rename` always raises.

    Used to prove that `save_state` writes a temp file and only then
    renames: if the rename fails, the original file must be
    unchanged.
    """

    def rename(self, src: Path, dst: Path) -> None:
        """Refuse every rename, with a message naming both paths."""
        raise FilesystemError(f"rename disabled for test: {src} -> {dst}")


__all__ = [
    "InMemoryClipboard",
    "InMemoryCounter",
    "InMemoryProcess",
    "RenameFails",
]
