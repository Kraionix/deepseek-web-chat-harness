"""Parse and validate `.harness/roadmap.toml`.

The roadmap is the machine-readable contract produced by an
architect session and consumed by coder sessions. It is not a
document for humans to read; `docs/architecture.md` is that. This
module only parses, validates, and renders.
"""

from __future__ import annotations

import hashlib
import tempfile
import tomllib
from pathlib import Path

from ..domain.models import (
    Roadmap,
    RoadmapInterface,
    RoadmapMeta,
    RoadmapStep,
    State,
)
from ..shared.errors import FormatError, RoadmapError
from ..shared.paths import normalize_rel, safe_path
from ..shared.toml import list_of_strings, list_of_tables
from .ports import FilesystemPort


def load(fs: FilesystemPort, path: Path) -> Roadmap:
    """Parse a roadmap TOML file into a `Roadmap`.

    Pre:  `path` is the absolute path of a roadmap file.
    Post: returns a `Roadmap` with `[meta]`, `[[steps]]`, and
          `[[interfaces]]` populated. `[[interfaces]]` is optional
          and yields an empty tuple when absent.
    Raises: `RoadmapError` on a missing file, malformed TOML, a
          missing required section, or a list-typed field whose
          shape is wrong (a string where a list is expected, and so
          on).
    """
    if not fs.exists(path):
        raise RoadmapError(f"roadmap not found: {path}")
    try:
        data = tomllib.loads(fs.read_text(path))
    except tomllib.TOMLDecodeError as exc:
        raise RoadmapError(f"invalid TOML in {path}: {exc}") from exc

    if "meta" not in data:
        raise RoadmapError(f"{path}: missing [meta] section")
    if "steps" not in data:
        raise RoadmapError(f"{path}: missing [[steps]] section")

    meta_raw = data["meta"]
    if not isinstance(meta_raw, dict):
        raise RoadmapError(f"{path}: [meta] must be a table")
    meta = RoadmapMeta(
        version=int(meta_raw.get("version", 0)),
        note=str(meta_raw.get("note", "")),
    )
    if meta.version < 1:
        raise RoadmapError(f"{path}: [meta].version must be >= 1")

    try:
        interfaces_raw = list_of_tables(
            data.get("interfaces", []), f"{path}: [[interfaces]]"
        )
        steps_raw = list_of_tables(data.get("steps", []), f"{path}: [[steps]]")
    except ValueError as exc:
        raise RoadmapError(str(exc)) from exc

    interfaces = tuple(_parse_interface(item, path) for item in interfaces_raw)
    steps = tuple(_parse_step(item, path) for item in steps_raw)
    if not steps:
        raise RoadmapError(f"{path}: [[steps]] must contain at least one step")

    return Roadmap(meta=meta, interfaces=interfaces, steps=steps)


def validate(roadmap: Roadmap, project_root: Path | None = None) -> list[str]:
    """Return a list of structural problems with `roadmap`.

    An empty list means the roadmap is well-formed. The function is
    deliberately structural: it checks numbering, references, graph
    shape, and path safety, not semantics.

    `project_root` is optional. When given, every path in `files`,
    `removes`, `moves`, and `interface.module` is additionally run
    through `safe_path`, catching symlink escapes and reserved
    names. When omitted, only the relative-path checks run.
    """
    problems: list[str] = []

    numbers = [s.number for s in roadmap.steps]
    if len(numbers) != len(set(numbers)):
        problems.append("step numbers are not unique")
    expected = list(range(1, len(numbers) + 1))
    if sorted(numbers) != expected:
        problems.append(
            f"step numbers must be 1..{len(numbers)}, got {sorted(numbers)}"
        )

    iface_names = [i.name for i in roadmap.interfaces]
    if len(iface_names) != len(set(iface_names)):
        problems.append("interface names are not unique")

    interface_names = set(iface_names)
    for step in roadmap.steps:
        for name in step.interfaces:
            if name not in interface_names:
                problems.append(f"step {step.number}: unknown interface {name!r}")
        for dep in step.depends_on:
            if dep >= step.number:
                problems.append(
                    f"step {step.number}: depends_on {dep} is not an earlier step"
                )
            elif dep not in numbers:
                problems.append(f"step {step.number}: depends_on {dep} does not exist")

        for rel in step.files:
            reason = _bad_path(rel)
            if reason is not None:
                problems.append(f"step {step.number}: file {rel!r}: {reason}")
            elif project_root is not None:
                problems.extend(_safe_path_problems(rel, f"step {step.number}: files"))

        for rel in step.removes:
            reason = _bad_path(rel)
            if reason is not None:
                problems.append(f"step {step.number}: removes {rel!r}: {reason}")
            elif project_root is not None:
                problems.extend(
                    _safe_path_problems(rel, f"step {step.number}: removes")
                )

        for src, dst in step.moves:
            for label, rel in (("moves.from", src), ("moves.to", dst)):
                reason = _bad_path(rel)
                if reason is not None:
                    problems.append(f"step {step.number}: {label} {rel!r}: {reason}")
                elif project_root is not None:
                    problems.extend(
                        _safe_path_problems(rel, f"step {step.number}: {label}")
                    )

        problems.extend(_step_set_problems(step))

    for iface in roadmap.interfaces:
        if not iface.module:
            continue
        reason = _bad_path(iface.module)
        if reason is not None:
            problems.append(
                f"interface {iface.name!r}: module {iface.module!r}: {reason}"
            )
        elif project_root is not None:
            problems.extend(
                _safe_path_problems(iface.module, f"interface {iface.name!r}: module")
            )

    return problems


