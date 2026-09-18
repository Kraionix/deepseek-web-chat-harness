"""Manage the metadata block in `.harness/handoff.md`.

The handoff file has two parts: the `<!-- harness:begin -->` ...
`<!-- harness:end -->` block, which the harness owns, and everything
outside it, which the user and the AI own. Only the block is ever
rewritten; the prose is preserved verbatim.

`close`, `new-phase`, and `apply` all need the block to be present
and current. It lives here rather than in each command so the three
cannot drift apart.
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
    - If the markers are present, the block between them is replaced
      with values from `state`; the prose around it is preserved.
    - If the markers are missing, the block is inserted at the top
      of the file. This handles a handoff that the AI rewrote from
      scratch without the markers.

    Pre:  `project_root` is a directory; `state` is loaded and
          coherent.
    Post: the file, if it exists, contains exactly one current block.
    """
    handoff = project_root / ".harness" / "handoff.md"
    if not fs.exists(handoff):
        return
    text = fs.read_text(handoff)
    if BEGIN in text and END in text:
        _replace_block(fs, handoff, text, state)
        return
    # Why: the AI may have written a handoff without the block.
    # Prepending it restores the harness's ownership of the block
    # without touching the prose the AI wrote.
    fs.write_text(handoff, _render_block(state) + "\n" + text)


def _replace_block(
    fs: FilesystemPort,
    path: Path,
    text: str,
    state: State,
) -> None:
    """Rewrite the block between the two markers in `text`."""
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    fs.write_text(path, head + _render_block(state) + tail)


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


__all__ = ["ensure_metadata"]
