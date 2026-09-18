"""Parse block messages and render reports.

The block format has three kinds, delimited by `<<<FILE:path>>>`,
`<<<DELETE:path>>>`, and `<<<MOVE:src:dst>>>`, each closed by
`<<<END>>>`. Everything outside a block is ignored. There is no
escaping and no nesting; the parser is a single forward scan that
tracks whether it is inside a block, so a literal `<<<FILE:...>>>`
line inside content is not a marker.
"""

from __future__ import annotations

from ..domain.models import (
    CheckResult,
    DeleteOp,
    Deviation,
    MoveOp,
    Report,
    StepOp,
    WriteOp,
    op_paths,
    op_written_paths,
)
from ..shared.errors import FormatError
from ..shared.paths import normalize_rel, safe_path

FILE_OPEN = "<<<FILE:"
DELETE_OPEN = "<<<DELETE:"
MOVE_OPEN = "<<<MOVE:"
FILE_CLOSE = "<<<END>>>"

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_MESSAGE_BYTES = 50 * 1024 * 1024
MAX_SNAPSHOT_TOTAL_BYTES = 50 * 1024 * 1024


def parse_step_message(text: str) -> list[StepOp]:
    """Parse a block message into a list of `StepOp`.

    Pre:  `text` is the raw content of the AI's message.
    Post: returns a list of ops, in the order the blocks appeared.
          Every path is unique across every op.
    Raises: `FormatError` on an oversized message, an unclosed
          block, an empty path, a duplicate path, a non-empty
          `DELETE` or `MOVE` body, a `MOVE` without exactly one
          `:`, an unknown keyword, or no blocks at all.
    """
    if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise FormatError(
            f"message is {len(text.encode('utf-8'))} bytes; "
            f"limit is {MAX_MESSAGE_BYTES}"
        )

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ops: list[StepOp] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        if stripped.startswith(FILE_OPEN) and stripped.endswith(">>>"):
            path = stripped[len(FILE_OPEN) : -3].strip()
            if not path:
                raise FormatError(f"empty path at line {i + 1}")
            i += 1
            buf: list[str] = []
            while i < len(lines) and lines[i].rstrip() != FILE_CLOSE:
                buf.append(lines[i])
                i += 1
            if i >= len(lines):
                raise FormatError(f"missing {FILE_CLOSE} for {path!r}")
            content = "\n".join(buf) + "\n" if buf else ""
            if len(content.encode("utf-8")) > MAX_FILE_BYTES:
                raise FormatError(
                    f"file {path!r} is {len(content.encode('utf-8'))} bytes; "
                    f"limit is {MAX_FILE_BYTES}"
                )
            ops.append(WriteOp(path=path, content=content))

        elif stripped.startswith(DELETE_OPEN) and stripped.endswith(">>>"):
            path = stripped[len(DELETE_OPEN) : -3].strip()
            if not path:
                raise FormatError(f"empty path at line {i + 1}")
            i += 1
            while i < len(lines) and lines[i].rstrip() != FILE_CLOSE:
                if lines[i].strip():
                    raise FormatError(
                        f"DELETE body must be empty for {path!r} (line {i + 1})"
                    )
                i += 1
            if i >= len(lines):
                raise FormatError(f"missing {FILE_CLOSE} for {path!r}")
            ops.append(DeleteOp(path=path))

        elif stripped.startswith(MOVE_OPEN) and stripped.endswith(">>>"):
            inner = stripped[len(MOVE_OPEN) : -3]
            if inner.count(":") != 1:
                raise FormatError(f"MOVE requires exactly one ':' separator: {inner!r}")
            src, dst = inner.split(":", 1)
            src = src.strip()
            dst = dst.strip()
            if not src or not dst:
                raise FormatError(f"MOVE requires two non-empty paths: {inner!r}")
            i += 1
            while i < len(lines) and lines[i].rstrip() != FILE_CLOSE:
                if lines[i].strip():
                    raise FormatError(
                        f"MOVE body must be empty for {src!r} (line {i + 1})"
                    )
                i += 1
            if i >= len(lines):
                raise FormatError(f"missing {FILE_CLOSE} for {src!r}")
            ops.append(MoveOp(src=src, dst=dst))

        elif (
            stripped.startswith("<<<") and stripped.endswith(">>>") and ":" in stripped
        ):
            raise FormatError(f"unknown block keyword at line {i + 1}: {stripped!r}")

        i += 1

    if not ops:
        raise FormatError(f"no {FILE_OPEN}...>>> blocks found in the message")

    _check_unique_paths(ops)
    return ops


