"""Tests for `application.format`."""

from __future__ import annotations

from pathlib import Path

import pytest

from dwch.application.format import (
    detect_marker_collision,
    format_step,
    is_protected,
    op_paths,
    op_written_paths,
    parse_step_arg,
    parse_step_message,
    render_report,
    report_sort_key,
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

# ---------------------------------------------------------------------------
# parse_step_message — FILE
# ---------------------------------------------------------------------------


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
    ops = parse_step_message(text)
    assert ops[0].content == "x = 1\n"


def test_parse_open_marker_with_trailing_space() -> None:
    """An open marker with trailing whitespace is recognized."""
    text = "<<<FILE:a.py>>>   \nx = 1\n<<<END>>>\n"
    ops = parse_step_message(text)
    assert ops[0].path == "a.py"


# ---------------------------------------------------------------------------
# parse_step_message — DELETE
# ---------------------------------------------------------------------------


def test_parse_delete_block() -> None:
    """A DELETE block parses to a DeleteOp with an empty body."""
    text = "<<<DELETE:src/old.py>>>\n<<<END>>>\n"
    ops = parse_step_message(text)
    assert len(ops) == 1
    assert isinstance(ops[0], DeleteOp)
    assert ops[0].path == "src/old.py"


def test_parse_delete_block_with_blank_body() -> None:
    """Whitespace-only lines in the DELETE body are tolerated."""
    text = "<<<DELETE:src/old.py>>>\n   \n\t\n<<<END>>>\n"
    ops = parse_step_message(text)
    assert isinstance(ops[0], DeleteOp)


def test_parse_delete_with_non_empty_body_is_error() -> None:
    """Any printable content in the DELETE body is a format error."""
    text = "<<<DELETE:src/old.py>>>\nfoo\n<<<END>>>\n"
    with pytest.raises(FormatError, match="DELETE body must be empty"):
        parse_step_message(text)


def test_parse_delete_empty_path() -> None:
    """An empty DELETE path raises."""
    with pytest.raises(FormatError, match="empty path"):
        parse_step_message("<<<DELETE:>>>\n<<<END>>>\n")


# ---------------------------------------------------------------------------
# parse_step_message — MOVE
# ---------------------------------------------------------------------------


def test_parse_move_block() -> None:
    """A MOVE block parses to a MoveOp with src and dst."""
    text = "<<<MOVE:src/a.py:src/b.py>>>\n<<<END>>>\n"
    ops = parse_step_message(text)
    assert len(ops) == 1
    assert isinstance(ops[0], MoveOp)
    assert ops[0].src == "src/a.py"
    assert ops[0].dst == "src/b.py"


def test_parse_move_with_non_empty_body_is_error() -> None:
    """Any printable content in the MOVE body is a format error."""
    text = "<<<MOVE:a.py:b.py>>>\nfoo\n<<<END>>>\n"
    with pytest.raises(FormatError, match="MOVE body must be empty"):
        parse_step_message(text)


def test_parse_move_with_extra_colon_is_error() -> None:
    """A second `:` in the MOVE marker is a format error."""
    text = "<<<MOVE:a.py:b.py:c.py>>>\n<<<END>>>\n"
    with pytest.raises(FormatError, match="exactly one ':'"):
        parse_step_message(text)


def test_parse_move_with_empty_side_is_error() -> None:
    """An empty side of the MOVE separator is a format error."""
    text = "<<<MOVE:a.py:>>>\n<<<END>>>\n"
    with pytest.raises(FormatError, match="two non-empty paths"):
        parse_step_message(text)


# ---------------------------------------------------------------------------
# parse_step_message — keyword and uniqueness
# ---------------------------------------------------------------------------


def test_parse_lowercase_file_keyword_is_error() -> None:
    """`<<<file:` is not recognized, and `<<<x:` looks like an unknown block."""
    # Lowercase does not match FILE_OPEN, so the parser falls through.
    # The line has both `<` markers and a `:`, so it is rejected as an
    # unknown keyword.
    text = "<<<file:a.py>>>\nx = 1\n<<<END>>>\n"
    with pytest.raises(FormatError):
        parse_step_message(text)


def test_parse_duplicate_path_across_ops() -> None:
    """A path appearing in two ops is refused."""
    text = "<<<FILE:a.py>>>\n1\n<<<END>>>\n<<<DELETE:a.py>>>\n<<<END>>>\n"
    with pytest.raises(FormatError, match="duplicate path"):
        parse_step_message(text)


def test_parse_duplicate_path_move_overlap() -> None:
    """A MOVE whose dst equals another op's path is refused."""
    text = "<<<FILE:b.py>>>\n1\n<<<END>>>\n<<<MOVE:a.py:b.py>>>\n<<<END>>>\n"
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


# ---------------------------------------------------------------------------
# op_paths / op_written_paths
# ---------------------------------------------------------------------------


def test_op_paths_write() -> None:
    """A WriteOp touches one path."""
    assert op_paths(WriteOp(path="a.py", content="")) == ("a.py",)


def test_op_paths_delete() -> None:
    """A DeleteOp touches one path."""
    assert op_paths(DeleteOp(path="a.py")) == ("a.py",)


def test_op_paths_move() -> None:
    """A MoveOp touches two paths."""
    assert op_paths(MoveOp(src="a.py", dst="b.py")) == ("a.py", "b.py")


def test_op_written_paths_write() -> None:
    """A WriteOp contributes its path."""
    assert op_written_paths(WriteOp(path="a.py", content="")) == ("a.py",)


def test_op_written_paths_delete() -> None:
    """A DeleteOp contributes nothing."""
    assert op_written_paths(DeleteOp(path="a.py")) == ()


def test_op_written_paths_move() -> None:
    """A MoveOp contributes only its destination."""
    assert op_written_paths(MoveOp(src="a.py", dst="b.py")) == ("b.py",)


# ---------------------------------------------------------------------------
# validate_paths
# ---------------------------------------------------------------------------


def test_validate_paths_accepts_write(tmp_path: Path) -> None:
    """A normal relative WriteOp path passes."""
    validate_paths([WriteOp(path="src/a.py", content="")], tmp_path)


def test_validate_paths_accepts_delete_move(tmp_path: Path) -> None:
    """Delete and Move paths go through the same validator."""
    validate_paths(
        [
            DeleteOp(path="src/a.py"),
            MoveOp(src="src/b.py", dst="src/c.py"),
        ],
        tmp_path,
    )


def test_validate_paths_rejects_parent_traversal(tmp_path: Path) -> None:
    """`..` in a WriteOp path is refused."""
    with pytest.raises(FormatError, match="invalid path component"):
        validate_paths([WriteOp(path="../x.py", content="")], tmp_path)


def test_validate_paths_rejects_move_dst_traversal(tmp_path: Path) -> None:
    """`..` in a MoveOp destination is refused."""
    with pytest.raises(FormatError, match="invalid path component"):
        validate_paths([MoveOp(src="a.py", dst="../x.py")], tmp_path)


def test_validate_paths_rejects_reserved(tmp_path: Path) -> None:
    """A Windows reserved name is refused."""
    with pytest.raises(FormatError, match="reserved Windows name"):
        validate_paths([WriteOp(path="src/CON", content="")], tmp_path)


# ---------------------------------------------------------------------------
# detect_marker_collision
# ---------------------------------------------------------------------------


def test_detect_marker_collision_bare_end() -> None:
    """A bare `<<<END>>>` line inside content is rejected."""
    op = WriteOp(path="a.py", content="before\n<<<END>>>\nafter\n")
    with pytest.raises(FormatError, match="bare"):
        detect_marker_collision(op)


def test_detect_marker_collision_bare_end_with_space() -> None:
    """A bare `<<<END>>>` with trailing whitespace is rejected."""
    op = WriteOp(path="a.py", content="before\n<<<END>>>   \nafter\n")
    with pytest.raises(FormatError, match="bare"):
        detect_marker_collision(op)


def test_detect_marker_collision_file_open_ok() -> None:
    """A `<<<FILE:...>>>` line inside content is allowed."""
    op = WriteOp(
        path="a.py",
        content="docstring example:\n<<<FILE:foo>>>\nreal content\n",
    )
    detect_marker_collision(op)


# ---------------------------------------------------------------------------
# is_protected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".harness/state.toml",
        ".harness/config.toml",
        ".harness/roadmap.lock",
        ".harness/roadmap.toml",
        ".harness/.gitignore",
        "steps/phase-01/step-01.txt",
        "steps/.gitignore",
    ],
)
def test_is_protected_true(path: str) -> None:
    """Every listed protected path is refused."""
    assert is_protected(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",
        ".harness/handoff.md",
        ".harness/summaries/p1.md",
        ".harness/deviations/step-01.toml",
        "src/steps/foo.py",
    ],
)
def test_is_protected_false(path: str) -> None:
    """Normal paths and adjacent paths are not protected."""
    assert not is_protected(path)


