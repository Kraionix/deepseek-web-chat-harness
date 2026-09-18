"""Parse and validate `.harness/plan.toml`.

The plan is the machine-readable contract produced by a planning
phase and consumed by a development phase. It replaces the
numbered roadmap of 0.3.x: tasks are keyed by `id` (a slug), not
by number. Task order in the file is execution order.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path

from ..domain.models import (
    Interface,
    Plan,
    PlanMeta,
    State,
    Task,
)
from ..shared.errors import FormatError, PlanError
from ..shared.paths import normalize_rel, safe_path
from ..shared.toml import list_of_strings, list_of_tables
from .ports import FilesystemPort

# Task ids are slugs: lowercase ASCII letters, digits, and hyphens,
# starting with a letter. 40 chars is generous for a task slug and
# keeps `steps/{phase}/{task_id}/` path-safe on every platform.
_TASK_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_TASK_ID_MAX_LEN = 40


def load(fs: FilesystemPort, path: Path) -> Plan:
    """Parse a plan TOML file into a `Plan`.

    Pre:  `path` is the absolute path of a plan file.
    Post: returns a `Plan` with `[meta]`, `[[tasks]]`, and
          `[[interfaces]]` populated. `[[interfaces]]` is optional
          and yields an empty tuple when absent.
    Raises: `PlanError` on a missing file, malformed TOML, a missing
          required section, or a list-typed field whose shape is
          wrong (a string where a list is expected, and so on).
    """
    if not fs.exists(path):
        raise PlanError(f"plan not found: {path}")
    try:
        data = tomllib.loads(fs.read_text(path))
    except tomllib.TOMLDecodeError as exc:
        raise PlanError(f"invalid TOML in {path}: {exc}") from exc

    if "meta" not in data:
        raise PlanError(f"{path}: missing [meta] section")
    if "tasks" not in data:
        raise PlanError(f"{path}: missing [[tasks]] section")

    meta_raw = data["meta"]
    if not isinstance(meta_raw, dict):
        raise PlanError(f"{path}: [meta] must be a table")
    meta = PlanMeta(
        version=int(meta_raw.get("version", 0)),
        note=str(meta_raw.get("note", "")),
    )
    if meta.version < 1:
        raise PlanError(f"{path}: [meta].version must be >= 1")

    try:
        interfaces_raw = list_of_tables(
            data.get("interfaces", []), f"{path}: [[interfaces]]"
        )
        tasks_raw = list_of_tables(data.get("tasks", []), f"{path}: [[tasks]]")
    except ValueError as exc:
        raise PlanError(str(exc)) from exc

    interfaces = tuple(_parse_interface(item, path) for item in interfaces_raw)
    tasks = tuple(_parse_task(item, path) for item in tasks_raw)
    if not tasks:
        raise PlanError(f"{path}: [[tasks]] must contain at least one task")

    return Plan(meta=meta, interfaces=interfaces, tasks=tasks)


def validate(plan: Plan, project_root: Path | None = None) -> list[str]:
    """Return a list of structural problems with `plan`.

    An empty list means the plan is well-formed. The function is
    structural: it checks ids, references, graph shape, and path
    safety, not semantics.

    `project_root` is optional. When given, every path in `files`,
    `removes`, `moves`, and `interface.module` is additionally run
    through `safe_path`, catching symlink escapes and reserved
    names. When omitted, only the relative-path checks run.
    """
    problems: list[str] = []

    if plan.meta.version < 1:
        problems.append("meta.version must be >= 1")

    ids = [t.id for t in plan.tasks]
    if len(ids) != len(set(ids)):
        problems.append("task ids are not unique")
    for tid in ids:
        if not _TASK_ID_RE.match(tid):
            problems.append(f"task id {tid!r} does not match ^[a-z][a-z0-9-]*$")
        if len(tid) > _TASK_ID_MAX_LEN:
            problems.append(f"task id {tid!r} is longer than {_TASK_ID_MAX_LEN} chars")

    iface_names = [i.name for i in plan.interfaces]
    if len(iface_names) != len(set(iface_names)):
        problems.append("interface names are not unique")

    used_interfaces: set[str] = set()
    for task in plan.tasks:
        used_interfaces.update(task.interfaces)
    for name in iface_names:
        if name not in used_interfaces:
            problems.append(f"interface {name!r} is not used by any task")

    id_set = set(ids)
    for task in plan.tasks:
        for dep in task.depends_on:
            if dep == task.id:
                problems.append(f"task {task.id!r}: depends_on itself")
            elif dep not in id_set:
                problems.append(f"task {task.id!r}: depends_on unknown id {dep!r}")

    if _has_cycle({t.id: list(t.depends_on) for t in plan.tasks}):
        problems.append("depends_on graph has a cycle")

    for task in plan.tasks:
        problems.extend(_task_set_problems(task))
        for p in task.files:
            problems.extend(_path_problems(p, f"task {task.id!r}: files", project_root))
        for p in task.removes:
            problems.extend(
                _path_problems(p, f"task {task.id!r}: removes", project_root)
            )
        for s, d in task.moves:
            problems.extend(
                _path_problems(s, f"task {task.id!r}: moves.from", project_root)
            )
            problems.extend(
                _path_problems(d, f"task {task.id!r}: moves.to", project_root)
            )

    for iface in plan.interfaces:
        if not iface.module:
            continue
        problems.extend(
            _path_problems(
                iface.module, f"interface {iface.name!r}: module", project_root
            )
        )

    return problems


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    """Return True if the dependency graph contains a cycle.

    Standard tri-color DFS. Edges pointing at unknown nodes are
    ignored here; they are reported separately as unknown deps.
    """
    white, gray, black = 0, 1, 2
    color = {node: white for node in graph}

    def visit(node: str) -> bool:
        color[node] = gray
        for nxt in graph.get(node, []):
            if nxt not in color:
                continue
            c = color[nxt]
            if c == gray:
                return True
            if c == white and visit(nxt):
                return True
        color[node] = black
        return False

    return any(color[node] == white and visit(node) for node in list(graph))


def _task_set_problems(task: Task) -> list[str]:
    """Intersection and uniqueness problems for one task's sets."""
    problems: list[str] = []
    files = {normalize_rel(p) for p in task.files}
    removes = {normalize_rel(p) for p in task.removes}
    moves_from = {normalize_rel(s) for s, _ in task.moves}
    moves_to = {normalize_rel(d) for _, d in task.moves}

    if files & removes:
        problems.append(
            f"task {task.id!r}: removes intersects files: "
            + ", ".join(sorted(files & removes))
        )
    if files & moves_from:
        problems.append(
            f"task {task.id!r}: moves.from intersects files: "
            + ", ".join(sorted(files & moves_from))
        )
    if files & moves_to:
        problems.append(
            f"task {task.id!r}: moves.to intersects files: "
            + ", ".join(sorted(files & moves_to))
        )
    if removes & moves_from:
        problems.append(
            f"task {task.id!r}: moves.from intersects removes: "
            + ", ".join(sorted(removes & moves_from))
        )

    if len(moves_from) != len(task.moves):
        problems.append(f"task {task.id!r}: moves.from values are not unique")
    if len(moves_to) != len(task.moves):
        problems.append(f"task {task.id!r}: moves.to values are not unique")

    for src, dst in task.moves:
        if normalize_rel(src) == normalize_rel(dst):
            problems.append(f"task {task.id!r}: move {src!r} has identical from and to")

    chained = moves_from & moves_to
    if chained:
        problems.append(
            f"task {task.id!r}: chained moves (a->b, b->c): "
            + ", ".join(sorted(chained))
        )

    return problems


