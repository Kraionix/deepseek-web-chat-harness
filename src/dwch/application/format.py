"""Parse step messages and render reports.

The step format is fixed and minimal: blocks delimited by
`<<<FILE:path>>>` and `<<<END>>>`. Everything outside a block is
ignored. There is no escaping and no nesting; the parser is a
single forward scan.
"""

from __future__ import annotations

from pathlib import Path

from ..domain.models import CheckResult, FileSpec, Report
from ..shared.errors import FormatError

FILE_OPEN = "<<<FILE:"
FILE_CLOSE = "<<<END>>>"


def parse_step_message(text: str) -> list[FileSpec]:
    """Parse a step message into a list of `FileSpec`.

    Preconditions: `text` is the raw content of the AI's message.
    Postconditions: a list of `(path, content)` pairs, in the order
    the blocks appeared.

    Raises `FormatError` on an unclosed block, an empty path, or a
    path that is not relative.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    specs: list[FileSpec] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(FILE_OPEN) and line.endswith(">>>"):
            path = line[len(FILE_OPEN) : -3].strip()
            if not path:
                raise FormatError(f"empty path at line {i + 1}")
            i += 1
            buf: list[str] = []
            while i < len(lines) and lines[i] != FILE_CLOSE:
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
    would be interpreted as the closing marker on a subsequent
    re-parse. The parser cannot distinguish the two. Refusing the
    step is safer than writing a file that breaks future tooling.
    """
    for line in spec.content.split("\n"):
        if line == FILE_CLOSE:
            raise FormatError(
                f"content of {spec.path!r} contains a bare "
                f"{FILE_CLOSE!r} line, which would break the parser"
            )


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


__all__ = [
    "FILE_CLOSE",
    "FILE_OPEN",
    "detect_marker_collision",
    "parse_step_message",
    "render_report",
    "summarize_check",
    "validate_paths",
]
