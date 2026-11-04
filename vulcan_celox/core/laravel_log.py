"""Laravel log (storage/logs/laravel.log) for the site's Logs tab.

Incremental reading by offset, complete lines only, like the agents' JSONL: no `tail -F` stays alive
per tab. Lines that do not start with a date (stack trace) go into the previous entry.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

LINE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[^\]]*)\]\s+([\w.-]+)\.([A-Z]+):\s?(.*)$")
TAIL_BYTES = 64 * 1024  # first read: only the end of the file
MAX_READ = 512 * 1024
LEVELS = ("EMERGENCY", "ALERT", "CRITICAL", "ERROR", "WARNING", "NOTICE", "INFO", "DEBUG")


def parse_laravel_line(line: str) -> Optional[Dict[str, str]]:
    match = LINE.match(line.rstrip("\n"))
    if not match:
        return None
    ts, channel, level, message = match.groups()
    return {"ts": ts, "channel": channel, "level": level, "message": message}


def parse_entries(lines: List[str]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for line in lines:
        entry = parse_laravel_line(line)
        if entry:
            entries.append(entry)
        elif entries and line.strip():
            entries[-1]["message"] += "\n" + line.rstrip("\n")
    return entries


def filter_entries(entries: List[Dict[str, str]], level: str = "", query: str = "") -> List[Dict[str, str]]:
    q = query.strip().lower()
    return [e for e in entries if (not level or e["level"] == level) and (not q or q in e["message"].lower())]


def read_log(path, offset: Optional[int] = None) -> Dict[str, Any]:
    """New entries since `offset` (None: the end of the file). `reset` when the file shrank (rotation)."""
    path = Path(path)
    try:
        size = os.path.getsize(path)
    except OSError:
        return {"exists": False, "entries": [], "offset": 0, "reset": False}
    reset = offset is not None and offset > size
    fresh = offset is None or reset
    start = max(0, size - TAIL_BYTES) if fresh else offset
    with open(path, "rb") as fh:
        fh.seek(start)
        data = fh.read(MAX_READ)
    skip = 0
    if fresh and start > 0:  # started in the middle of a line: skip to the next one
        cut = data.find(b"\n")
        skip = cut + 1 if cut >= 0 else len(data)
    end = data.rfind(b"\n")
    if end < skip:
        complete, consumed = b"", skip
    else:
        complete, consumed = data[skip:end + 1], end + 1  # the unterminated line is left for the next read
    lines = complete.decode("utf-8", errors="replace").splitlines()
    return {"exists": True, "entries": parse_entries(lines), "offset": start + consumed, "reset": reset}
