"""Path validation helpers for step paths and roadmap paths.

Only stdlib dependencies. `shared` does not import from any other
layer.

Two functions:

- `check_safe_root(project_root)` — called once by the CLI before
  any command runs. Refuses to operate at filesystem roots, in
  system directories, in the home directory, on UNC or device
  paths, and inside the Windows environment roots.
- `safe_path(raw, resolved_root)` — the single path validator used
  for every path in a step message and for every path-typed field
  in the roadmap. Returns the *resolved* path; every subsequent
  filesystem operation must use the returned value, never
  `root / rel`.

TOCTOU between validation and the eventual write is out of scope
for a local single-user CLI. The checks here close the structural
hole (a validator that checks one path while the write follows a
symlink to another); they do not defend against a concurrent
process racing the resolver.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .errors import FormatError

# Windows reserved device names. Case-insensitive, with or without
# an extension. `COM0`/`LPT0` are included because Windows accepts
# them in some contexts.
_RESERVED_WINDOWS_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM0",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT0",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)

_INVALID_PATH_CHARS = frozenset('<>:"|?*')

# Top-level system directories, by platform. Only checked when the
# resolved root's parent is the filesystem root itself.
_WINDOWS_TOP_DIRS = frozenset(
    {
        "users",
        "windows",
        "program files",
        "program files (x86)",
        "programdata",
    }
)
_POSIX_TOP_DIRS = frozenset(
    {
        "etc",
        "usr",
        "bin",
        "sbin",
        "lib",
        "lib64",
        "boot",
        "dev",
        "proc",
        "sys",
        "var",
        "root",
        "srv",
        "opt",
    }
)
_MACOS_TOP_DIRS = frozenset({"system", "library", "applications"})


def normalize_rel(raw: str) -> str:
    """Normalize a path string to a relative POSIX form.

    Backslashes become slashes, repeated slashes collapse, and a
    trailing slash is removed. Used for comparison and for storing
    paths in the lock and in deviation files.
    """
    s = raw.replace("\\", "/")
    while "//" in s:
        s = s.replace("//", "/")
    if len(s) > 1:
        s = s.rstrip("/")
    return s


def check_safe_root(project_root: Path) -> str | None:
    """Return a refusal reason, or None when `project_root` is safe.

    Called by the CLI before dispatch and again by `cmd_init`.
    `project_root` is always `Path.cwd()`; there is no other source.

    Refusals:

    - UNC and device paths (`\\\\server\\share`, `\\\\?\\...`).
    - Filesystem roots (`/`, `C:\\`).
    - System directories at the filesystem top level.
    - Windows environment roots (`SystemRoot`, `ProgramFiles`, ...):
      equal to, inside, or containing the project root.
    - The home directory, or any ancestor of it. A project *inside*
      home (e.g. `~/projects/foo`) is allowed.
    """
    try:
        resolved = project_root.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        return f"cannot resolve project root: {exc}"

    s = str(resolved)
    if s.startswith(("\\\\", "//")):
        return f"refusing to run on a UNC path: {resolved}"
    if len(resolved.parts) >= 1 and str(resolved.parts[0]).startswith(
        ("\\\\?\\", "\\\\.\\")
    ):
        return f"refusing to run on a device path: {resolved}"

    if len(resolved.parts) < 2:
        return f"refusing to run at filesystem root: {resolved}"

    if len(resolved.parts) == 2:
        lname = resolved.name.lower()
        if sys.platform == "win32":
            if lname in _WINDOWS_TOP_DIRS:
                return f"refusing to run in a system directory: {resolved}"
        else:
            if lname in _POSIX_TOP_DIRS:
                return f"refusing to run in a system directory: {resolved}"
            if sys.platform == "darwin" and lname in _MACOS_TOP_DIRS:
                return f"refusing to run in a system directory: {resolved}"
        # `/home` itself, not `/home/<user>/...`.
        if lname == "home":
            return f"refusing to run in a system directory: {resolved}"

    if sys.platform == "win32":
        for var in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
            env_val = os.environ.get(var)
            if not env_val:
                continue
            try:
                env_path = Path(env_val).resolve(strict=False)
            except (OSError, RuntimeError):
                continue
            if resolved == env_path:
                return f"refusing to run in {var}: {resolved}"
            if resolved.is_relative_to(env_path):
                return f"refusing to run inside {var}: {resolved}"
            if env_path.is_relative_to(resolved):
                return f"refusing to run above {var}: {resolved}"

    try:
        home = Path.home().resolve(strict=False)
    except (OSError, RuntimeError):
        home = None
    if home is not None:
        if resolved == home:
            return f"refusing to run in the home directory: {resolved}"
        if home.is_relative_to(resolved):
            return f"refusing to run above the home directory: {resolved}"

    return None


def safe_path(raw: str, resolved_root: Path) -> Path:
    """Validate `raw` and return the resolved target under `resolved_root`.

    Raises `FormatError` on:

    - an empty or whitespace-only path;
    - an absolute path, or a drive-relative path like `C:foo`;
    - a component that is empty, `.`, `..`, has a leading or
      trailing space, a trailing dot, contains `< > : " | ? *`,
      contains a control character, is a Windows reserved name, or
      is longer than 255 UTF-8 bytes;
    - a path whose resolution changes (a symlink component);
    - a path whose resolution escapes `resolved_root`.

    `resolved_root` must already be resolved; `check_safe_root`
    guarantees that for the project root. The project root itself
    being a symlink is fine: the comparison is against
    `resolved_root / rel`, and `resolved_root` is already resolved.

    A leading dot is *allowed*: `.harness/`, `.gitignore`, and
    `.github/` are ordinary paths. Windows strips only *trailing*
    dots and *trailing* spaces; a leading dot is not stripped.
    """
    s = raw.replace("\\", "/")
    while "//" in s:
        s = s.replace("//", "/")
    if len(s) > 1:
        s = s.rstrip("/")

    if not s or not s.strip():
        raise FormatError(f"empty path: {raw!r}")

    if s.startswith("/"):
        raise FormatError(f"absolute path not allowed: {raw!r}")

    # Split manually: `PurePosixPath` would normalize `.` away and
    # hide a `.` component from the per-component check below.
    parts = s.split("/")
    if not parts:
        raise FormatError(f"empty path: {raw!r}")

    first = parts[0]
    if len(first) >= 2 and first[0].isalpha() and first[1] == ":":
        raise FormatError(f"drive-relative path not allowed: {raw!r}")

    for part in parts:
        _validate_component(part, raw)

    rel = Path(*parts)

    if len(str(rel)) > 260:
        print(
            f"warning: path longer than 260 characters: {rel}",
            file=sys.stderr,
        )

    candidate = resolved_root / rel
    try:
        resolved_candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise FormatError(f"cannot resolve {raw!r}: {exc}") from exc

    if resolved_candidate != candidate:
        raise FormatError(f"symlinks are not supported in step paths: {rel}")

    if not resolved_candidate.is_relative_to(resolved_root):
        raise FormatError(f"path escapes project root: {rel}")

    return resolved_candidate


def _validate_component(part: str, raw: str) -> None:
    """Reject one path component that is unsafe on any platform.

    A component may not be empty, `.`, or `..`; it may not start or
    end with a space, and it may not end with a dot. A leading dot
    is allowed. It may not contain `< > : " | ? *` or a control
    character, may not be a reserved Windows name, and may not
    exceed 255 UTF-8 bytes.
    """
    if not part:
        raise FormatError(f"empty path component in {raw!r}")
    if part in (".", ".."):
        raise FormatError(f"invalid path component {part!r} in {raw!r}")
    if part[0] == " " or part[-1] in (" ", "."):
        raise FormatError(
            f"path component with leading or trailing space or trailing dot: {part!r}"
        )
    for ch in part:
        if ch in _INVALID_PATH_CHARS:
            raise FormatError(f"path component contains {ch!r}: {part!r} (in {raw!r})")
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise FormatError(f"path component contains a control character: {part!r}")
    stem = part.rsplit(".", 1)[0] if "." in part else part
    if stem.upper() in _RESERVED_WINDOWS_NAMES:
        raise FormatError(f"path component is a reserved Windows name: {part!r}")
    if len(part.encode("utf-8")) > 255:
        raise FormatError(f"path component longer than 255 bytes: {part!r}")


__all__ = ["check_safe_root", "normalize_rel", "safe_path"]
