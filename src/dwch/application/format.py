"""Parse step messages and render reports.

The step format is fixed and minimal: blocks delimited by
`<<<FILE:path>>>` and `<<<END>>>`. Everything outside a block is
ignored. There is no escaping and no nesting; the parser is a
single forward scan that tracks whether it is inside a block, so a
literal `<<<FILE:...>>>` line inside content is not a marker.

Step numbers are canonicalized here: `1`, `01`, and `001` all name
the same step, and every command that builds a step filename goes
through `format_step`. Likewise, `report_sort_key` extracts the
numeric part so that `report-1.txt` and `report-10.txt` sort in
numeric rather than lexicographic order.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..domain.models import CheckResult, Deviation, FileSpec, Report
from ..shared.errors import FormatError

FILE_OPEN = "<<<FILE:"
FILE_CLOSE = "<<<END>>>"

_REPORT_RE = re.compile(r"^report-(\d+)\.txt$")


def parse_step_message(text: str) -> list[FileSpec]:
    """Parse a step message into a list of `FileSpec`.

    Pre:  `text` is the raw content of the AI's message.
    Post: returns a list of `(path, content)` pairs, in the order
          the blocks appeared. Paths are unique.
    Raises: `FormatError` on an unclosed block, an empty path, a
          duplicate path, or no blocks at all.

    Trailing whitespace around the marker lines is tolerated: the
    parser compares an `rstrip()`-ed line. A human copying from a
    chat window sometimes leaves a trailing space after
    `<<<END>>>`.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    specs: list[FileSpec] = []
    seen: set[str] = set()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(FILE_OPEN) and line.rstrip().endswith(">>>"):
            stripped = line.rstrip()
            path = stripped[len(FILE_OPEN) : -3].strip()
            if not path:
                raise FormatError(f"empty path at line {i + 1}")
            if path in seen:
                raise FormatError(f"duplicate path {path!r} at line {i + 1}")
            seen.add(path)
            i += 1
            buf: list[str] = []
            while i < len(lines) and lines[i].rstrip() != FILE_CLOSE:
                buf.append(lines[i])
                i += 1
            if i >= len(lines):
                raise FormatError(f"missing {FILE_CLOSE} for {path!r}")
            content = "\n".join(buf) + "\n" if buf else ""
            specs.append(FileSpec(path=path, content=content))
        i += 1
    if not specs:
        raise FormatError(f"no {FILE_OPEN}...>>> blocks found in the message")
    return specs


def validate_paths(specs: list[FileSpec], project_root: Path) -> None:
    """Reject unsafe paths before any write happens.

    A path is unsafe if it is absolute, contains `..`, or resolves
    outside `project_root`. The check runs on all specs before any
    file is written, so a bad path in spec #5 does not leave specs
    #1–4 on disk.
    """
    for spec in specs:
        # Why: on Windows, `Path("/foo")` has a root but no drive, so
        # `is_absolute()` returns False. A leading separator still
        # means "outside the project", so it is rejected explicitly.
        if spec.path.startswith(("/", "\\")):
            raise FormatError(f"absolute path not allowed: {spec.path!r}")
        p = Path(spec.path)
        if p.is_absolute():
            raise FormatError(f"absolute path not allowed: {spec.path!r}")
        if ".." in p.parts:
            raise FormatError(f"parent traversal not allowed: {spec.path!r}")
        resolved = (project_root / p).resolve()
        if not resolved.is_relative_to(project_root.resolve()):
            raise FormatError(f"path escapes project root: {spec.path!r}")


def detect_marker_collision(spec: FileSpec) -> None:
    """Raise `FormatError` if `spec.content` would break the parser.

    A content that contains the literal `<<<END>>>` on its own line
    (modulo trailing whitespace) would be interpreted as the closing
    marker on a subsequent re-parse. The parser cannot distinguish
    the two. Refusing the step is safer than writing a file that
    breaks future tooling.

    A literal `<<<FILE:...>>>` line inside content is *not* a
    problem: the parser tracks whether it is inside a block, so an
    opening marker only counts when it appears outside one.
    """
    for line in spec.content.split("\n"):
        if line.rstrip() == FILE_CLOSE:
            raise FormatError(
                f"content of {spec.path!r} contains a bare "
                f"{FILE_CLOSE!r} line, which would break the parser"
            )


