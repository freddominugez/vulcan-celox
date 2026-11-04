"""Parser for the ASCII tables printed by Valet's CLI (Symfony Console format)."""

from __future__ import annotations

from typing import Dict, List


def _is_border(line: str) -> bool:
    s = line.strip()
    return len(s) >= 2 and s[0] == "+" and s[-1] == "+" and set(s) <= set("+-=")


def _is_row(line: str) -> bool:
    s = line.strip()
    return len(s) >= 2 and s[0] == "|" and s[-1] == "|"


def _cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip()[1:-1].split("|")]


def parse_table(text: str) -> List[Dict[str, str]]:
    """Converts the first table found in the text into a list of dicts.

        Ignores text before and after the table. A table with only a header returns [].
        Rows with a different number of cells than the header are padded or truncated.
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not _is_border(lines[i]):
        i += 1
    # header: first data line after the initial border
    while i < len(lines) and not _is_row(lines[i]):
        if not _is_border(lines[i]):
            return []
        i += 1
    if i >= len(lines):
        return []
    header = _cells(lines[i])
    rows: List[Dict[str, str]] = []
    i += 1
    while i < len(lines):
        line = lines[i]
        if _is_border(line):
            i += 1
            continue
        if not _is_row(line):
            break
        cells = _cells(line)
        cells = (cells + [""] * len(header))[:len(header)]
        rows.append(dict(zip(header, cells)))
        i += 1
    return rows