def _step_set_problems(step: RoadmapStep) -> list[str]:
    """Intersection and uniqueness problems for one step's sets."""
    problems: list[str] = []
    files = {normalize_rel(p) for p in step.files}
    removes = {normalize_rel(p) for p in step.removes}
    moves_from = {normalize_rel(s) for s, _ in step.moves}
    moves_to = {normalize_rel(d) for _, d in step.moves}

    if files & removes:
        problems.append(
            f"step {step.number}: removes intersects files: "
            + ", ".join(sorted(files & removes))
        )
    if files & moves_from:
        problems.append(
            f"step {step.number}: moves.from intersects files: "
            + ", ".join(sorted(files & moves_from))
        )
    if files & moves_to:
        problems.append(
            f"step {step.number}: moves.to intersects files: "
            + ", ".join(sorted(files & moves_to))
        )
    if removes & moves_from:
        problems.append(
            f"step {step.number}: moves.from intersects removes: "
            + ", ".join(sorted(removes & moves_from))
        )

    if len(moves_from) != len(step.moves):
        problems.append(f"step {step.number}: moves.from values are not unique")
    if len(moves_to) != len(step.moves):
        problems.append(f"step {step.number}: moves.to values are not unique")

    for src, dst in step.moves:
        if normalize_rel(src) == normalize_rel(dst):
            problems.append(
                f"step {step.number}: move {src!r} has identical from and to"
            )

    chained = moves_from & moves_to
    if chained:
        problems.append(
            f"step {step.number}: chained moves (a->b, b->c): "
            + ", ".join(sorted(chained))
        )

    return problems


def _safe_path_problems(rel: str, label: str) -> list[str]:
    """Return a single-element list if `safe_path` refuses `rel`."""
    # `safe_path` needs a root to check escape; use an empty
    # temporary directory as a placeholder root. The structural
    # checks (reserved names, control characters, symlinks) still
    # fire; the escape check compares against a synthetic root and
    # is a no-op for relative paths.
    with tempfile.TemporaryDirectory() as tmp:
        try:
            safe_path(rel, Path(tmp).resolve())
        except FormatError as exc:
            return [f"{label}: {rel!r}: {exc}"]
    return []


def find_step(roadmap: Roadmap, number: int) -> RoadmapStep | None:
    """Return the step with `number`, or None."""
    for step in roadmap.steps:
        if step.number == number:
            return step
    return None


def sha256(fs: FilesystemPort, path: Path) -> str:
    """Return the hex SHA-256 of the file at `path`.

    Pre:  `path` exists and is a file.
    Post: a 64-character lowercase hex string.
    """
    return hashlib.sha256(fs.read_bytes(path)).hexdigest()


def render_summary(roadmap: Roadmap, state: State) -> str:
    """Render a compact list of every step with its status.

    Statuses: `done` (roadmap_step >= number), `current`
    (roadmap_step + 1 == number), `pending` (otherwise).
    """
    lines = [
        f"## Roadmap summary (v{roadmap.meta.version})",
        "",
    ]
    for step in roadmap.steps:
        if state.roadmap_step >= step.number:
            mark = "done"
        elif state.roadmap_step + 1 == step.number:
            mark = "current"
        else:
            mark = "pending"
        lines.append(f"- {step.number:>3}. {step.title} — *{mark}*")
    return "\n".join(lines)


