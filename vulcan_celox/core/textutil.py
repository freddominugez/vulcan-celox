"""Text normalization for search (accent-insensitive, case-insensitive) and a short title for a request."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def contains(haystack: str, needle: str) -> bool:
    return normalize(needle) in normalize(haystack)


HEADLINE_MAX = 120
_FENCE_START = re.compile(r"^`{2,}(?:[\w+-]+(?=\s))?\s*")
_FENCE_END = re.compile(r"\s*`{2,}$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def headline(text: Optional[str], limit: int = HEADLINE_MAX) -> str:
    """A short line for a title from a pasted request: without the block's backticks (two or more: there is a real paste
        with one fewer), the first sentence when it is title-sized, otherwise cut at a word."""
    line = _FENCE_END.sub("", _FENCE_START.sub("", " ".join((text or "").split()))).strip()
    match = _SENTENCE_END.search(line)
    if match and 20 <= match.start() <= limit:
        return line[:match.start()]
    if len(line) <= limit:
        return line
    cut = line[:limit].rsplit(" ", 1)[0] if " " in line[:limit] else line[:limit]
    return cut.rstrip(" ,;:") + "..."
