"""Filesystem adapter backed by `pathlib` and the standard library.

Reads are UTF-8 with `errors="strict"` (a decode failure is a real
error). Writes are UTF-8 with LF line endings, no exceptions.
"""

from __future__ import annotations

from pathlib import Path

from ..shared.errors import FilesystemError


class LocalFilesystem:
    """`FilesystemPort` implementation over the local filesystem."""

    def read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FilesystemError(f"read failed: {path}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise FilesystemError(f"not UTF-8: {path}: {exc}") from exc

    def write_text(self, path: Path, text: str) -> None:
        try:
            path.write_text(text, encoding="utf-8", newline="\n")
        except OSError as exc:
            raise FilesystemError(f"write failed: {path}: {exc}") from exc

    def read_bytes(self, path: Path) -> bytes:
        try:
            return path.read_bytes()
        except OSError as exc:
            raise FilesystemError(f"read failed: {path}: {exc}") from exc

    def write_bytes(self, path: Path, data: bytes) -> None:
        try:
            path.write_bytes(data)
        except OSError as exc:
            raise FilesystemError(f"write failed: {path}: {exc}") from exc

    def exists(self, path: Path) -> bool:
        return path.exists()

    def is_dir(self, path: Path) -> bool:
        return path.is_dir()

    def is_file(self, path: Path) -> bool:
        return path.is_file()

    def mkdir(self, path: Path, *, parents: bool = False) -> None:
        try:
            path.mkdir(parents=parents, exist_ok=True)
        except OSError as exc:
            raise FilesystemError(f"mkdir failed: {path}: {exc}") from exc

    def glob(self, root: Path, pattern: str) -> list[Path]:
        return [p for p in root.glob(pattern) if p.is_file()]

    def listdir(self, path: Path) -> list[Path]:
        try:
            return sorted(path.iterdir())
        except OSError as exc:
            raise FilesystemError(f"listdir failed: {path}: {exc}") from exc

    def unlink(self, path: Path) -> None:
        try:
            path.unlink()
        except OSError as exc:
            raise FilesystemError(f"unlink failed: {path}: {exc}") from exc

    def rename(self, src: Path, dst: Path) -> None:
        """Atomic replace via `Path.replace`.

        `Path.replace` maps to `rename(2)` on POSIX and to
        `MoveFileEx(MOVEFILE_REPLACE_EXISTING)` on Windows. Both are
        atomic with respect to the destination: a reader sees either
        the old file or the new one, never a partial write.
        """
        try:
            src.replace(dst)
        except OSError as exc:
            raise FilesystemError(f"rename failed: {src} -> {dst}: {exc}") from exc


__all__ = ["LocalFilesystem"]