def _path_problems(value: str, label: str, project_root: Path | None) -> list[str]:
    """Return structural path problems for one path string.

    `safe_path` needs a root for its escape check. When
    `project_root` is None, only the structural checks (relative,
    no `..`, no leading separator) run.
    """
    if value.startswith(("/", "\\")):
        return [f"{label}: {value!r}: absolute path not allowed"]
    p = Path(value)
    if p.is_absolute():
        return [f"{label}: {value!r}: absolute path not allowed"]
    if ".." in p.parts:
        return [f"{label}: {value!r}: parent traversal not allowed"]
    if project_root is not None:
        try:
            safe_path(value, project_root.resolve(strict=False))
        except FormatError as exc:
            return [f"{label}: {value!r}: {exc}"]
    return []


def find_task(plan: Plan, task_id: str) -> Task | None:
    """Return the task with `task_id`, or None."""
    for task in plan.tasks:
        if task.id == task_id:
            return task
    return None


def position_of(plan: Plan, task_id: str) -> int:
    """Return the zero-based index of `task_id`, or -1 if absent."""
    for i, task in enumerate(plan.tasks):
        if task.id == task_id:
            return i
    return -1


def sha256(fs: FilesystemPort, path: Path) -> str:
    """Return the hex SHA-256 of the file at `path`.

    Pre:  `path` exists and is a file.
    Post: a 64-character lowercase hex string.
    """
    return hashlib.sha256(fs.read_bytes(path)).hexdigest()


def render_summary(plan: Plan, state: State) -> str:
    """Render a compact list of every task with its status.

    Statuses: `done` (position > index), `current` (position ==
    index), `pending` (otherwise).
    """
    lines = [
        f"## Plan summary (v{plan.meta.version})",
        "",
    ]
    for i, task in enumerate(plan.tasks):
        if state.plan_position > i:
            mark = "done"
        elif state.plan_position == i:
            mark = "current"
        else:
            mark = "pending"
        lines.append(f"- `{task.id}`: {task.title} — *{mark}*")
    return "\n".join(lines)


