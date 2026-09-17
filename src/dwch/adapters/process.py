"""Subprocess adapter.

Runs a command with UTF-8 decoding and a timeout. Returns exit
code, stdout, and stderr; raises `ProcessError` only on a start
failure or timeout, never on a non-zero exit (callers decide
whether that is an error in their context).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..domain.models import ProcessResult
from ..shared.errors import ProcessError


class SubprocessRunner:
    """`ProcessPort` implementation over `subprocess.run`."""

    def run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        timeout: float = 60.0,
    ) -> ProcessResult:
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProcessError(f"command not found: {cmd[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProcessError(f"command timed out: {' '.join(cmd)}") from exc
        return ProcessResult(
            exit_code=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )


__all__ = ["SubprocessRunner"]
