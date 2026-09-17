"""Parse and validate `.harness/roadmap.toml`.

The roadmap is the machine-readable contract produced by an
architect session and consumed by coder sessions. It is not a
document for humans to read; `docs/architecture.md` is that. This
module only parses, validates, and renders.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

from ..domain.models import (
    Roadmap,
    RoadmapInterface,
    RoadmapMeta,
    RoadmapStep,
    State,
)
from ..shared.errors import RoadmapError
from .ports import FilesystemPort


def load(fs: FilesystemPort, path: Path) -> Roadmap:
    """Parse a roadmap TOML file into a `Roadmap`.

    Pre:  `path` is the absolute path of a roadmap file.
    Post: returns a `Roadmap` with `[meta]`, `[[interfaces]]`, and
          `[[steps]]` populated.
    Raises: `RoadmapError` on a missing file, malformed TOML, or a
          missing required section.
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
    meta = RoadmapMeta(
        version=int(meta_raw.get("version", 0)),
        note=str(meta_raw.get("note", "")),
    )
    if meta.version < 1:
        raise RoadmapError(f"{path}: [meta].version must be >= 1")

    interfaces = tuple(
        _parse_interface(item, path) for item in data.get("interfaces", [])
    )
    steps = tuple(_parse_step(item, path) for item in data.get("steps", []))
    if not steps:
        raise RoadmapError(f"{path}: [[steps]] must contain at least one step")

    return Roadmap(meta=meta, interfaces=interfaces, steps=steps)


def validate(roadmap: Roadmap) -> list[str]:
    """Return a list of structural problems with `roadmap`.

    An empty list means the roadmap is well-formed. The function is
    deliberately structural: it checks numbering, references, graph
    shape, and path safety, not semantics.
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

    for iface in roadmap.interfaces:
        if not iface.module:
            continue
        reason = _bad_path(iface.module)
        if reason is not None:
            problems.append(
                f"interface {iface.name!r}: module {iface.module!r}: {reason}"
            )

    if _has_cycle(roadmap.steps):
        problems.append("depends_on graph contains a cycle")

    return problems


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
    number = int(item.get("number", 0))
    if number < 1:
        raise RoadmapError(f"{path}: a [[steps]] entry has invalid number {number}")
    title = str(item.get("title", "")).strip()
    if not title:
        raise RoadmapError(f"{path}: step {number} is missing `title`")
    return RoadmapStep(
        number=number,
        title=title,
        goal=str(item.get("goal", "")),
        files=tuple(str(p) for p in item.get("files", [])),
        interfaces=tuple(str(n) for n in item.get("interfaces", [])),
        acceptance=tuple(str(a) for a in item.get("acceptance", [])),
        depends_on=tuple(int(d) for d in item.get("depends_on", [])),
    )


def _has_cycle(steps: tuple[RoadmapStep, ...]) -> bool:
    """True when `depends_on` contains a cycle.

    Depth-first walk with three states: unvisited, visiting, done.
    """
    by_number = {s.number: s for s in steps}
    state: dict[int, int] = {}

    def visit(n: int) -> bool:
        s = state.get(n, 0)
        if s == 1:
            return True
        if s == 2:
            return False
        state[n] = 1
        for dep in by_number[n].depends_on:
            if dep in by_number and visit(dep):
                return True
        state[n] = 2
        return False

    return any(visit(n) for n in by_number)


__all__ = [
    "find_step",
    "load",
    "render_current",
    "render_interfaces",
    "render_summary",
    "sha256",
    "validate",
]
