"""Tests for `shared.toml`."""

from __future__ import annotations

import tomllib

import pytest

from dwch.shared.toml import (
    escape_basic_string,
    list_of_strings,
    list_of_tables,
)


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("plain", "plain"),
        ("back\\slash", "back\\\\slash"),
        ('quote"here', 'quote\\"here'),
        ("line\nbreak", "line\\nbreak"),
        ("tab\there", "tab\\there"),
        ("carriage\rreturn", "carriage\\rreturn"),
        ("back\bspace", "back\\bspace"),
        ("form\ffeed", "form\\ffeed"),
        ("null\x00byte", "null\\u0000byte"),
        ("unit\x1fsep", "unit\\u001Fsep"),
        ("del\x7fchar", "del\\u007Fchar"),
    ],
)
def test_escape_basic_string(raw: str, escaped: str) -> None:
    """Escape every character TOML requires inside a basic string."""
    assert escape_basic_string(raw) == escaped


def test_escape_passes_unicode_through() -> None:
    """Non-ASCII printable characters are not escaped."""
    assert escape_basic_string("привет — 日本") == "привет — 日本"


def test_escape_round_trips_through_tomllib() -> None:
    """Any escaped value parses back to the original string."""
    samples = [
        "plain",
        "with \\ backslash",
        'with " quote',
        "with\nnewline",
        "with\t tab",
        "control \x00\x1f\x7f",
        "юникод",
    ]
    for value in samples:
        document = f'x = "{escape_basic_string(value)}"'
        parsed = tomllib.loads(document)
        assert parsed["x"] == value


def test_list_of_tables_ok() -> None:
    """A list of dicts passes through unchanged."""
    assert list_of_tables([{"a": 1}, {"b": 2}], "x") == [{"a": 1}, {"b": 2}]


def test_list_of_tables_empty() -> None:
    """An empty list is valid."""
    assert list_of_tables([], "x") == []


def test_list_of_tables_rejects_string() -> None:
    """A string is not a list of tables."""
    with pytest.raises(ValueError, match="expected a list of tables, got str"):
        list_of_tables("abc", "x")


def test_list_of_tables_rejects_non_table_item() -> None:
    """An item that is not a table is rejected, with its index."""
    with pytest.raises(ValueError, match=r"x\[1\]: expected a table"):
        list_of_tables([{"a": 1}, "nope"], "x")


def test_list_of_tables_rejects_none() -> None:
    """None is not a list of tables."""
    with pytest.raises(ValueError, match="expected a list of tables"):
        list_of_tables(None, "x")


def test_list_of_strings_ok() -> None:
    """A list of strings passes through unchanged."""
    assert list_of_strings(["a", "b"], "x") == ["a", "b"]


def test_list_of_strings_empty() -> None:
    """An empty list is valid."""
    assert list_of_strings([], "x") == []


def test_list_of_strings_rejects_bare_string() -> None:
    """A bare string is not split into characters."""
    with pytest.raises(ValueError, match="expected a list of strings, got str"):
        list_of_strings("abc", "x")


def test_list_of_strings_rejects_non_string_item() -> None:
    """A non-string item is rejected, with its index."""
    with pytest.raises(ValueError, match=r"x\[0\]: expected a string"):
        list_of_strings([1, 2], "x")
