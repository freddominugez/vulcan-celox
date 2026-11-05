"""Who wrote a file on the Code screen. The disk says what changed and the agent's JSONL says who: an event only gets an agent if a
session paired or active in that folder recorded an edit of that same path within 60 s. Without that record it stays null."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from vulcan_celox.core.agents import edits as edit_log

WINDOW = 60.0
CACHE = 1.0
ROWS = 200


def _parse(at: Optional[str]) -> Optional[float]:
    if not at:
        return None
    try:
        return datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _related(folder: Optional[str], root: str) -> bool:
    if not folder:
        return False
    real = os.path.realpath(folder)
    return real == root or real.startswith(root + os.sep) or root.startswith(real + os.sep)


class EditAttribution:
    def __init__(self, app):
        self.app = app
        self.lock = threading.Lock()
        self.cache: Dict[str, Any] = {}

    def recent(self, root: str) -> Dict[str, List[Dict[str, Any]]]:
        """Real path -> edits that the sessions of this folder recorded a short while ago."""
        now = time.monotonic()
        with self.lock:
            cached = self.cache.get(root)
        if cached and now - cached[0] < CACHE:
            return cached[1]
        out: Dict[str, List[Dict[str, Any]]] = {}
        index = self.app.agents.index
        for session in index.sessions():
            if not (session.is_active or session.pairing_id):
                continue
            if not (_related(session.project_root, root) or _related(session.cwd, root)):
                continue
            base = session.cwd or session.project_root or root
            for row in edit_log.recent_rows(index, session.id, ROWS):
                at = _parse(row["at"])
                if at is None or row["state"] == "failed":
                    continue
                full = os.path.realpath(os.path.join(base, row["path"]))
                out.setdefault(full, []).append({"at": at, "agent": session.agent, "session": session.id})
        with self.lock:
            self.cache[root] = (now, out)
        return out

    def apply(self, root: str, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fills in the agent of recent events. The record may arrive after the write, so the screen also receives what became known now."""
        waiting = [e for e in events if e.get("agent") is None and e["kind"] != "dir" and time.time() - e["at"] <= WINDOW * 2]
        if waiting:
            recent = self.recent(root)
            for event in waiting:
                full = os.path.realpath(os.path.join(root, event["rel"]))
                match = [r for r in recent.get(full, ()) if abs(r["at"] - event["at"]) <= WINDOW]
                if match:
                    best = max(match, key=lambda r: r["at"])
                    event["agent"] = {"agent": best["agent"], "session": best["session"]}
        known = {e["rel"]: e["agent"] for e in events if e.get("agent") and time.time() - e["at"] <= WINDOW * 2}
        return [{"rel": rel, "agent": agent} for rel, agent in known.items()]
