"""Read and write deviation files under `.harness/deviations/`.

One file per task: `.harness/deviations/{task_id}.toml`. Three
types only. Set-diff mismatches are reported by `verify` checks,
not written as deviations.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from ..domain.models import Deviation, DeviationType
from ..shared.errors import DeviationError
from ..shared.toml import escape_basic_string, list_of_strings, list_of_tables
from .ports import FilesystemPort


def load(fs: FilesystemPort, dir_path: Path, task_id: str) -> list[Deviation]:
    """Load deviations for one task from `{task_id}.toml`.

    Returns an empty list when the file does not exist.
    """
    path = dir_path / f"{task_id}.toml"
    if not fs.exists(path):
        return []
    return parse(fs.read_text(path), path)


def write(
    fs: FilesystemPort,
    dir_path: Path,
    task_id: str,
    deviations: list[Deviation],
) -> None:
    """Write `{task_id}.toml`, overwriting any previous content.

    An empty list is a no-op: it does not create an empty file, and
    it does not delete an existing one. The coder is the author of
    a deviation file; the harness only preserves what is there.
    """
    if not deviations:
        return
    fs.mkdir(dir_path, parents=True)
    path = dir_path / f"{task_id}.toml"
    fs.write_text(path, render(deviations))


def load_recent(fs: FilesystemPort, dir_path: Path, n: int) -> list[Deviation]:
    """Load up to `n` deviation files, newest last.

    Missing directory is not an error. `n <= 0` returns an empty
    list: the caller asked for no deviations, not for all of them.
    """
    if n <= 0:
        return []
    if not fs.is_dir(dir_path):
        return []
    files = sorted(fs.glob(dir_path, "*.toml"))
    out: list[Deviation] = []
    for path in files[-n:]:
        out.extend(parse(fs.read_text(path), path))
    return out


def summarize(deviations: list[Deviation], n: int) -> str:
    """Render the last `n` deviations as a markdown list.

    `n <= 0` renders the empty placeholder: the caller asked for no
    deviations, not for all of them.
    """
    if n <= 0 or not deviations:
        return "## Deviations\n\n(none)"
    tail = deviations[-n:]
    lines = ["## Deviations", ""]
    for dev in tail:
        affected = ", ".join(dev.affected) or "-"
        lines.append(f"- {dev.type.value}: {affected} — {dev.reason}")
    return "\n".join(lines)


def render(deviations: list[Deviation]) -> str:
    """Render deviations as a TOML document."""
    lines: list[str] = []
    for dev in deviations:
        lines.append("[[deviation]]")
        lines.append(f'type = "{dev.type.value}"')
        affected = ", ".join(f'"{escape_basic_string(a)}"' for a in dev.affected)
        lines.append(f"affected = [{affected}]")
        lines.append(f'reason = "{escape_basic_string(dev.reason)}"')
        lines.append(f'detail = "{escape_basic_string(dev.detail)}"')
        lines.append("")
    return "\n".join(lines)


def parse(text: str, path: Path) -> list[Deviation]:
    """Parse a deviation TOML document into a list of `Deviation`.

    Pre:  `text` is the file content; `path` is used only for error
          messages.
    Post: returns one `Deviation` per `[[deviation]]` table.
    Raises: `DeviationError` on malformed TOML, an unknown type, or
          a list-typed field whose shape is wrong.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise DeviationError(f"invalid TOML in {path}: {exc}") from exc

    try:
        items = list_of_tables(data.get("deviation", []), f"{path}: [[deviation]]")
    except ValueError as exc:
        raise DeviationError(str(exc)) from exc

    out: list[Deviation] = []
    for item in items:
        raw_type = str(item.get("type", "")).strip()
        try:
            dtype = DeviationType(raw_type)
        except ValueError as exc:
            raise DeviationError(
                f"{path}: unknown deviation type {raw_type!r}"
            ) from exc
        try:
            affected = list_of_strings(item.get("affected", []), f"{path}: affected")
        except ValueError as exc:
            raise DeviationError(str(exc)) from exc
        out.append(
            Deviation(
                type=dtype,
                affected=tuple(affected),
                reason=str(item.get("reason", "")),
                detail=str(item.get("detail", "")),
            )
        )
    return out


__all__ = [
    "load",
    "load_recent",
    "parse",
    "render",
    "summarize",
    "write",
]