# ---------------------------------------------------------------------------
# format_step / parse_step_arg / report_sort_key
# ---------------------------------------------------------------------------


def test_format_step_single_digit() -> None:
    """A single-digit step gets a leading zero."""
    assert format_step(1) == "01"
    assert format_step(9) == "09"


def test_format_step_two_digits() -> None:
    """A two-digit step is unchanged."""
    assert format_step(10) == "10"
    assert format_step(99) == "99"


def test_format_step_three_digits() -> None:
    """A three-digit step is not truncated."""
    assert format_step(100) == "100"


def test_parse_step_arg_integer() -> None:
    """A plain integer is parsed."""
    assert parse_step_arg("1") == 1
    assert parse_step_arg("42") == 42


def test_parse_step_arg_leading_zeros() -> None:
    """Leading zeros do not change the value."""
    assert parse_step_arg("01") == 1
    assert parse_step_arg("001") == 1


def test_parse_step_arg_zero() -> None:
    """Zero is rejected."""
    with pytest.raises(FormatError, match="must be >= 1"):
        parse_step_arg("0")


def test_parse_step_arg_negative() -> None:
    """A negative number is rejected."""
    with pytest.raises(FormatError, match="must be >= 1"):
        parse_step_arg("-1")


def test_parse_step_arg_non_integer() -> None:
    """A non-integer is rejected."""
    with pytest.raises(FormatError, match="positive integer"):
        parse_step_arg("abc")