def render_current(step: RoadmapStep) -> str:
    """Render the full spec of one roadmap step."""
    files = "\n".join(f"  - {p}" for p in step.files) or "  (none)"
    removes = "\n".join(f"  - {p}" for p in step.removes) or "  (none)"
    moves = "\n".join(f"  - {s} → {d}" for s, d in step.moves) or "  (none)"
    interfaces = ", ".join(step.interfaces) or "(none)"
    acceptance = "\n".join(f"  - {a}" for a in step.acceptance) or "  (none)"
    depends = ", ".join(str(d) for d in step.depends_on) or "(none)"
    return (
        f"## Current step {step.number}: {step.title}\n"
        f"\n"
        f"Goal: {step.goal}\n"
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


def render_interfaces(roadmap: Roadmap) -> str:
    """Render the full interface table as a markdown list."""
    if not roadmap.interfaces:
        return "## Interfaces\n\n(none declared)"
    lines = ["## Interfaces", ""]
    for iface in roadmap.interfaces:
        line = f"- `{iface.signature}` — {iface.module}"
        if iface.doc:
            line += f" — {iface.doc}"
        lines.append(line)
    return "\n".join(lines)


def _bad_path(value: str) -> str | None:
    """Return a reason string if `value` is not a safe relative path.

    Pre:  `value` is a string from the roadmap.
    Post: None if the path is relative and contains no `..`; a short
          reason otherwise.
    """
    # Why: on Windows, `Path("/foo")` has a root but no drive, so
    # `is_absolute()` returns False. A leading separator still means
    # "outside the project", so it is rejected explicitly.
    if value.startswith(("/", "\\")):
        return "absolute path not allowed"
    p = Path(value)
    if p.is_absolute():
        return "absolute path not allowed"
    if ".." in p.parts:
        return "parent traversal not allowed"
    return None


def _parse_interface(item: dict, path: Path) -> RoadmapInterface:
    name = str(item.get("name", "")).strip()
    if not name:
        raise RoadmapError(f"{path}: an [[interfaces]] entry is missing `name`")
    return RoadmapInterface(
        name=name,
        kind=str(item.get("kind", "function")),
        module=str(item.get("module", "")),
        signature=str(item.get("signature", name)),
        doc=str(item.get("doc", "")),
    )


def _parse_step(item: dict, path: Path) -> RoadmapStep:
    number_raw = item.get("number", 0)
    if not isinstance(number_raw, int) or isinstance(number_raw, bool):
        raise RoadmapError(f"{path}: a [[steps]] entry has non-integer number")
    number = number_raw
    if number < 1:
        raise RoadmapError(f"{path}: a [[steps]] entry has invalid number {number}")
    title = str(item.get("title", "")).strip()
    if not title:
        raise RoadmapError(f"{path}: step {number} is missing `title`")
    try:
        files = list_of_strings(item.get("files", []), f"{path}: step {number}.files")
        interfaces = list_of_strings(
            item.get("interfaces", []), f"{path}: step {number}.interfaces"
        )
        acceptance = list_of_strings(
            item.get("acceptance", []), f"{path}: step {number}.acceptance"
        )
        removes = list_of_strings(
            item.get("removes", []), f"{path}: step {number}.removes"
        )
        depends_raw = item.get("depends_on", [])
        if not isinstance(depends_raw, list):
            raise ValueError(
                f"{path}: step {number}.depends_on: expected a list of integers, "
                f"got {type(depends_raw).__name__}"
            )
        depends_on: list[int] = []
        for i, d in enumerate(depends_raw):
            if not isinstance(d, int) or isinstance(d, bool):
                raise ValueError(
                    f"{path}: step {number}.depends_on[{i}]: expected an integer, "
                    f"got {type(d).__name__}"
                )
            depends_on.append(d)
        moves = _parse_moves(item.get("moves", []), path, number)
    except ValueError as exc:
        raise RoadmapError(str(exc)) from exc

    return RoadmapStep(
        number=number,
        title=title,
        goal=str(item.get("goal", "")),
        files=tuple(files),
        interfaces=tuple(interfaces),
        acceptance=tuple(acceptance),
        depends_on=tuple(depends_on),
        removes=tuple(removes),
        moves=tuple(moves),
    )


def _parse_moves(raw: object, path: Path, number: int) -> list[tuple[str, str]]:
    """Parse the `moves` field into a list of `(src, dst)` tuples.

    Each item must be an inline table with string `from` and `to`
    keys. A bare string is rejected rather than silently ignored.
    """
    if not isinstance(raw, list):
        raise ValueError(
            f"{path}: step {number}.moves: expected a list of tables, "
            f"got {type(raw).__name__}"
        )
    out: list[tuple[str, str]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(
                f"{path}: step {number}.moves[{i}]: expected a table, "
                f"got {type(item).__name__}"
            )
        src = item.get("from")
        dst = item.get("to")
        if not isinstance(src, str) or not isinstance(dst, str):
            raise ValueError(
                f"{path}: step {number}.moves[{i}]: "
                "`from` and `to` must both be strings"
            )
        out.append((src, dst))
    return out


__all__ = [
    "find_step",
    "load",
    "render_current",
    "render_interfaces",
    "render_summary",
    "sha256",
    "validate",
]
