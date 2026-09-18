"""Manage the metadata block in `.harness/handoff.md`.

The handoff file has two parts: the `<!-- harness:begin -->` ...
`<!-- harness:end -->` block, which the harness owns, and everything
outside it, which the user and the AI own. Only the block is ever
rewritten; the prose is preserved verbatim.

`close`, `new-phase`, and `apply` all need the block to be present
and current. It lives here rather than in each command so the three
cannot drift apart.

The scanner is linear. A regex with `.*?` and `DOTALL` is
quadratic on pathological input (many `BEGIN` with no `END`), and
the handoff is untrusted AI output.
"""

from __future__ import annotations

from pathlib import Path

from ..domain.models import State
from .ports import FilesystemPort

BEGIN = "<!-- harness:begin -->"
END = "<!-- harness:end -->"


def ensure_metadata(
    fs: FilesystemPort,
    project_root: Path,
    state: State,
) -> None:
    """Ensure the harness block is present and current.

    - If the file does not exist, this is a no-op: some phases run
      without a handoff, and the harness does not require one.
    - If a full block is present, it is replaced in place; the prose
      around it is preserved.
    - If a stray marker is present without its pair, or if both
      markers are missing, every marker line is stripped and a fresh
      block is inserted at the top.

    Pre:  `project_root` is a directory; `state` is loaded and
          coherent.
    Post: the file, if it exists, contains exactly one current block.
    """
    handoff = project_root / ".harness" / "handoff.md"
    if not fs.exists(handoff):
        return
    text = fs.read_text(handoff)

    span = _find_first_block(text)
    if span is not None:
        start, end = span
        fs.write_text(handoff, text[:start] + _render_block(state) + text[end:])
        return

    cleaned = _strip_marker_lines(text)
    fs.write_text(handoff, _render_block(state) + "\n" + cleaned)


def _find_first_block(text: str) -> tuple[int, int] | None:
    """Return `(start, end)` of the first complete block, or None.

    `start` is the index of `BEGIN`, `end` is the index just past
    the matching `END`. Linear in `len(text)`; no regex.
    """
    begin_idx = text.find(BEGIN)
    if begin_idx == -1:
        return None
    end_idx = text.find(END, begin_idx + len(BEGIN))
    if end_idx == -1:
        return None
    return (begin_idx, end_idx + len(END))


def _strip_marker_lines(text: str) -> str:
    """Remove every line that is exactly a stray marker.

    Only lines whose stripped content equals `BEGIN` or `END` are
    removed. Prose mentioning the markers is left alone.
    """
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.strip() in (BEGIN, END):
            continue
        out.append(line)
    return "".join(out)


def _render_block(state: State) -> str:
    """Render the harness-owned metadata block for `state`."""
    frozen = "true" if state.roadmap_frozen else "false"
    return (
        f"{BEGIN}\n"
        f"phase: {state.current_phase}\n"
        f"kind: {state.phase_kind}\n"
        f"step: {state.current_step}\n"
        f"roadmap_version: {state.roadmap_version}\n"
        f"roadmap_step: {state.roadmap_step}\n"
        f"frozen: {frozen}\n"
        f"last_commit: {state.last_commit or '(none)'}\n"
        f"closed: {state.last_closed}\n"
        f"{END}"
    )


__all__ = ["BEGIN", "END", "ensure_metadata"]
