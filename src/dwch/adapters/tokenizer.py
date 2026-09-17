"""Tokenizer adapter backed by HuggingFace `tokenizers`.

The tokenizer file is loaded lazily on first use and cached for the
life of the process. `count()` and `count_batch()` skip special
tokens — the harness counts content, not what the model will see
after its own wrapping.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..shared.errors import TokenizerError


@lru_cache(maxsize=4)
def _load_tokenizer(path_str: str):
    """Load and cache a `Tokenizer` from a file path.

    `lru_cache` keyed on the path string. Loading is one-time per
    process; re-loads only happen if the path changes, which it
    does not in normal operation.
    """
    try:
        from tokenizers import Tokenizer
    except ImportError as exc:
        raise TokenizerError(
            "tokenizers is not installed; run `pip install tokenizers`"
        ) from exc
    path = Path(path_str)
    if not path.is_file():
        raise TokenizerError(
            f"tokenizer file not found: {path}. Run `dwch init` to download it."
        )
    try:
        return Tokenizer.from_file(str(path))
    except Exception as exc:
        raise TokenizerError(f"could not load {path}: {exc}") from exc


class DeepseekTokenizer:
    """`TokenCounterPort` implementation using a local tokenizer file."""

    def __init__(self, tokenizer_path: Path) -> None:
        self._path = tokenizer_path

    def count(self, text: str) -> int:
        if not text:
            return 0
        tokenizer = _load_tokenizer(str(self._path))
        encoded = tokenizer.encode(text, add_special_tokens=False)
        return len(encoded.ids)

    def count_batch(self, texts: list[str]) -> list[int]:
        if not texts:
            return []
        tokenizer = _load_tokenizer(str(self._path))
        encoded = tokenizer.encode_batch(texts, add_special_tokens=False)
        return [len(e.ids) for e in encoded]


__all__ = ["DeepseekTokenizer"]
