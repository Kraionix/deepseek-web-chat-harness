"""Error hierarchy for the harness.

All harness-raised exceptions derive from `HarnessError`. The CLI
catches it once at the top and turns it into exit code 2 with a
message on stderr. No silent failures.

Subclasses name the stage that failed, not the failure mode: a
missing file and a permission error are both `FilesystemError`;
malformed step text is `FormatError`; a git command's non-zero exit
is `GitError`.
"""

from __future__ import annotations


class HarnessError(Exception):
    """Base for every error the harness raises.

    Never raised directly; use a subclass.
    """


class ConfigError(HarnessError):
    """`.harness/config.toml` is missing, malformed, or inconsistent."""


class StateError(HarnessError):
    """`.harness/state.toml` is missing, malformed, or out of sync."""


class FormatError(HarnessError):
    """A message failed to parse or validate."""


class FilesystemError(HarnessError):
    """A file operation failed: read, write, mkdir, unlink, rename."""


class ProcessError(HarnessError):
    """A subprocess failed to start or timed out."""


class GitError(HarnessError):
    """A git command returned a non-zero exit code."""


class ClipboardError(HarnessError):
    """Clipboard access failed or is unsupported on this platform."""


class TokenizerError(HarnessError):
    """The tokenizer file is missing or could not be loaded."""


class PlanError(HarnessError):
    """`.harness/plan.toml` is missing, malformed, or inconsistent."""


class DeviationError(HarnessError):
    """A deviation file under `.harness/deviations/` is malformed."""


__all__ = [
    "ClipboardError",
    "ConfigError",
    "DeviationError",
    "FilesystemError",
    "FormatError",
    "GitError",
    "HarnessError",
    "PlanError",
    "ProcessError",
    "StateError",
    "TokenizerError",
]
