"""Read and write deviation files under `.harness/deviations/`.

The coder writes `.harness/deviations/step-NN.toml` to declare a
deviation. `verify` writes `.harness/deviations/step-NN-auto.toml`
when it detects one. Both files use the same TOML schema.

`load_step` reads only the declared file; `load_auto_step` reads
only the auto file. `load_recent` reads both, for the bootstrap's
deviations summary.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from ..domain.models import Deviation, DeviationType
from ..shared.errors import DeviationError
from ..shared.toml import escape_basic_string, list_of_strings, list_of_tables
from .ports import FilesystemPort


def load_step(fs: FilesystemPort, dir_path: Path, step: int) -> list[Deviation]:
    """Load declared deviations for one step from `step-NN.toml`.

    Returns an empty list when the file does not exist. Auto
    deviations are read by `load_auto_step`.
    """
    path = dir_path / f"step-{step:02d}.toml"
    if not fs.exists(path):
        return []
    return parse(fs.read_text(path), path)


def load_auto_step(fs: FilesystemPort, dir_path: Path, step: int) -> list[Deviation]:
    """Load auto deviations for one step from `step-NN-auto.toml`.

    Returns an empty list when the file does not exist.
    """
    path = dir_path / f"step-{step:02d}-auto.toml"
    if not fs.exists(path):
        return []
    return parse(fs.read_text(path), path)


def load_recent(fs: FilesystemPort, dir_path: Path, n: int) -> list[Deviation]:
    """Load up to `n` deviation files, newest last.

    Both declared and auto files are read. Missing directory is not
    an error. `n <= 0` returns an empty list: the caller asked for
    no deviations, not for all of them (`[-0:]` is the whole list).
    """
    if n <= 0:
        return []
    if not fs.is_dir(dir_path):
        return []
    files = sorted(fs.glob(dir_path, "step-*.toml"))
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
        flag = "auto" if dev.auto else "declared"
        lines.append(f"- {dev.type.value} ({flag}): {affected} — {dev.reason}")
    return "\n".join(lines)


def write_auto(
    fs: FilesystemPort,
    dir_path: Path,
    step: int,
    deviations: list[Deviation],
) -> None:
    """Write `.harness/deviations/step-NN-auto.toml`, overwriting.

    Auto deviations are deterministic for a given step, so a rewrite
    is safe: the same mismatch yields the same file.
    """
    if not deviations:
        return
    fs.mkdir(dir_path, parents=True)
    path = dir_path / f"step-{step:02d}-auto.toml"
    fs.write_text(path, render(deviations))


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
        lines.append(f"auto = {'true' if dev.auto else 'false'}")
        lines.append("")
    return "\n".join(lines)


def parse(text: str, path: Path) -> list[Deviation]:
    """Parse a deviation TOML document into a list of `Deviation`.

    Pre:  `text` is the file content; `path` is used only for error
          messages.
    Post: returns one `Deviation` per `[[deviation]]` table.
    Raises: `DeviationError` on malformed TOML, an unknown type, a
          list-typed field whose shape is wrong, or a non-boolean
          `auto` value. A string `auto = "false"` is rejected
          rather than silently coerced to True by `bool()`.
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
        raw_auto = item.get("auto", False)
        if not isinstance(raw_auto, bool):
            raise DeviationError(
                f"{path}: auto must be a boolean, "
                f"got {type(raw_auto).__name__} ({raw_auto!r})"
            )
        out.append(
            Deviation(
                type=dtype,
                affected=tuple(affected),
                reason=str(item.get("reason", "")),
                detail=str(item.get("detail", "")),
                auto=raw_auto,
            )
        )
    return out


__all__ = [
    "load_auto_step",
    "load_recent",
    "load_step",
    "parse",
    "render",
    "summarize",
    "write_auto",
]