def render_task(task: Task) -> str:
    """Render the full spec of one task."""
    files = "\n".join(f"  - {p}" for p in task.files) or "  (none)"
    removes = "\n".join(f"  - {p}" for p in task.removes) or "  (none)"
    moves = "\n".join(f"  - {s} → {d}" for s, d in task.moves) or "  (none)"
    interfaces = ", ".join(task.interfaces) or "(none)"
    acceptance = "\n".join(f"  - {a}" for a in task.acceptance) or "  (none)"
    depends = ", ".join(task.depends_on) or "(none)"
    return (
        f"## Current task: {task.id} — {task.title}\n"
        f"\n"
        f"Goal: {task.goal}\n"
        f"\n"
        f"Files:\n{files}\n"
        f"\n"
        f"Removes:\n{removes}\n"
        f"\n"
        f"Moves:\n{moves}\n"
        f"\n"
        f"Interfaces: {interfaces}\n"
        f"Depends on: {depends}\n"
        f"\n"
        f"Acceptance:\n{acceptance}\n"
    )


def render_interfaces(plan: Plan) -> str:
    """Render the full interface table as a markdown list."""
    if not plan.interfaces:
        return "## Interfaces\n\n(none declared)"
    lines = ["## Interfaces", ""]
    for iface in plan.interfaces:
        line = f"- `{iface.signature}` — {iface.module}"
        if iface.doc:
            line += f" — {iface.doc}"
        lines.append(line)
    return "\n".join(lines)


def _parse_interface(item: dict, path: Path) -> Interface:
    name = str(item.get("name", "")).strip()
    if not name:
        raise PlanError(f"{path}: an [[interfaces]] entry is missing `name`")
    return Interface(
        name=name,
        kind=str(item.get("kind", "function")),
        module=str(item.get("module", "")),
        signature=str(item.get("signature", name)),
        doc=str(item.get("doc", "")),
    )


def _parse_task(item: dict, path: Path) -> Task:
    task_id = str(item.get("id", "")).strip()
    if not task_id:
        raise PlanError(f"{path}: a [[tasks]] entry is missing `id`")
    title = str(item.get("title", "")).strip()
    if not title:
        raise PlanError(f"{path}: task {task_id!r} is missing `title`")
    try:
        files = list_of_strings(item.get("files", []), f"{path}: task {task_id}.files")
        interfaces = list_of_strings(
            item.get("interfaces", []), f"{path}: task {task_id}.interfaces"
        )
        acceptance = list_of_strings(
            item.get("acceptance", []), f"{path}: task {task_id}.acceptance"
        )
        removes = list_of_strings(
            item.get("removes", []), f"{path}: task {task_id}.removes"
        )
        depends_raw = item.get("depends_on", [])
        if not isinstance(depends_raw, list):
            raise ValueError(
                f"{path}: task {task_id}.depends_on: expected a list of "
                f"strings, got {type(depends_raw).__name__}"
            )
        depends_on: list[str] = []
        for i, d in enumerate(depends_raw):
            if not isinstance(d, str):
                raise ValueError(
                    f"{path}: task {task_id}.depends_on[{i}]: expected a "
                    f"string, got {type(d).__name__}"
                )
            depends_on.append(d)
        moves = _parse_moves(item.get("moves", []), path, task_id)
    except ValueError as exc:
        raise PlanError(str(exc)) from exc

    return Task(
        id=task_id,
        title=title,
        goal=str(item.get("goal", "")),
        files=tuple(files),
        interfaces=tuple(interfaces),
        acceptance=tuple(acceptance),
        depends_on=tuple(depends_on),
        removes=tuple(removes),
        moves=tuple(moves),
    )


def _parse_moves(raw: object, path: Path, task_id: str) -> list[tuple[str, str]]:
    """Parse the `moves` field into a list of `(src, dst)` tuples.

    Each item must be an inline table with string `from` and `to`
    keys. A bare string is rejected rather than silently ignored.
    """
    if not isinstance(raw, list):
        raise ValueError(
            f"{path}: task {task_id}.moves: expected a list of tables, "
            f"got {type(raw).__name__}"
        )
    out: list[tuple[str, str]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(
                f"{path}: task {task_id}.moves[{i}]: expected a table, "
                f"got {type(item).__name__}"
            )
        src = item.get("from")
        dst = item.get("to")
        if not isinstance(src, str) or not isinstance(dst, str):
            raise ValueError(
                f"{path}: task {task_id}.moves[{i}]: "
                "`from` and `to` must both be strings"
            )
        out.append((src, dst))
    return out


__all__ = [
    "find_task",
    "load",
    "position_of",
    "render_interfaces",
    "render_summary",
    "render_task",
    "sha256",
    "validate",
]
