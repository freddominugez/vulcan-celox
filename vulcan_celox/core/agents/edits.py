"""Record of each session's file edits. The index keeps only where each edit is in the JSONL; the content is
read on demand by offset, because the JSONL remains the source of truth (and `originalFile` is never stored)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from vulcan_celox.core.agents.discovery import zstd_bin
from vulcan_celox.core.agents.jsonl_stream import MAX_LINE, LineStream, ZstdLineStream
from vulcan_celox.core.agents.model import as_str

SCHEMA = """
CREATE TABLE IF NOT EXISTS session_edits (
  session_id TEXT NOT NULL, seq INTEGER NOT NULL, path TEXT NOT NULL, at TEXT, tool TEXT, turn INTEGER,
  byte_offset INTEGER NOT NULL, result_offset INTEGER, ref TEXT, kind TEXT, state TEXT,
  PRIMARY KEY (session_id, seq));
CREATE INDEX IF NOT EXISTS session_edits_path ON session_edits(session_id, path);
"""
COLUMNS = ("seq", "path", "at", "tool", "turn", "byte_offset", "result_offset", "ref", "kind", "state")
CLAUDE_TOOLS = {"Edit": "edit", "MultiEdit": "edit", "Write": "write"}
CODEX_KINDS = {"add": "create", "update": "edit", "delete": "delete"}
PATCH_KINDS = {"Add": "create", "Update": "edit", "Delete": "delete"}
PATCH_BEGIN = "*** Begin Patch"
PATCH_FILE = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+?)\s*$", re.M)
PATCH_SECTION = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: |^\*\*\* End Patch\s*$", re.M)
BIG_PATH = re.compile(rb'"file_path"\s*:\s*"((?:[^"\\]|\\.){1,4096})"')
BIG_TOOL = re.compile(rb'"name"\s*:\s*"(Edit|MultiEdit|Write)"')
BIG_ASSISTANT = re.compile(rb'"role"\s*:\s*"assistant"')
BIG_SIDECHAIN = re.compile(rb'"isSidechain"\s*:\s*true')
BIG_PATCH = re.compile(rb"\*\*\* (Add|Update|Delete) File: ([^\\\n\"]{1,4096})")
_MAX_PENDING = 256


def _patch_text(payload: dict) -> str:
    """Texto do patch num function_call ou custom_tool_call, inclusive dentro de JSON ou heredoc."""
    raw = payload.get("arguments", payload.get("input"))
    if not isinstance(raw, str):
        raw = json.dumps(raw) if raw else ""
    if PATCH_BEGIN not in raw:
        return ""
    try:
        return _find_patch(json.loads(raw)) or raw
    except ValueError:
        return raw


def _find_patch(data: Any) -> str:
    if isinstance(data, str):
        return data if PATCH_BEGIN in data else ""
    if isinstance(data, list):
        return next((t for t in map(_find_patch, data) if t), "")
    if isinstance(data, dict):
        return next((t for t in map(_find_patch, data.values()) if t), "")
    return ""


class EditTracker:
    """Follows the JSONL lines alongside the session reader; the saved state allows continuing from the offset."""

    def __init__(self, agent: str, state: Optional[Dict] = None):
        state = state or {}
        self.agent = agent
        self.seq = int(state.get("seq", 0))
        self.pending: Dict[str, Dict] = dict(state.get("pending") or {})  # Claude: por tool_use; Codex: por caminho
        self.items = bool(state.get("items"))
        self.rows: List[Dict] = []

    def state(self) -> Dict:
        return {"seq": self.seq, "pending": self.pending, "items": self.items}

    def drain(self) -> List[Dict]:
        out, self.rows = self.rows, []
        return out

    def _add(self, path: str, at: str, tool: str, turn: int, offset: int, ref: str, kind: str, state: str) -> Dict:
        self.seq += 1
        row = {"seq": self.seq, "path": path, "at": at, "tool": tool, "turn": turn, "byte_offset": offset,
               "result_offset": None, "ref": ref, "kind": kind, "state": state}
        self.rows.append(row)
        return row

    def _remember(self, key: str, row: Dict) -> None:
        self.pending[key] = row
        while len(self.pending) > _MAX_PENDING:
            self.pending.pop(next(iter(self.pending)))

    def feed(self, start: int, obj: dict, turn: int) -> None:
        (self._feed_claude if self.agent == "claude" else self._feed_codex)(start, obj, turn)

    # ── Claude Code ────────────────────────────────────────────────────────
    def _feed_claude(self, start: int, obj: dict, turn: int) -> None:
        kind = obj.get("type")
        if kind not in ("user", "assistant") or obj.get("isSidechain"):
            return
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        content = message.get("content") if isinstance(message.get("content"), list) else []
        for block in content:
            if not isinstance(block, dict):
                continue
            if kind == "assistant" and block.get("type") == "tool_use":
                self._claude_tool(block, start, as_str(obj.get("timestamp")), turn)
            elif kind == "user" and block.get("type") == "tool_result":
                self._claude_result(block, obj.get("toolUseResult"), start)

    def _claude_tool(self, block: dict, start: int, at: str, turn: int) -> None:
        name, data, tool_id = block.get("name"), block.get("input"), block.get("id")
        if name not in CLAUDE_TOOLS or not isinstance(data, dict) or not isinstance(tool_id, str):
            return
        path = data.get("file_path")
        if isinstance(path, str) and path and tool_id not in self.pending:
            self._remember(tool_id, self._add(path, at, name, turn, start, tool_id, CLAUDE_TOOLS[name], "pending"))

    def _claude_result(self, block: dict, result: Any, start: int) -> None:
        row = self.pending.pop(block.get("tool_use_id"), None) if isinstance(block.get("tool_use_id"), str) else None
        if row is None:
            return
        row = {**row, "result_offset": start, "state": "failed" if block.get("is_error") else "ok"}
        if row["kind"] == "write" and isinstance(result, dict):
            row["kind"] = "create" if result.get("type") == "create" else "edit"
        self.rows.append(row)

    # ── Codex ──────────────────────────────────────────────────────────────
    def _feed_codex(self, start: int, obj: dict, turn: int) -> None:
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        at = as_str(obj.get("timestamp"))
        if obj.get("type") == "event_msg" and payload.get("type") == "item_completed":
            item = payload.get("item")
            if isinstance(item, dict) and item.get("type") == "FileChange" and isinstance(item.get("changes"), dict):
                self._file_change(item, start, at, turn)
        elif obj.get("type") == "response_item" and payload.get("type") in ("function_call", "custom_tool_call"):
            if not self.items:
                self._patch(_patch_text(payload), payload.get("name"), start, at, turn)

    def _patch(self, text: str, name: Any, start: int, at: str, turn: int) -> None:
        for match in PATCH_FILE.finditer(text):
            path = match.group(2)
            row = self._add(path, at, as_str(name) or "apply_patch", turn, start, path, PATCH_KINDS[match.group(1)], "ok")
            self._remember(path, row)

    def _file_change(self, item: dict, start: int, at: str, turn: int) -> None:
        """The item brings the ready-made diff. The patch that originated it stays the same edit, not a second one."""
        self.items = True
        state = "ok" if item.get("status") in ("completed", None) else "failed"
        for path, change in item["changes"].items():
            change = change if isinstance(change, dict) else {}
            kind = CODEX_KINDS.get(change.get("type"), "edit")
            earlier = self.pending.pop(path, None)
            if earlier is not None:
                self.rows.append({**earlier, "at": at, "byte_offset": start, "tool": "FileChange", "kind": kind,
                                  "state": state})
            else:
                self._add(path, at, "FileChange", turn, start, path, kind, state)

    # ── linha acima do limite ──────────────────────────────────────────────
    def feed_oversized(self, start: int, raw: bytes, turn: int) -> None:
        """The giant line is discarded by the reader, but the edit happened: record it without a diff."""
        if self.agent == "claude":
            head = raw[:65536]
            tool, path = BIG_TOOL.search(head), BIG_PATH.search(head)
            # only the agent message: the "type" key of the line comes after the content, outside what was read
            if tool and path and BIG_ASSISTANT.search(head) and not BIG_SIDECHAIN.search(head):
                try:
                    name = json.loads(b'"' + path.group(1) + b'"')
                except ValueError:
                    return
                self._add(name, "", tool.group(1).decode(), turn, start, "", "edit", "no_diff")
        elif not self.items:
            for match in BIG_PATCH.finditer(raw):
                self._add(match.group(2).decode("utf-8", "replace").strip(), "", "apply_patch", turn, start,
                          "", PATCH_KINDS[match.group(1).decode()], "no_diff")


# ── banco ────────────────────────────────────────────────────────────────────
def store(db, session_id: str, rows: List[Dict]) -> None:
    db.executemany("INSERT OR REPLACE INTO session_edits VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   [(session_id, *(r.get(c) for c in COLUMNS)) for r in rows])


def rows_of(index, session_id: str, start: int = 0, limit: int = 200, path: Optional[str] = None) -> List[Dict]:
    sql = "SELECT * FROM session_edits WHERE session_id = ? AND seq > ?"
    args: list = [session_id, start]
    if path is not None:
        sql += " AND path = ?"
        args.append(path)
    with index.lock:
        rows = index.db.execute(sql + " ORDER BY seq LIMIT ?", (*args, limit)).fetchall()
    return [{c: r[c] for c in COLUMNS} for r in rows]


def recent_rows(index, session_id: str, limit: int = 200) -> List[Dict]:
    """The last edits of a session, newest first."""
    with index.lock:
        rows = index.db.execute("SELECT * FROM session_edits WHERE session_id = ? ORDER BY seq DESC LIMIT ?", (session_id, limit)).fetchall()
    return [{c: r[c] for c in COLUMNS} for r in rows]


def row_at(index, session_id: str, seq: int) -> Optional[Dict]:
    with index.lock:
        row = index.db.execute("SELECT * FROM session_edits WHERE session_id = ? AND seq = ?", (session_id, seq)).fetchone()
    return {c: row[c] for c in COLUMNS} if row else None


# ── on-demand content ───────────────────────────────────────────────────────
def line_at(file_path: str, offset: Optional[int], max_line: int = MAX_LINE) -> Optional[dict]:
    """The line that starts at `offset`, reading only it (in .zst, decompressing until reaching it)."""
    if offset is None:
        return None
    if file_path.endswith(".zst"):
        stream: LineStream = ZstdLineStream(file_path, zstd_bin(), max_line)
    else:
        stream = LineStream(file_path, offset, max_line)
    lines = iter(stream)
    try:
        for start, obj in lines:
            if start >= offset:
                return obj if start == offset else None
    except OSError:
        return None
    finally:
        lines.close()
    return None


def _sides_from_lines(lines: List[str]) -> Tuple[str, str]:
    old, new = [], []
    for line in lines:
        if line.startswith("-"):
            old.append(line[1:])
        elif line.startswith("+"):
            new.append(line[1:])
        else:
            text = line[1:] if line.startswith(" ") else line
            old.append(text)
            new.append(text)
    return "\n".join(old), "\n".join(new)


def _unified_sides(text: str) -> Tuple[str, str]:
    body = [ln for ln in text.split("\n") if not ln.startswith(("--- ", "+++ ", "@@", "\\ No newline"))]
    while body and not body[-1]:
        body.pop()
    return _sides_from_lines(body)


def _patch_section(text: str, path: str) -> Optional[Tuple[str, List[str]]]:
    for match in PATCH_FILE.finditer(text):
        if match.group(2) != path:
            continue
        following = PATCH_SECTION.search(text, match.end())
        body = text[match.end():following.start() if following else len(text)]
        lines = [ln for ln in body.split("\n") if ln and not ln.startswith(("@@", "*** Move to:"))]
        return match.group(1), lines
    return None


def _claude_detail(row: Dict, line: dict, result_line: Optional[dict]) -> Optional[Dict]:
    message = line.get("message") if isinstance(line.get("message"), dict) else {}
    content = message.get("content") if isinstance(message.get("content"), list) else []
    block = next((b for b in content if isinstance(b, dict) and b.get("id") == row["ref"]), None)
    data = block.get("input") if isinstance(block, dict) else None
    if not isinstance(data, dict):
        return None
    result = result_line.get("toolUseResult") if isinstance(result_line, dict) else None
    result = result if isinstance(result, dict) else {}
    if row["tool"] == "Write":
        original = result.get("originalFile") if isinstance(result.get("originalFile"), str) else ""
        return {"old": original, "new": as_str(data.get("content")), "complete": bool(result)}
    hunks = result.get("structuredPatch") if isinstance(result.get("structuredPatch"), list) else []
    pieces = [_sides_from_lines([ln for ln in h.get("lines", []) if isinstance(ln, str)])
              for h in hunks if isinstance(h, dict)]
    if not pieces:
        pairs = data.get("edits") if isinstance(data.get("edits"), list) else [data]
        pieces = [(as_str(p.get("old_string")), as_str(p.get("new_string"))) for p in pairs if isinstance(p, dict)]
    return {"old": "\n…\n".join(p[0] for p in pieces), "new": "\n…\n".join(p[1] for p in pieces), "complete": False,
            "replace_all": data.get("replace_all") is True}


def _codex_detail(row: Dict, line: dict) -> Optional[Dict]:
    payload = line.get("payload") if isinstance(line.get("payload"), dict) else {}
    if isinstance(payload.get("item"), dict):
        changes = payload["item"].get("changes")
        change = changes.get(row["path"]) if isinstance(changes, dict) else None
        if not isinstance(change, dict):
            return None
        if isinstance(change.get("unified_diff"), str):
            old, new = _unified_sides(change["unified_diff"])
            return {"old": old, "new": new, "complete": False}
        text = as_str(change.get("content"))
        return {"old": "", "new": text, "complete": True} if change.get("type") == "add" else \
            {"old": text, "new": "", "complete": True}
    section = _patch_section(_patch_text(payload), row["path"])
    if section is None:
        return None
    kind, lines = section
    old, new = _sides_from_lines(lines)
    return {"old": old, "new": new, "complete": kind != "Update"}


def edit_detail(agent: str, file_path: str, row: Dict) -> Dict:
    """Both sides of an edit, or `available: False` with the reason. `complete` says whether it is the whole file or a snippet."""
    if row.get("state") == "no_diff":
        return {"available": False, "reason": "no_diff"}
    line = line_at(file_path, row.get("byte_offset"))
    if line is None:
        return {"available": False, "reason": "source_gone"}
    if agent == "claude":
        detail = _claude_detail(row, line, line_at(file_path, row.get("result_offset")))
    else:
        detail = _codex_detail(row, line)
    return {"available": True, **detail} if detail else {"available": False, "reason": "no_diff"}
