"""Update the metadata block in `.harness/handoff.md`.

The handoff file has two parts: the `<!-- harness:begin -->` ...
`<!-- harness:end -->` block, which the harness owns, and everything
outside it, which the user owns. Only the block is ever rewritten;
the prose is preserved verbatim.

Both `close` and `new-phase` need this. It lives here rather than
in either command so the two cannot drift apart.
"""

from __future__ import annotations

from pathlib import Path

from ..domain.models import State
from .ports import FilesystemPort

BEGIN = "<!-- harness:begin -->"
END = "<!-- harness:end -->"


def update_metadata(fs: FilesystemPort, project_root: Path, state: State) -> None:
    """Rewrite the harness block in `.harness/handoff.md`.

    No-op when the file is missing or when either marker is absent.
    A missing handoff file is not an error: some phases do not use
    one, and the harness does not require it.
    """
    handoff = project_root / ".harness" / "handoff.md"
    if not fs.exists(handoff):
        return
    text = fs.read_text(handoff)
    if BEGIN not in text or END not in text:
        return
    meta = (
        f"{BEGIN}\n"
        f"phase: {state.current_phase}\n"
        f"step: {state.current_step}/{state.total_steps}\n"
        f"last_commit: {state.last_commit or '(none)'}\n"
        f"closed: {state.last_closed}\n"
        f"{END}"
    )
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    fs.write_text(handoff, head + meta + tail)


__all__ = ["update_metadata"]
