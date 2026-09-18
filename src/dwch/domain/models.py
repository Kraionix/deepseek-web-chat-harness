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

    `PLANNING` sessions produce a plan. `DEVELOPMENT` sessions
    execute a frozen plan. `UNSET` is the initial value before any
    `start`.
    """

    PLANNING = "planning"
    DEVELOPMENT = "development"
    UNSET = "unset"


class PhaseStatus(StrEnum):
    """Lifecycle status of the current phase.

    `OPEN` is the normal working state. `CLOSED` is set by `done`
    on the last task or by `close` in an older protocol. `ABANDONED`
    is set by `abandon`; the files stay on disk and the next phase
    does not inherit.
    """

    OPEN = "open"
    CLOSED = "closed"
    ABANDONED = "abandoned"


class DeviationType(StrEnum):
    """Kind of deviation a task records against the plan.

    Three types only. `BLOCKER` and `PLAN_CORRECTION` close the
    task as deviated and queue a follow-up. `ASSUMPTION` closes the
    task as done and logs the deviation.
    """

    BLOCKER = "blocker"
    ASSUMPTION = "assumption"
    PLAN_CORRECTION = "plan-correction"


@dataclass(frozen=True, slots=True)
class WriteOp:
    """One file to write.

    `path` is relative to the project root. `content` is the file
    body verbatim, exactly as it should be written to disk.
    """

    path: str
    content: str


@dataclass(frozen=True, slots=True)
class DeleteOp:
    """One file to delete.

    Only regular files may be deleted. Directories are not
    supported.
    """

    path: str


@dataclass(frozen=True, slots=True)
class MoveOp:
    """One file rename.

    `src` must exist; `dst` must not. Both paths are relative to
    the project root.
    """

    src: str
    dst: str


StepOp = WriteOp | DeleteOp | MoveOp


def op_paths(op: StepOp) -> tuple[str, ...]:
    """Return every path the op touches.

    Used by the uniqueness check, by `validate_paths`, and by
    `is_substantive`.
    """
    if isinstance(op, WriteOp):
        return (op.path,)
    if isinstance(op, DeleteOp):
        return (op.path,)
    if isinstance(op, MoveOp):
        return (op.src, op.dst)
    raise TypeError(f"unknown StepOp type: {type(op).__name__}")


def op_written_paths(op: StepOp) -> tuple[str, ...]:
    """Return only the paths that exist after the op.

    Used by `check_compile`, by `check_task_changes`, and by the
    task-existence precheck. A `DeleteOp` contributes nothing; a
    `MoveOp` contributes its destination.
    """
    if isinstance(op, WriteOp):
        return (op.path,)
    if isinstance(op, DeleteOp):
        return ()
    if isinstance(op, MoveOp):
        return (op.dst,)
    raise TypeError(f"unknown StepOp type: {type(op).__name__}")


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
    """One recorded deviation from the plan.

    Three types only. `auto` is kept for schema compatibility and is
    always False in 0.4.0: file-set mismatches are check failures,
    not deviations.
    """

    type: DeviationType
    affected: tuple[str, ...]
    reason: str
    detail: str
    auto: bool = False


@dataclass(frozen=True, slots=True)
class PlanMeta:
    """Metadata header of `.harness/plan.toml`.

    `version` is a positive integer. A new planning phase that
    replaces the plan must increment it.
    """

    version: int
    note: str


@dataclass(frozen=True, slots=True)
class Interface:
    """One public interface declared by the planner.

    `kind` is `"class"`, `"function"`, or `"constant"`. `module` is
    the relative path where the interface is expected to live.
    """

    name: str
    kind: str
    module: str
    signature: str
    doc: str


@dataclass(frozen=True, slots=True)
class Task:
    """One task in the plan.

    `id` is a slug (`^[a-z][a-z0-9-]*$`, unique, ≤40 chars). It
    replaces the numbered step from 0.3.x. `depends_on` names other
    task ids; cycles are rejected by `plan.validate`.

    `removes` lists files the task deletes; `moves` lists
    `(src, dst)` pairs the task renames. Both default to empty.
    """

    id: str
    title: str
    goal: str
    files: tuple[str, ...]
    interfaces: tuple[str, ...]
    acceptance: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    removes: tuple[str, ...] = ()
    moves: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Plan:
    """Parsed `.harness/plan.toml`.

    Task order in the file is execution order. `meta.version`
    increments per plan; a new plan resets `state.plan.position` to
    zero.
    """

    meta: PlanMeta
    interfaces: tuple[Interface, ...]
    tasks: tuple[Task, ...]


@dataclass(frozen=True, slots=True)
class Report:
    """The report produced by `verify` and sent back to the AI.

    `task_id` is the task the report is about. `attempt` is the
    consecutive failure count at the time the report was written
    (1 for the first verify of a task).
    """

    task_id: str
    attempt: int
    apply_log: str
    checks: tuple[CheckResult, ...]
    commit_hash: str | None
    commit_message: str | None
    deviations: tuple[Deviation, ...]
    plan_position: tuple[int, int] | None
    notes: str
    question: str


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    """One public symbol extracted from a Python module.

    `kind` is `"class"`, `"function"`, or `"constant"`. `signature`
    is the ast-unparsed declaration line for classes and functions;
    for constants it is `name = ...`.
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

    See `application.config` for the loader and the expected shape
    of the file. All fields have defaults derived from the rendered
    template, so a minimal config works without all sections.
    """

    harness_version: str
    project_name: str
    paths: dict[str, str]
    context: dict[str, Any]
    verify_commands: tuple[dict[str, Any], ...]
    planning_commands: tuple[dict[str, Any], ...]
    plan: dict[str, Any]
    bootstrap: dict[str, Any]
    tokenizer_path: Path
    tokenizer_url: str
    read_max_tokens: int
    notes_path: str


@dataclass(frozen=True, slots=True)
class State:
    """Parsed `.harness/state.toml`.

    State is the single source of truth for lifecycle facts in
    0.4.0. There is no `handoff.md` and no separate roadmap lock
    file: `state.plan` records the frozen plan's version and hash.
    """

    harness_version: str
    phase_name: str
    phase_kind: str
    phase_status: str
    phase_opened_at: str
    phase_closed_at: str
    plan_version: int
    plan_sha256: str
    plan_position: int
    plan_frozen: bool
    verify_ok: bool
    verify_task_id: str
    verify_at: str
    failure_task_id: str
    failure_check_name: str
    failure_excerpt: str
    failure_count: int
    rollback_count: int
    last_commit: str
    last_commit_date: str


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
    "DeleteOp",
    "Deviation",
    "DeviationType",
    "Interface",
    "ModuleInfo",
    "MoveOp",
    "PhaseKind",
    "PhaseStatus",
    "Plan",
    "PlanMeta",
    "ProcessResult",
    "Report",
    "State",
    "StepOp",
    "SymbolInfo",
    "Task",
    "WriteOp",
    "op_paths",
    "op_written_paths",
]
