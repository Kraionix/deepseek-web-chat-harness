"""Minimal TOML serialization and coercion helpers.

Only the parts the harness actually needs:

- `escape_basic_string` for writing TOML strings.
- `list_of_tables` / `list_of_strings` for coercing user-edited
  TOML into a verified shape before it is iterated.

There is no full TOML writer here, and no plan to add one — the
two render sites (`lock.render`, `deviations.render`) both write a
small, known-shape document.
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


def list_of_tables(value: object, label: str) -> list[dict]:
    """Return `value` as a list of dicts, or raise `ValueError`.

    Pre:  `value` is any Python object, typically whatever
          `tomllib` produced for a TOML array-of-tables key.
    Post: a list of dicts.
    Raises: `ValueError` when `value` is not a list, or when any
          item is not a table. The message names `label` and the
          actual type, so callers can re-wrap it in their own error
          type without losing the diagnosis.

    Iterating directly over a string (the previous behaviour) yields
    characters, not tables, and the next `item.get(...)` call raises
    `AttributeError`. Coercion here turns that into a clear error.
    """
    if not isinstance(value, list):
        raise ValueError(
            f"{label}: expected a list of tables, got {type(value).__name__}"
        )
    out: list[dict] = []
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(
                f"{label}[{i}]: expected a table, got {type(item).__name__}"
            )
        out.append(item)
    return out


def list_of_strings(value: object, label: str) -> list[str]:
    """Return `value` as a list of strings, or raise `ValueError`.

    Pre:  `value` is any Python object.
    Post: a list of strings.
    Raises: `ValueError` when `value` is not a list, or when any
          item is not a string. A bare string input is rejected
          rather than split into characters.
    """
    if not isinstance(value, list):
        raise ValueError(
            f"{label}: expected a list of strings, got {type(value).__name__}"
        )
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(
                f"{label}[{i}]: expected a string, got {type(item).__name__}"
            )
        out.append(item)
    return out


__all__ = ["escape_basic_string", "list_of_strings", "list_of_tables"]
