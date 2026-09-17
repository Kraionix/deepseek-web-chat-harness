"""Tests for `application.token_counter`."""

from __future__ import annotations

from dwch.application.token_counter import count_sections, count_text
from tests.fakes import InMemoryCounter


def test_count_text_empty() -> None:
    """Empty text is zero by convention."""
    assert count_text(InMemoryCounter(), "") == 0


def test_count_text_len() -> None:
    """The fake returns `len`, which the facade passes through."""
    assert count_text(InMemoryCounter(), "hello") == 5


def test_count_sections_empty() -> None:
    """An empty section map yields zero and an empty breakdown."""
    total, breakdown = count_sections(InMemoryCounter(), {})
    assert total == 0
    assert breakdown == {}


def test_count_sections_breakdown() -> None:
    """Breakdown keys mirror section names and sum to the total."""
    total, breakdown = count_sections(
        InMemoryCounter(),
        {"a": "12", "bb": "345"},
    )
    assert total == 5
    assert breakdown == {"a": 2, "bb": 3}
