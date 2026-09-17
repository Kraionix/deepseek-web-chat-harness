"""Tests for `application.format`."""

from __future__ import annotations

from pathlib import Path

import pytest

from dwch.application.format import (
    detect_marker_collision,
    parse_step_message,
    render_report,
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


def test_detect_marker_collision_file_open_ok() -> None:
    """A `<<<FILE:...>>>` line inside content is allowed."""
    spec = FileSpec(
        path="a.py",
        content="docstring example:\n<<<FILE:foo>>>\nreal content\n",
    )
    detect_marker_collision(spec)


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
