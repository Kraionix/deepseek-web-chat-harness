"""Write, read, and check `.harness/roadmap.lock`.

The lock records the freeze: at `close --freeze` the harness writes
a TOML file with the SHA-256 of the roadmap and every architecture
document. In development, `verify` compares the current hashes
against the lock and reports any drift as a non-required check.

All paths inside the lock are stored relative to the project root,
using forward slashes, so the file is portable across machines and
platforms.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from ..domain.models import Lock, LockEntry
from ..shared.errors import LockError
from ..shared.toml import escape_basic_string
from .ports import FilesystemPort
from .roadmap import sha256


def write(
    fs: FilesystemPort,
    lock_path: Path,
    project_root: Path,
    roadmap_path: Path,
    architecture_paths: list[Path],
    *,
    at: str,
    phase: str,
    commit: str,
    version: int,
) -> Lock:
    """Compute hashes and write a lock file.

    Pre:  `roadmap_path` and every path in `architecture_paths` are
          absolute and live under `project_root`.
    Post: `lock_path` is written with relative paths and computed
          hashes.
    Raises: `LockError` if an architecture path is outside
          `project_root`; `FilesystemError` if a hash cannot be
          computed.
    """
    entries = tuple(
        LockEntry(
            path=_relative(p, project_root),
            sha256=sha256(fs, p),
        )
        for p in architecture_paths
    )
    lock = Lock(
        at=at,
        phase=phase,
        commit=commit,
        version=version,
        roadmap_sha256=sha256(fs, roadmap_path),
        architecture=entries,
    )
    fs.write_text(lock_path, render(lock))
    return lock


def load(fs: FilesystemPort, path: Path) -> Lock | None:
    """Return the parsed lock at `path`, or None if it does not exist.

    Raises: `LockError` if the file exists but is malformed.
    """
    if not fs.exists(path):
        return None
    try:
        data = tomllib.loads(fs.read_text(path))
    except tomllib.TOMLDecodeError as exc:
        raise LockError(f"invalid TOML in {path}: {exc}") from exc
    section = data.get("lock")
    if not isinstance(section, dict):
        raise LockError(f"{path}: missing [lock] section")
    entries = tuple(
        LockEntry(path=str(e.get("path", "")), sha256=str(e.get("sha256", "")))
        for e in data.get("architecture", [])
    )
    return Lock(
        at=str(section.get("at", "")),
        phase=str(section.get("phase", "")),
        commit=str(section.get("commit", "")),
        version=int(section.get("version", 0)),
        roadmap_sha256=str(section.get("roadmap_sha256", "")),
        architecture=entries,
    )


def check(
    fs: FilesystemPort,
    lock: Lock,
    project_root: Path,
    roadmap_path: Path,
    architecture_paths: list[Path],
) -> list[str]:
    """Return a list of relative paths whose hash differs from `lock`.

    A path is reported if it is missing, present in the lock but not
    in the current set, present in the current set but not in the
    lock, or has a different SHA-256. An empty list means the frozen
    state matches. Returned paths are relative to `project_root`,
    matching the lock format.
    """
    problems: list[str] = []

    roadmap_rel = _relative(roadmap_path, project_root)
    if fs.exists(roadmap_path):
        if sha256(fs, roadmap_path) != lock.roadmap_sha256:
            problems.append(roadmap_rel)
    else:
        problems.append(roadmap_rel)

    locked = {e.path: e.sha256 for e in lock.architecture}
    current = {_relative(p, project_root): p for p in architecture_paths}

    for rel, expected in locked.items():
        p = project_root / rel
        if not fs.exists(p):
            problems.append(rel)
            continue
        if sha256(fs, p) != expected:
            problems.append(rel)

    for rel in current:
        if rel not in locked:
            problems.append(rel)

    return problems


def render(lock: Lock) -> str:
    """Render a `Lock` as a TOML document.

    All string values pass through `escape_basic_string`. The fields
    the harness writes (timestamps, hashes, phase names, relative
    paths) never need it, but a lock loaded and re-rendered from
    disk could, and the cost of uniform escaping is nil.
    """
    lines = [
        "[lock]",
        f'at = "{escape_basic_string(lock.at)}"',
        f'phase = "{escape_basic_string(lock.phase)}"',
        f'commit = "{escape_basic_string(lock.commit)}"',
        f"version = {lock.version}",
        f'roadmap_sha256 = "{escape_basic_string(lock.roadmap_sha256)}"',
        "",
    ]
    for entry in lock.architecture:
        lines.append("[[architecture]]")
        lines.append(f'path = "{escape_basic_string(entry.path)}"')
        lines.append(f'sha256 = "{escape_basic_string(entry.sha256)}"')
        lines.append("")
    return "\n".join(lines)


def _relative(path: Path, project_root: Path) -> str:
    """Return `path` relative to `project_root`, POSIX-style.

    Raises: `LockError` when `path` is not under `project_root`.
    """
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError as exc:
        raise LockError(
            f"path is outside project root: {path} (root={project_root})"
        ) from exc


__all__ = ["check", "load", "render", "write"]
