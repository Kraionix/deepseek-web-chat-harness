"""Tests for `application.format`."""

from __future__ import annotations

from pathlib import Path

import pytest

from dwch.application.format import (
    detect_marker_collision,
    format_step,
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
    Deviation,
    DeviationType,
    FileSpec,
    Report,
)
from dwch.shared.errors import FormatError


def test_parse_single_block() -> None:
    """One block parses to one spec with a trailing newline."""
    text = "<<<FILE:src/a.py>>>\nx = 1\n<<<END>>>\n"
    specs = parse_step_message(text)
    assert len(specs) == 1
    assert specs[0].path == "src/a.py"
    assert specs[0].content == "x = 1\n"


def test_parse_multiple_blocks() -> None:
    """Blocks preserve their order."""
    text = "<<<FILE:a.py>>>\n1\n<<<END>>>\n<<<FILE:b.py>>>\n2\n<<<END>>>\n"
    specs = parse_step_message(text)
    assert [s.path for s in specs] == ["a.py", "b.py"]


def test_parse_crlf() -> None:
    """Windows line endings do not leak into content."""
    text = "<<<FILE:a.py>>>\r\nx\r\n<<<END>>>\r\n"
    specs = parse_step_message(text)
    assert specs[0].content == "x\n"


def test_parse_empty_content() -> None:
    """A block with no lines between markers yields empty content."""
    text = "<<<FILE:empty.txt>>>\n<<<END>>>\n"
    specs = parse_step_message(text)
    assert specs[0].content == ""


def test_parse_no_blocks() -> None:
    """Text without blocks raises `FormatError`."""
    with pytest.raises(FormatError, match="no "):
        parse_step_message("just prose\n")


def test_parse_unclosed_block() -> None:
    """A missing close marker raises `FormatError`."""
    with pytest.raises(FormatError, match="missing"):
        parse_step_message("<<<FILE:a.py>>>\nx\n")


def test_parse_empty_path() -> None:
    """An empty path raises `FormatError`."""
    with pytest.raises(FormatError, match="empty path"):
        parse_step_message("<<<FILE:>>>\nx\n<<<END>>>\n")


def test_parse_duplicate_path() -> None:
    """A duplicate path raises `FormatError`."""
    text = "<<<FILE:a.py>>>\n1\n<<<END>>>\n<<<FILE:a.py>>>\n2\n<<<END>>>\n"
    with pytest.raises(FormatError, match="duplicate path"):
        parse_step_message(text)


def test_parse_ignores_prose() -> None:
    """Prose outside blocks does not interfere."""
    text = "Here we go.\n<<<FILE:a.py>>>\n1\n<<<END>>>\nThat was the file.\n"
    assert len(parse_step_message(text)) == 1


def test_parse_close_marker_with_trailing_space() -> None:
    """A close marker with trailing whitespace is recognized."""
    text = "<<<FILE:a.py>>>\nx = 1\n<<<END>>>   \n"
    specs = parse_step_message(text)
    assert specs[0].content == "x = 1\n"


def test_parse_close_marker_with_trailing_tab() -> None:
    """A close marker with a trailing tab is recognized."""
    text = "<<<FILE:a.py>>>\nx = 1\n<<<END>>>\t\n"
    specs = parse_step_message(text)
    assert specs[0].content == "x = 1\n"


def test_parse_open_marker_with_trailing_space() -> None:
    """An open marker with trailing whitespace is recognized."""
    text = "<<<FILE:a.py>>>   \nx = 1\n<<<END>>>\n"
    specs = parse_step_message(text)
    assert specs[0].path == "a.py"


@pytest.mark.parametrize(
    "path",
    ["/abs/path.py", "../escape.py", "src/../../escape.py"],
)
def test_validate_paths_rejects_unsafe(tmp_path: Path, path: str) -> None:
    """Absolute paths and parent traversal are rejected."""
    with pytest.raises(FormatError):
        validate_paths([FileSpec(path=path, content="")], tmp_path)


def test_validate_paths_accepts_safe(tmp_path: Path) -> None:
    """A normal relative path passes."""
    validate_paths([FileSpec(path="src/a.py", content="")], tmp_path)


def test_detect_marker_collision_bare_end() -> None:
    """A bare `<<<END>>>` line inside content is rejected."""
    spec = FileSpec(path="a.py", content="before\n<<<END>>>\nafter\n")
    with pytest.raises(FormatError, match="bare"):
        detect_marker_collision(spec)


def test_detect_marker_collision_bare_end_with_space() -> None:
    """A bare `<<<END>>>` with trailing whitespace is rejected."""
    spec = FileSpec(path="a.py", content="before\n<<<END>>>   \nafter\n")
    with pytest.raises(FormatError, match="bare"):
        detect_marker_collision(spec)


def test_detect_marker_collision_file_open_ok() -> None:
    """A `<<<FILE:...>>>` line inside content is allowed."""
    spec = FileSpec(
        path="a.py",
        content="docstring example:\n<<<FILE:foo>>>\nreal content\n",
    )
    detect_marker_collision(spec)


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
