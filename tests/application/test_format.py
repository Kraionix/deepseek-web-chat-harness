"""Tests for `application.format`."""

from __future__ import annotations

from pathlib import Path

import pytest

from dwch.application.format import (
    detect_marker_collision,
    op_paths,
    op_written_paths,
    parse_step_message,
    render_hint,
    render_report,
    summarize_check,
    summarize_deviation,
    validate_paths,
)
from dwch.domain.models import (
    CheckResult,
    DeleteOp,
    Deviation,
    DeviationType,
    MoveOp,
    Report,
    WriteOp,
)
from dwch.shared.errors import FormatError


def test_parse_single_file_block() -> None:
    """One FILE block parses to one WriteOp with a trailing newline."""
    text = "<<<FILE:src/a.py>>>\nx = 1\n<<<END>>>\n"
    ops = parse_step_message(text)
    assert len(ops) == 1
    assert isinstance(ops[0], WriteOp)
    assert ops[0].path == "src/a.py"
    assert ops[0].content == "x = 1\n"


def test_parse_multiple_file_blocks() -> None:
    """Blocks preserve their order."""
    text = "<<<FILE:a.py>>>\n1\n<<<END>>>\n<<<FILE:b.py>>>\n2\n<<<END>>>\n"
    ops = parse_step_message(text)
    assert [o.path for o in ops] == ["a.py", "b.py"]


def test_parse_crlf() -> None:
    """Windows line endings do not leak into content."""
    text = "<<<FILE:a.py>>>\r\nx\r\n<<<END>>>\r\n"
    ops = parse_step_message(text)
    assert ops[0].content == "x\n"


def test_parse_empty_file_content() -> None:
    """A block with no lines between markers yields empty content."""
    text = "<<<FILE:empty.txt>>>\n<<<END>>>\n"
    ops = parse_step_message(text)
    assert ops[0].content == ""


def test_parse_no_blocks() -> None:
    """Text without blocks raises `FormatError`."""
    with pytest.raises(FormatError, match="no "):
        parse_step_message("just prose\n")


def test_parse_unclosed_file_block() -> None:
    """A missing close marker raises `FormatError`."""
    with pytest.raises(FormatError, match="missing"):
        parse_step_message("<<<FILE:a.py>>>\nx\n")


def test_parse_empty_path() -> None:
    """An empty path raises `FormatError`."""
    with pytest.raises(FormatError, match="empty path"):
        parse_step_message("<<<FILE:>>>\nx\n<<<END>>>\n")


def test_parse_ignores_prose() -> None:
    """Prose outside blocks does not interfere."""
    text = "Here we go.\n<<<FILE:a.py>>>\n1\n<<<END>>>\nThat was the file.\n"
    assert len(parse_step_message(text)) == 1


def test_parse_close_marker_with_trailing_space() -> None:
    """A close marker with trailing whitespace is recognized."""
    text = "<<<FILE:a.py>>>\nx = 1\n<<<END>>>   \n"
    assert parse_step_message(text)[0].content == "x = 1\n"


def test_parse_delete_block() -> None:
    """A DELETE block parses to a DeleteOp with an empty body."""
    text = "<<<DELETE:src/old.py>>>\n<<<END>>>\n"
    ops = parse_step_message(text)
    assert isinstance(ops[0], DeleteOp)
    assert ops[0].path == "src/old.py"


def test_parse_delete_with_non_empty_body_is_error() -> None:
    """Any printable content in the DELETE body is a format error."""
    text = "<<<DELETE:src/old.py>>>\nfoo\n<<<END>>>\n"
    with pytest.raises(FormatError, match="DELETE body must be empty"):
        parse_step_message(text)


def test_parse_move_block() -> None:
    """A MOVE block parses to a MoveOp with src and dst."""
    text = "<<<MOVE:src/a.py:src/b.py>>>\n<<<END>>>\n"
    ops = parse_step_message(text)
    assert isinstance(ops[0], MoveOp)
    assert ops[0].src == "src/a.py"
    assert ops[0].dst == "src/b.py"


def test_parse_move_with_extra_colon_is_error() -> None:
    """A second `:` in the MOVE marker is a format error."""
    text = "<<<MOVE:a.py:b.py:c.py>>>\n<<<END>>>\n"
    with pytest.raises(FormatError, match="exactly one ':'"):
        parse_step_message(text)


def test_parse_duplicate_path_across_ops() -> None:
    """A path appearing in two ops is refused."""
    text = "<<<FILE:a.py>>>\n1\n<<<END>>>\n<<<DELETE:a.py>>>\n<<<END>>>\n"
    with pytest.raises(FormatError, match="duplicate path"):
        parse_step_message(text)


