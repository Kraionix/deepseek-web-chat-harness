"""Tests for `shared.toml.escape_basic_string`."""

from __future__ import annotations

import tomllib

import pytest

from dwch.shared.toml import escape_basic_string


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
