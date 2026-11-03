"""Log do Laravel (storage/logs/laravel.log) para a aba Logs do site.

Leitura incremental pelo offset, só linhas completas, como os JSONL dos agentes: nenhum `tail -F` fica vivo
por aba. Linhas que não começam com data (stack trace) entram na entrada anterior.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

LINE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[^\]]*)\]\s+([\w.-]+)\.([A-Z]+):\s?(.*)$")
TAIL_BYTES = 64 * 1024  # primeira leitura: só o fim do arquivo
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
    """Entradas novas desde `offset` (None: o fim do arquivo). `reset` quando o arquivo encolheu (rotação)."""
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
    if fresh and start > 0:  # começou no meio de uma linha: pula até a próxima
        cut = data.find(b"\n")
        skip = cut + 1 if cut >= 0 else len(data)
    end = data.rfind(b"\n")
    if end < skip:
        complete, consumed = b"", skip
    else:
        complete, consumed = data[skip:end + 1], end + 1  # a linha sem fim fica para a próxima leitura
    lines = complete.decode("utf-8", errors="replace").splitlines()
    return {"exists": True, "entries": parse_entries(lines), "offset": start + consumed, "reset": reset}
