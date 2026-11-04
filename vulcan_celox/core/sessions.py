"""Terminal sessions with memory: persistent record and reconstruction of the typed commands."""

from __future__ import annotations

import codecs
import threading
from dataclasses import asdict, dataclass, field, fields
from typing import Dict, List, Optional

from vulcan_celox.core.models import now_iso

SESSIONS_FILE = "terminal_sessions"
MAX_COMMANDS = 2000
PASTE_START = "\x1b[200~"
PASTE_END = "\x1b[201~"


@dataclass
class SessionRecord:
    id: str
    title: str = ""
    site: Optional[str] = None
    cwd: str = ""
    tags: List[str] = field(default_factory=list)
    commands: List[Dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    closed_at: Optional[str] = None
    exit_code: Optional[int] = None
    memory_file: Optional[str] = None
    theme: Optional[str] = None  # tab color identity, the same as the paired agent session

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data) -> Optional["SessionRecord"]:
        if not isinstance(data, dict) or not data.get("id"):
            return None
        names = {f.name for f in fields(cls)}
        record = cls(**{k: v for k, v in data.items() if k in names})
        record.tags = [t for t in (record.tags or []) if isinstance(t, str)]
        record.commands = [c for c in (record.commands or []) if isinstance(c, dict) and c.get("cmd")]
        return record


class InputTracker:
    """Rebuilds shell lines from the bytes sent to the PTY.

        A conscious approximation: commands recalled from history with the arrow keys are not
        visible in the input and stay only in the output log.
    """

    def __init__(self):
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._line: List[str] = []
        self._pending = ""
        self._pasting = False

    def feed(self, data: bytes) -> List[str]:
        text = self._pending + self._decoder.decode(data)
        self._pending = ""
        done: List[str] = []
        i = 0
        while i < len(text):
            ch = text[i]
            if text.startswith(PASTE_START, i):
                self._pasting = True
                i += len(PASTE_START)
                continue
            if text.startswith(PASTE_END, i):
                self._pasting = False
                i += len(PASTE_END)
                continue
            if ch == "\x1b":
                end = self._escape_end(text, i)
                if end is None:  # incomplete sequence: wait for the next chunk
                    self._pending = text[i:]
                    break
                i = end
                continue
            if ch in "\r\n":
                self._commit(done)
            elif ch in "\x7f\x08":
                if self._line:
                    self._line.pop()
            elif ch in "\x15\x03":  # Ctrl+U apaga a linha, Ctrl+C cancela
                self._line.clear()
            elif ch == "\x17":  # Ctrl+W deletes the last word
                while self._line and self._line[-1] == " ":
                    self._line.pop()
                while self._line and self._line[-1] != " ":
                    self._line.pop()
            elif ch == "\t" or ord(ch) < 0x20:
                pass
            else:
                self._line.append(ch)
            i += 1
        return done

    def _commit(self, done: List[str]) -> None:
        line = "".join(self._line).strip()
        self._line.clear()
        if line:
            done.append(line)

    @staticmethod
    def _escape_end(text: str, i: int) -> Optional[int]:
        if i + 1 >= len(text):
            return None
        nxt = text[i + 1]
        if nxt == "[":  # CSI: parameters up to a final byte between @ and ~
            j = i + 2
            while j < len(text):
                if "@" <= text[j] <= "~":
                    return j + 1
                j += 1
            return None
        if nxt == "O":  # SS3 (arrows in application mode)
            return i + 3 if i + 2 < len(text) else None
        return i + 2  # Alt+tecla


class SessionStore:
    def __init__(self, store):
        self.store = store
        self._lock = threading.RLock()
        self._records: Dict[str, SessionRecord] = {}
        for raw in store.load(SESSIONS_FILE, []):
            record = SessionRecord.from_dict(raw)
            if record:
                self._records[record.id] = record

    def _save(self) -> None:
        self.store.save(SESSIONS_FILE, [r.to_dict() for r in self._records.values()])

    def create(self, session_id: str, title: str, site: Optional[str], cwd: str,
               theme: Optional[str] = None) -> SessionRecord:
        with self._lock:
            record = SessionRecord(id=session_id, title=title, site=site, cwd=cwd, theme=theme)
            self._records[session_id] = record
            self._save()
            return record

    def delete(self, session_id: str) -> Optional[SessionRecord]:
        with self._lock:
            record = self._records.pop(session_id, None)
            if record is not None:
                self._save()
            return record

    def get(self, session_id: str) -> Optional[SessionRecord]:
        with self._lock:
            return self._records.get(session_id)

    def list(self, site: object = "*") -> List[SessionRecord]:
        with self._lock:
            items = [r for r in self._records.values() if site == "*" or r.site == site]
        return sorted(items, key=lambda r: r.created_at, reverse=True)

    def split(self, site: object = "*") -> Dict[str, List[SessionRecord]]:
        items = self.list(site)
        return {"open": [r for r in items if r.is_open], "closed": [r for r in items if not r.is_open]}

    def rename(self, session_id: str, title: str) -> SessionRecord:
        with self._lock:
            record = self._records[session_id]
            record.title = title
            self._save()
            return record

    def set_tags(self, session_id: str, tag_ids: List[str]) -> SessionRecord:
        with self._lock:
            record = self._records[session_id]
            record.tags = list(dict.fromkeys(tag_ids))
            self._save()
            return record

    def remove_tag_everywhere(self, tag_id: str) -> None:
        with self._lock:
            changed = False
            for record in self._records.values():
                if tag_id in record.tags:
                    record.tags = [t for t in record.tags if t != tag_id]
                    changed = True
            if changed:
                self._save()

    def add_commands(self, session_id: str, commands: List[str]) -> None:
        if not commands:
            return
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return
            stamp = now_iso()
            record.commands.extend({"ts": stamp, "cmd": c} for c in commands)
            if len(record.commands) > MAX_COMMANDS:
                record.commands = record.commands[-MAX_COMMANDS:]
            self._save()

    def close(self, session_id: str, exit_code: Optional[int] = None) -> Optional[SessionRecord]:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return None
            if record.closed_at is None:
                record.closed_at = now_iso()
                record.exit_code = exit_code
                self._save()
            return record

    def set_memory_file(self, session_id: str, path: str) -> None:
        with self._lock:
            record = self._records.get(session_id)
            if record and record.memory_file != path:
                record.memory_file = path
                self._save()

    def close_orphans(self, live_ids) -> List[SessionRecord]:
        """Sessions marked as open whose PTY no longer exists (previous app terminated)."""
        live = set(live_ids)
        closed = []
        with self._lock:
            for record in self._records.values():
                if record.is_open and record.id not in live:
                    record.closed_at = now_iso()
                    closed.append(record)
            if closed:
                self._save()
        return closed
