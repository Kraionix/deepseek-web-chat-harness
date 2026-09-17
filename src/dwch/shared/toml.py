"""Minimal TOML serialization helpers.

Only the parts the harness actually needs: escaping strings for
basic-string syntax. There is no full TOML writer here, and no
plan to add one — the two call sites (`lock.render`,
`deviations.render`) both write a small, known-shape document.
"""

from __future__ import annotations

# Control characters below 0x20 that have a single-letter escape.
_SHORT_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def escape_basic_string(value: str) -> str:
    """Escape `value` for use inside a TOML basic string.

    Pre:  `value` is any Python str.
    Post: returns a string with backslash, double quote, the five
          short-escape control characters, any other C0 control
          character, and DEL escaped. Printable Unicode (including
          non-ASCII) is passed through unchanged.

    The set of characters that must be escaped in a basic string is
    fixed by the TOML specification: U+0000..U+0008, U+000A..U+001F,
    U+007F, plus backslash and double quote. C1 controls
    (U+0080..U+009F) are explicitly allowed as-is.
    """
    parts: list[str] = []
    for ch in value:
        if ch in _SHORT_ESCAPES:
            parts.append(_SHORT_ESCAPES[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            parts.append(f"\\u{ord(ch):04X}")
        else:
            parts.append(ch)
    return "".join(parts)


__all__ = ["escape_basic_string"]
