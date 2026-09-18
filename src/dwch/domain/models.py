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


class PhaseKind(StrEnum):
    """Kind of phase a session belongs to.

    `PLANNING` sessions produce design artifacts and a roadmap.
    `DEVELOPMENT` sessions execute a frozen roadmap.
    `UNSET` is the initial value before any `new-phase`.
    """

    PLANNING = "planning"
    DEVELOPMENT = "development"
    UNSET = "unset"


class DeviationType(StrEnum):
    """Kind of deviation a step records against the roadmap.

    `EXTRA_FILE`       — file not listed in `step.files`.
    `MISSING_FILE`     — file listed in `step.files` not written.
    `INTERFACE_CHANGE` — public symbol added, removed, or renamed.
    `BUGFIX_PRIOR`     — change to code from a previous step.
    `ASSUMPTION`       — the spec was incomplete; the coder decided.
    `PLAN_CORRECTION`  — the step spec was wrong, but workable.
    `BLOCKER`          — the step is impossible as specified.
    """

    EXTRA_FILE = "extra-file"
    MISSING_FILE = "missing-file"
    INTERFACE_CHANGE = "interface-change"
    BUGFIX_PRIOR = "bugfix-prior"
    ASSUMPTION = "assumption"
    PLAN_CORRECTION = "plan-correction"
    BLOCKER = "blocker"


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
class Deviation:
    """One recorded deviation from the roadmap.

    `auto` is True when `verify` detected the deviation itself;
    False when the coder declared it in a deviation file.
    """

    type: DeviationType
    affected: tuple[str, ...]
    reason: str
    detail: str
    auto: bool


@dataclass(frozen=True, slots=True)
class RoadmapMeta:
    """Metadata header of `.harness/roadmap.toml`.

    `version` is a positive integer. A new architect session that
    replaces the roadmap must increment it.
    """

    version: int
    note: str


@dataclass(frozen=True, slots=True)
class RoadmapInterface:
    """One public interface declared by the architect.

    `kind` is `"class"`, `"function"`, or `"constant"`. `module` is
    the relative path where the interface is expected to live.
    """

    name: str
    kind: str
    module: str
    signature: str
    doc: str


@dataclass(frozen=True, slots=True)
class RoadmapStep:
    """One implementation step in the roadmap.

    `number` is unique and positive within a single roadmap version.
    `depends_on` names earlier step numbers; cycles are rejected by
    `roadmap.validate`.
    """

    number: int
    title: str
    goal: str
    files: tuple[str, ...]
    interfaces: tuple[str, ...]
    acceptance: tuple[str, ...]
    depends_on: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Roadmap:
    """Parsed `.harness/roadmap.toml`.

    Step numbers are local to this roadmap version. Replacing the
    roadmap resets `state.roadmap_step` to zero.
    """

    meta: RoadmapMeta
    interfaces: tuple[RoadmapInterface, ...]
    steps: tuple[RoadmapStep, ...]


@dataclass(frozen=True, slots=True)
class LockEntry:
    """One hashed file in a lock.

    `path` is stored relative to the project root, using forward
    slashes, so the lock is portable between machines and platforms.
    """

    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Lock:
    """Parsed `.harness/roadmap.lock`.

    Records the freeze: which phase produced it, the git commit at
    freeze time, the roadmap version, and the hashes of every file
    that was frozen. All paths are relative to the project root.
    """

    at: str
    phase: str
    commit: str
    version: int
    roadmap_sha256: str
    architecture: tuple[LockEntry, ...]


@dataclass(frozen=True, slots=True)
class Report:
    """The report produced by `verify` and sent back to the AI.

    `apply_log` is the text written by the preceding `apply`. The
    `deviations` and `roadmap_position` fields are populated only in
    development phases with a frozen roadmap; otherwise they are
    empty.
    """

    step_number: int
    apply_log: str
    checks: tuple[CheckResult, ...]
    commit_hash: str | None
    commit_message: str | None
    deviations: tuple[Deviation, ...]
    roadmap_position: tuple[int, int] | None
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
    planning_commands: tuple[dict[str, Any], ...]
    roadmap: dict[str, Any]
    bootstrap: dict[str, Any]
    tokenizer_path: Path
    tokenizer_url: str
    read_max_tokens: int


@dataclass(frozen=True, slots=True)
class State:
    """Parsed `.harness/state.toml`.

    Written by the harness; read on every command that needs to know
    the current phase, step, or roadmap position.

    `current_step` counts steps within the current phase, so it is
    reset by `new-phase`. `roadmap_step` counts positions within the
    active roadmap version and is reset by `close --freeze`.

    `last_commit` records the commit hash known at the last lifecycle
    transition (`close`, `new-phase`, `rollback`). It is not kept in
    sync with HEAD after every `verify` — the bootstrap header reads
    HEAD directly from git for that.

    `summary_phase` and `summary_written_at` record the most recent
    phase summary recorded by `close`. The bootstrap shows
    `.harness/summaries/{summary_phase}.md` as the only cross-phase
    context the next session sees. Both default to empty strings:
    a project has no summary until its first `close`.
    """

    harness_version: str
    current_phase: str
    phase_kind: str
    current_step: int
    last_commit: str
    last_commit_date: str
    roadmap_version: int
    roadmap_step: int
    roadmap_frozen: bool
    rollback_count: int
    last_opened: str
    last_closed: str
    summary_phase: str = ""
    summary_written_at: str = ""


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Output of `context.build_bootstrap()`.

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
    "Deviation",
    "DeviationType",
    "FileSpec",
    "Lock",
    "LockEntry",
    "ModuleInfo",
    "PhaseKind",
    "ProcessResult",
    "Report",
    "Roadmap",
    "RoadmapInterface",
    "RoadmapMeta",
    "RoadmapStep",
    "State",
    "SymbolInfo",
]