def format_step(number: int) -> str:
    """Return the canonical filename fragment for a step number.

    Two digits for numbers below 100, more when needed: `1` -> `01`,
    `100` -> `100`. Every command that builds `step-NN.txt`,
    `apply-NN.log`, or `report-NN.txt` goes through this function so
    the names agree across commands.
    """
    return f"{number:02d}"


def parse_step_arg(raw: str) -> int:
    """Parse a step argument into a canonical positive integer.

    Accepts `1`, `01`, `001`. Rejects non-integers and non-positive
    values with `FormatError`. Callers convert to exit code 2 for
    CLI input; internal callers let it propagate.
    """
    try:
        n = int(raw)
    except (TypeError, ValueError) as exc:
        raise FormatError(f"step must be a positive integer, got {raw!r}") from exc
    if n < 1:
        raise FormatError(f"step must be >= 1, got {n}")
    return n


def report_sort_key(path: Path) -> int:
    """Return the numeric step number from a `report-NN.txt` filename.

    Non-matching names sort to -1 so they end up first under
    `sorted(..., key=report_sort_key)`. `[-n:]` then picks the
    numerically newest reports, not the lexicographically newest
    (`report-1.txt, report-10.txt, report-2.txt, ...`).
    """
    match = _REPORT_RE.match(path.name)
    if match is None:
        return -1
    return int(match.group(1))


def render_report(report: Report) -> str:
    """Render a `Report` as a markdown document.

    Section order is fixed. Empty sections are still printed so the
    reader can see that a check produced no output, rather than
    wondering if it was skipped.
    """
    lines: list[str] = []
    lines.append(f"=== Step {report.step_number:02d} report ===")
    lines.append("")

    lines.append("apply output:")
    lines.append(report.apply_log or "(empty)")
    lines.append("")

    lines.append("verify commands:")
    if not report.checks:
        lines.append("(none configured)")
    else:
        for check in report.checks:
            lines.append(f"$ {' '.join(check.command)}")
            if check.stdout:
                lines.append(check.stdout.rstrip())
            if check.stderr:
                lines.append("[stderr]")
                lines.append(check.stderr.rstrip())
            lines.append(
                f"exit: {check.exit_code}{'' if check.required else ' (optional)'}"
            )
            lines.append("")

    lines.append("commit:")
    if report.commit_hash:
        lines.append(f"{report.commit_hash} {report.commit_message}")
    else:
        lines.append("not committed")
    lines.append("")

    if report.roadmap_position is not None:
        before, after = report.roadmap_position
        lines.append(f"roadmap position: {before} -> {after}")
        lines.append("")

    lines.append("deviations:")
    if not report.deviations:
        lines.append("(none)")
    else:
        for dev in report.deviations:
            lines.append(summarize_deviation(dev))
    lines.append("")

    lines.append("notes:")
    lines.append(report.notes or "(fill)")
    lines.append("")

    lines.append("question for AI:")
    lines.append(report.question or "(none)")
    lines.append("")
    return "\n".join(lines)


def summarize_check(check: CheckResult) -> str:
    """One-line summary of a `CheckResult` for the CLI's stdout.

    Used by `verify` to print a progress line before writing the
    full report.
    """
    status = "OK" if check.exit_code == 0 else f"FAIL({check.exit_code})"
    suffix = "" if check.required else " optional"
    return f"{check.name}: {status}{suffix}"


def summarize_deviation(dev: Deviation) -> str:
    """One-line summary of a `Deviation` for the report body."""
    affected = ", ".join(dev.affected) or "-"
    flag = "auto" if dev.auto else "declared"
    detail = f" — {dev.detail}" if dev.detail else ""
    return f"- {dev.type.value} ({flag}): {affected} — {dev.reason}{detail}"


__all__ = [
    "FILE_CLOSE",
    "FILE_OPEN",
    "detect_marker_collision",
    "format_step",
    "parse_step_arg",
    "parse_step_message",
    "render_report",
    "report_sort_key",
    "summarize_check",
    "summarize_deviation",
    "validate_paths",
]