def _check_unique_paths(ops: list[StepOp]) -> None:
    """Reject a message where any path appears in more than one op."""
    seen: set[str] = set()
    for op in ops:
        for p in op_paths(op):
            norm = normalize_rel(p)
            if norm in seen:
                raise FormatError(f"duplicate path {p!r}")
            seen.add(norm)


def validate_paths(ops: list[StepOp], project_root) -> None:
    """Reject unsafe paths before any write happens.

    Every path of every op goes through `safe_path`, the single
    validator. The check runs on all ops before any file is
    written, so a bad path in op #5 does not leave ops #1–4 on
    disk.
    """
    resolved_root = project_root.resolve(strict=False)
    for op in ops:
        for p in op_paths(op):
            safe_path(p, resolved_root)


def detect_marker_collision(op: WriteOp) -> None:
    """Raise `FormatError` if `op.content` would break the parser.

    A content that contains the literal `<<<END>>>` on its own line
    (modulo trailing whitespace) would be interpreted as the closing
    marker on a subsequent re-parse. The parser cannot distinguish
    the two. Refusing the message is safer than writing a file that
    breaks future tooling.

    A literal `<<<FILE:...>>>` line inside content is *not* a
    problem: the parser tracks whether it is inside a block, so an
    opening marker only counts when it appears outside one.
    """
    for line in op.content.split("\n"):
        if line.rstrip() == FILE_CLOSE:
            raise FormatError(
                f"content of {op.path!r} contains a bare "
                f"{FILE_CLOSE!r} line, which would break the parser"
            )


def render_report(report: Report) -> str:
    """Render a `Report` as a markdown document.

    Section order is fixed. Empty sections are still printed so the
    reader can see that a check produced no output, rather than
    wondering if it was skipped.
    """
    lines: list[str] = []
    lines.append(f"=== Task {report.task_id} report (attempt {report.attempt}) ===")
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

    if report.plan_position is not None:
        before, after = report.plan_position
        lines.append(f"plan position: {before} -> {after}")
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


def render_hint(report: Report) -> str:
    """Render a short hint (≤10 lines) placed on the clipboard.

    The hint names the first failing required check and the two
    ways forward: `dwch fix` for a fresh fix-bootstrap, or fix and
    re-run `apply` + `verify`. The full report is on disk.
    """
    lines: list[str] = [
        f"verify FAILED: task {report.task_id} (attempt {report.attempt})",
    ]
    first_failed = next(
        (c for c in report.checks if c.exit_code != 0 and c.required),
        None,
    )
    if first_failed is not None:
        lines.append(f"  first failure: {first_failed.name}")
        excerpt = (first_failed.stdout or first_failed.stderr or "").splitlines()
        for ln in excerpt[:3]:
            lines.append(f"    {ln}")
    if report.commit_hash is None:
        lines.append("commit: skipped")
    lines.append("")
    lines.append("Next:")
    lines.append("  - `dwch fix`  (fix-bootstrap for a fresh chat)")
    lines.append("  - or fix and re-run `dwch apply` then `dwch verify`")
    lines.append(
        f"  - or declare a deviation at .harness/deviations/{report.task_id}.toml"
    )
    return "\n".join(lines[:10])


def summarize_check(check: CheckResult) -> str:
    """One-line summary of a `CheckResult` for the CLI's stdout."""
    status = "OK" if check.exit_code == 0 else f"FAIL({check.exit_code})"
    suffix = "" if check.required else " optional"
    return f"{check.name}: {status}{suffix}"


def summarize_deviation(dev: Deviation) -> str:
    """One-line summary of a `Deviation` for the report body."""
    affected = ", ".join(dev.affected) or "-"
    detail = f" — {dev.detail}" if dev.detail else ""
    return f"- {dev.type.value}: {affected} — {dev.reason}{detail}"


__all__ = [
    "DELETE_OPEN",
    "FILE_CLOSE",
    "FILE_OPEN",
    "MAX_FILE_BYTES",
    "MAX_MESSAGE_BYTES",
    "MAX_SNAPSHOT_TOTAL_BYTES",
    "MOVE_OPEN",
    "detect_marker_collision",
    "op_paths",
    "op_written_paths",
    "parse_step_message",
    "render_hint",
    "render_report",
    "summarize_check",
    "summarize_deviation",
    "validate_paths",
]
