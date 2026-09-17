"""Dependency bundle passed to every command.

Commands never construct adapters themselves. The CLI builds one
`Deps` and passes it to the chosen command. This keeps the
adapters' concrete classes out of `application/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ports import (
    ClipboardPort,
    FilesystemPort,
    GitPort,
    ProcessPort,
    TokenCounterPort,
)


@dataclass(frozen=True, slots=True)
class Deps:
    """Container for the five ports plus the project root.

    `project_root` is the absolute path of the consuming project.
    All commands treat it as their working directory root.
    """

    fs: FilesystemPort
    clipboard: ClipboardPort
    process: ProcessPort
    git: GitPort
    counter: TokenCounterPort
    project_root: Path


__all__ = ["Deps"]