def test_parse_three_ops_in_order() -> None:
    """A message with all three block kinds parses in order."""
    text = (
        "<<<FILE:a.py>>>\n1\n<<<END>>>\n"
        "<<<MOVE:b.py:c.py>>>\n<<<END>>>\n"
        "<<<DELETE:d.py>>>\n<<<END>>>\n"
    )
    ops = parse_step_message(text)
    assert isinstance(ops[0], WriteOp)
    assert isinstance(ops[1], MoveOp)
    assert isinstance(ops[2], DeleteOp)


def test_op_paths_write() -> None:
    """A WriteOp touches one path."""
    assert op_paths(WriteOp(path="a.py", content="")) == ("a.py",)


def test_op_paths_move() -> None:
    """A MoveOp touches two paths."""
    assert op_paths(MoveOp(src="a.py", dst="b.py")) == ("a.py", "b.py")


def test_op_written_paths_delete() -> None:
    """A DeleteOp contributes nothing."""
    assert op_written_paths(DeleteOp(path="a.py")) == ()


def test_op_written_paths_move() -> None:
    """A MoveOp contributes only its destination."""
    assert op_written_paths(MoveOp(src="a.py", dst="b.py")) == ("b.py",)


def test_validate_paths_rejects_parent_traversal(tmp_path: Path) -> None:
    """`..` in a WriteOp path is refused."""
    with pytest.raises(FormatError, match="invalid path component"):
        validate_paths([WriteOp(path="../x.py", content="")], tmp_path)


def test_detect_marker_collision_bare_end() -> None:
    """A bare `<<<END>>>` line inside content is rejected."""
    op = WriteOp(path="a.py", content="before\n<<<END>>>\nafter\n")
    with pytest.raises(FormatError, match="bare"):
        detect_marker_collision(op)


def test_detect_marker_collision_file_open_ok() -> None:
    """A `<<<FILE:...>>>` line inside content is allowed."""
    op = WriteOp(
        path="a.py",
        content="docstring example:\n<<<FILE:foo>>>\nreal content\n",
    )
    detect_marker_collision(op)


def test_render_report_minimal() -> None:
    """The report includes every section header."""
    report = Report(
        task_id="models",
        attempt=1,
        apply_log="apply\n",
        checks=(),
        commit_hash=None,
        commit_message=None,
        deviations=(),
        plan_position=None,
        notes="",
        question="",
    )
    text = render_report(report)
    assert "=== Task models report (attempt 1) ===" in text
    assert "commit:\nnot committed" in text
    assert "deviations:\n(none)" in text


def test_render_hint_failing_check() -> None:
    """The hint names the first failing required check."""
    report = Report(
        task_id="t1",
        attempt=2,
        apply_log="",
        checks=(
            CheckResult(
                name="compile",
                command=("compile",),
                exit_code=1,
                stdout="a.py: syntax error",
                stderr="",
                required=True,
            ),
        ),
        commit_hash=None,
        commit_message=None,
        deviations=(),
        plan_position=None,
        notes="",
        question="",
    )
    hint = render_hint(report)
    assert "verify FAILED: task t1 (attempt 2)" in hint
    assert "compile" in hint
    assert "dwch fix" in hint
    assert "a.py: syntax error" in hint


def test_render_hint_is_at_most_ten_lines() -> None:
    """The hint is at most ten lines."""
    report = Report(
        task_id="t",
        attempt=1,
        apply_log="",
        checks=(
            CheckResult(
                name="x",
                command=("x",),
                exit_code=1,
                stdout="\n".join(str(i) for i in range(50)),
                stderr="",
                required=True,
            ),
        ),
        commit_hash=None,
        commit_message=None,
        deviations=(),
        plan_position=None,
        notes="",
        question="",
    )
    hint = render_hint(report)
    assert len(hint.splitlines()) <= 10


def test_summarize_check() -> None:
    """The summary is one line with a status and optional flag."""
    ok = CheckResult(
        name="x",
        command=("x",),
        exit_code=0,
        stdout="",
        stderr="",
        required=True,
    )
    assert summarize_check(ok) == "x: OK"
    optional = CheckResult(
        name="y",
        command=("y",),
        exit_code=1,
        stdout="",
        stderr="",
        required=False,
    )
    assert summarize_check(optional) == "y: FAIL(1) optional"


def test_summarize_deviation() -> None:
    """The summary names type, affected files, and reason."""
    dev = Deviation(
        type=DeviationType.ASSUMPTION,
        affected=("a.py",),
        reason="missing spec",
        detail="",
    )
    assert summarize_deviation(dev) == "- assumption: a.py — missing spec"
