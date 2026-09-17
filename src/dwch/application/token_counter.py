"""Section-aware token accounting.

Thin facade over `TokenCounterPort`. Exists so commands do not have
to know about the port's batch API when they only need a single
count, and so multi-section counting (bootstrap, read, verify
header) is expressed in one place.
"""

from __future__ import annotations

from .ports import TokenCounterPort


def count_sections(
    counter: TokenCounterPort,
    sections: dict[str, str],
) -> tuple[int, dict[str, int]]:
    """Count every section in one batch.

    Returns `(total, breakdown)`. `breakdown` has the same keys as
    `sections`. Uses `count_batch` so that a real tokenizer runs the
    work in parallel; a trivial implementation may fall back to a
    loop, which is fine because the section count is small.
    """
    if not sections:
        return 0, {}
    names = list(sections.keys())
    texts = [sections[name] for name in names]
    counts = counter.count_batch(texts)
    breakdown = dict(zip(names, counts, strict=True))
    return sum(counts), breakdown


def count_text(counter: TokenCounterPort, text: str) -> int:
    """Count a single text. Empty text is zero by convention."""
    if not text:
        return 0
    return counter.count(text)


__all__ = ["count_sections", "count_text"]
