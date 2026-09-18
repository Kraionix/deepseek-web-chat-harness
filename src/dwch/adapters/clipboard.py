"""Clipboard adapters for Windows, macOS, and Linux.

`pick_clipboard()` returns the platform-appropriate implementation.
On unsupported platforms, a `NullClipboard` is returned; its
`write()` returns False and `read()` returns empty string. Callers
must handle those cases.
"""

from __future__ import annotations

import platform
import shutil
import subprocess


class WindowsClipboard:
    """Clipboard access via PowerShell."""

    def read(self) -> str:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-Clipboard -Raw",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout

    def write(self, text: str) -> bool:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
                ],
                input=text,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0


class MacClipboard:
    """Clipboard access via `pbpaste` / `pbcopy`."""

    def read(self) -> str:
        if not shutil.which("pbpaste"):
            return ""
        try:
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout

    def write(self, text: str) -> bool:
        if not shutil.which("pbcopy"):
            return False
        try:
            result = subprocess.run(
                ["pbcopy"],
                input=text,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0


class LinuxClipboard:
    """Clipboard access via `wl-copy` (Wayland) or `xclip` (X11)."""

    def _write_cmd(self) -> list[str] | None:
        if shutil.which("wl-copy"):
            return ["wl-copy"]
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard"]
        return None

    def _read_cmd(self) -> list[str] | None:
        if shutil.which("wl-paste"):
            return ["wl-paste", "--no-newline"]
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard", "-o"]
        return None

    def read(self) -> str:
        cmd = self._read_cmd()
        if not cmd:
            return ""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout

    def write(self, text: str) -> bool:
        cmd = self._write_cmd()
        if not cmd:
            return False
        try:
            result = subprocess.run(
                cmd,
                input=text,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0


class NullClipboard:
    """Placeholder for unsupported platforms.

    Callers get an empty read and a failed write; the CLI prints a
    warning in those cases.
    """

    def read(self) -> str:
        return ""

    def write(self, text: str) -> bool:
        return False


def pick_clipboard():
    """Return the platform-appropriate clipboard adapter."""
    system = platform.system()
    if system == "Windows":
        return WindowsClipboard()
    if system == "Darwin":
        return MacClipboard()
    if system == "Linux":
        return LinuxClipboard()
    return NullClipboard()


__all__ = [
    "LinuxClipboard",
    "MacClipboard",
    "NullClipboard",
    "WindowsClipboard",
    "pick_clipboard",
]
