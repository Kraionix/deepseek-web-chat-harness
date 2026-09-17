"""Domain models for the harness.

Frozen dataclasses. No runtime validation beyond what the type
annotations express; the harness assumes inputs come from trusted
sources (its own config, its own state, its own command output).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class StepStatus(StrEnum):
    """Lifecycle state of one step.

    `PENDING`   — not yet applied.
    `APPLIED`   — files written by `apply`, not yet verified.
    `VERIFIED`  — `verify` succeeded, commit made.
    `FAILED`    — `verify` ran but at least one required check failed.
    `ROLLED_BACK` — undone by `rollback`.
    """

    PENDING = "pending"
    APPLIED = "applied"
    VERIFIED = "verified"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class PhaseStatus(StrEnum):
    """Lifecycle state of one phase."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class Step:
    """One unit of work: a batch of files produced by the AI.

    `files` is the list of relative paths the step's message declared.
    `status` reflects the last operation performed on this step.
    Timestamps are ISO-8601 strings; the harness never parses them
    back into datetimes.
    """

    number: int
    files: tuple[str, ...]
    status: StepStatus = StepStatus.PENDING
    applied_at: str | None = None
    verified_at: str | None = None


@dataclass(frozen=True, slots=True)
class Phase:
    """A named group of steps with a shared goal.

    Phase names are `NN-slug` (e.g. `01-implementation`). The numeric
    prefix orders phases; the slug is a short label.
    """

    name: str
    steps: tuple[Step, ...]
    status: PhaseStatus = PhaseStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True, slots=True)
class FileSpec:
    """One file produced by parsing a step message.

    `path` is relative to the project root. `content` is the file
    body verbatim, exactly as it should be written to disk.
    """

    path: str
    content: str


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Result of running one subprocess.

    `exit_code` is 0 for success. `stdout` and `stderr` are decoded
    UTF-8 text with `errors="replace"`, so they are always safe to
    print.
    """

    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result of one verify command.

    `required` mirrors the config flag: a failing non-required check
    is recorded in the report but does not block the commit.
    """

    name: str
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    required: bool


@dataclass(frozen=True, slots=True)
class Report:
    """The report produced by `verify` and sent back to the AI.

    `apply_log` is the text written by the preceding `apply` (the
    list of files written). `notes` and `question` are user-fillable
    placeholders; the harness never writes to them.
    """

    step_number: int
    apply_log: str
    checks: tuple[CheckResult, ...]
    commit_hash: str | None
    commit_message: str | None
    notes: str
    question: str


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    """One public symbol extracted from a Python module.

    `kind` is `"class"`, `"function"`, or `"constant"`. `signature`
    is the ast-unparsed declaration line for classes and functions;
    for constants it is empty.
    """

    name: str
    kind: str
    signature: str


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    """Interface summary of one Python module.

    `docstring` is the first line of the module docstring, or empty.
    `symbols` is empty for modules with no public surface.
    """

    path: str
    size_lines: int
    docstring: str
    symbols: tuple[SymbolInfo, ...]


@dataclass(frozen=True, slots=True)
class Config:
    """Parsed `.harness/config.toml`.

    See `application.config` for the loader and the expected shape of
    the file. All fields have defaults derived from `templates/config.toml`,
    so a minimal config works without all sections present.
    """

    harness_version: str
    project_name: str
    paths: dict[str, str]
    context: dict[str, Any]
    verify_commands: tuple[dict[str, Any], ...]
    bootstrap: dict[str, Any]
    tokenizer_path: Path
    tokenizer_url: str
    read_max_tokens: int


@dataclass(frozen=True, slots=True)
class State:
    """Parsed `.harness/state.toml`.

    Written by the harness; read on every command that needs to know
    the current phase or step. Timestamps are ISO-8601 strings.

    `last_commit` records the commit hash known at the last
    lifecycle transition (`close`, `new-phase`, `rollback`). It is
    not kept in sync with HEAD after every `verify` — the bootstrap
    header reads HEAD directly from git for that. This field exists
    so a state file on disk can answer "what was the last commit
    when this session was closed".

    `current_step` and `total_steps` *are* kept in sync: `verify`
    updates them before its commit, so the bootstrap's Progress
    section reflects the work actually done in the current phase.
    """

    harness_version: str
    current_phase: str
    current_step: int
    total_steps: int
    last_commit: str
    last_commit_date: str
    last_opened: str
    last_closed: str


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Output of `context.build()`.

    `breakdown` maps section name to token count. `truncated` is
    True when the harness dropped optional sections to fit
    `max_tokens`.
    """

    text: str
    breakdown: dict[str, int] = field(default_factory=dict)
    total_tokens: int = 0
    truncated: bool = False


__all__ = [
    "BootstrapResult",
    "CheckResult",
    "Config",
    "FileSpec",
    "ModuleInfo",
    "Phase",
    "PhaseStatus",
    "ProcessResult",
    "Report",
    "State",
    "Step",
    "StepStatus",
    "SymbolInfo",
]
