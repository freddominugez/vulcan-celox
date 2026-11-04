"""Incremental reading of a session file: continues from the offset with the reader's saved state."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from vulcan_celox.core.agents import claude_reader
from vulcan_celox.core.agents.discovery import zstd_bin
from vulcan_celox.core.agents.edits import EditTracker
from vulcan_celox.core.agents.jsonl_stream import MAX_LINE, LineStream, ZstdLineStream
from vulcan_celox.core.agents.model import AgentSession, SessionEvent


def _readers() -> Dict:
    readers = {"claude": (claude_reader.new_session, claude_reader.ClaudeReader)}
    try:
        from vulcan_celox.core.agents import codex_reader
        readers["codex"] = (codex_reader.new_session, codex_reader.CodexReader)
    except ImportError:  # pragma: no cover  (the Codex reader has been part of the package since its introduction)
        pass
    return readers


@dataclass
class ReadResult:
    session: AgentSession
    state: Dict
    offset: int
    size: int
    events: List[SessionEvent] = field(default_factory=list)
    errors: List[Tuple[int, str]] = field(default_factory=list)
    reset: bool = False
    usage: List[Dict] = field(default_factory=list)
    edits: List[Dict] = field(default_factory=list)


def read_session(agent: str, path, session: Optional[AgentSession] = None, state: Optional[Dict] = None,
                 offset: int = 0, max_line: int = MAX_LINE) -> ReadResult:
    path = Path(path)
    new_session, reader_cls = _readers()[agent]
    reset = False
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    compressed = path.name.endswith(".zst")  # always from the start; the offset does not belong to the file on disk
    if session is None or size < offset or compressed:
        reset = session is not None
        session, state, offset = new_session(path), None, 0
    reader = reader_cls(session, state)
    stream = ZstdLineStream(path, zstd_bin(), max_line) if compressed else LineStream(path, offset, max_line)
    tracker = EditTracker(agent, (state or {}).get("edits"))
    stream.on_oversized = lambda start, raw: tracker.feed_oversized(start, raw, session.turns)
    feed_errors: List[Tuple[int, str]] = []
    for start, obj in stream:
        try:
            reader.feed(obj)
            tracker.feed(start, obj, session.turns)
        except Exception as exc:  # noqa: BLE001  one strange line must not block the whole session
            feed_errors.append((start, f"linha ignorada: {type(exc).__name__}: {exc}"))
    if stream.reset and not reset:
        # the file shrank between the stat above and the open: the old state is invalid, reread from scratch
        result = read_session(agent, path, None, None, 0, max_line)
        result.reset = True
        return result
    errors = stream.errors + feed_errors
    session.parse_errors += len(errors)
    return ReadResult(session=session, state={**reader.state(), "edits": tracker.state()}, offset=stream.offset,
                      size=stream.size or size, events=reader.b.drain_events(), errors=errors, reset=reset,
                      usage=reader.drain_usage() if hasattr(reader, "drain_usage") else [], edits=tracker.drain())