def test_report_sort_key_numeric_order() -> None:
    """`report-2.txt` sorts before `report-10.txt`."""
    a = report_sort_key(Path("report-2.txt"))
    b = report_sort_key(Path("report-10.txt"))
    assert a < b


def test_report_sort_key_no_match() -> None:
    """A name that does not match sorts first."""
    assert report_sort_key(Path("other.txt")) == -1


# ---------------------------------------------------------------------------
# render_report and summaries
# ---------------------------------------------------------------------------


def test_render_report_minimal() -> None:
    """The report includes every section header."""
    report = Report(
        step_number=1,
        apply_log="apply\n",
        checks=(),
        commit_hash=None,
        commit_message=None,
        deviations=(),
        roadmap_position=None,
        notes="",
        question="",
    )
    text = render_report(report)
    assert "=== Step 01 report ===" in text
    assert "commit:\nnot committed" in text
    assert "deviations:\n(none)" in text


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
    """The summary names type, flag, affected files, and reason."""
    dev = Deviation(
        type=DeviationType.ASSUMPTION,
        affected=("a.py",),
        reason="missing spec",
        detail="",
        auto=False,
    )
    assert summarize_deviation(dev) == ("- assumption (declared): a.py — missing spec")


def test_summarize_extra_move_deviation() -> None:
    """The extra-move deviation renders with its affected pair list."""
    dev = Deviation(
        type=DeviationType.EXTRA_MOVE,
        affected=("a.py -> b.py",),
        reason="auto-detected by verify",
        detail="",
        auto=True,
    )
    text = summarize_deviation(dev)
    assert "extra-move" in text
    assert "auto" in text
    assert "a.py -> b.py" in text
