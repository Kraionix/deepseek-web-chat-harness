"""Manage the metadata block in `.harness/handoff.md`.

The handoff file has two parts: the `<!-- harness:begin -->` ...
`<!-- harness:end -->` block, which the harness owns, and everything
outside it, which the user and the AI own. Only the block is ever
rewritten; the prose is preserved verbatim.

`close`, `new-phase`, and `apply` all need the block to be present
and current. It lives here rather than in each command so the three
cannot drift apart.

Robustness note: the AI is free to rewrite the handoff and may
produce only one of the two markers, or duplicate a marker. The
regex-based implementation below collapses every such case to a
single fresh block; the previous `partition`-based one left the
stray marker in place and accumulated blocks across calls.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..domain.models import State
from .ports import FilesystemPort

BEGIN = "<!-- harness:begin -->"
END = "<!-- harness:end -->"

# A single, non-greedy match of the whole harness block. `DOTALL`
# lets the body span lines; `re.escape` keeps the marker text from
# being interpreted as regex. `count=1` on `sub` replaces only the
# first block, so a duplicated block further down is preserved as
# prose (and would be re-emitted on the next call — but the AI
# cannot legally write a second block, and the harness never does).
_BLOCK_RE = re.compile(
    re.escape(BEGIN) + r".*?" + re.escape(END),
    re.DOTALL,
)


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
      block is inserted at the top. This handles a handoff the AI
      rewrote from scratch and a handoff with a half-deleted block
      identically, without accumulating stale fragments.

    Pre:  `project_root` is a directory; `state` is loaded and
          coherent.
    Post: the file, if it exists, contains exactly one current block.
    """
    handoff = project_root / ".harness" / "handoff.md"
    if not fs.exists(handoff):
        return
    text = fs.read_text(handoff)

    if _BLOCK_RE.search(text):
        fs.write_text(handoff, _replace_first_block(text, state))
        return

    # No full block. Remove any stray marker lines the AI may have
    # left, then prepend a fresh block.
    cleaned = _strip_marker_lines(text)
    fs.write_text(handoff, _render_block(state) + "\n" + cleaned)


def _replace_first_block(text: str, state: State) -> str:
    """Replace the first complete harness block in `text`."""
    return _BLOCK_RE.sub(lambda _m: _render_block(state), text, count=1)


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
