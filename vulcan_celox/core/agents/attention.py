"""Where a session's turn stands: working, your turn, or maybe waiting.

The reader keeps only the fact seen in the file (`running`, `tool_pending`, `your_turn`) and the time. The displayed state is
computed at read time, because "the tool has not answered for a while" depends on the clock, not on the file.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from vulcan_celox.core.agents.model import AgentSession, epoch

WAITING_AFTER_SECONDS = 20
RUNNING_MAX_SECONDS = 600  # no new line for longer than this: the session stopped, it is not working
STALE_SECONDS = 6 * 3600  # an old signal becomes noise: someone who left yesterday is not waiting for an answer
PERMISSION_MAX_SECONDS = 1800
_MAX_PENDING = 64


def utc_iso(at: float) -> str:
    return datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AttentionTracker:
    """Tracks the turn from the reader's events and leaves the result in `session.attention`."""

    def __init__(self, session: AgentSession, state: Optional[Dict] = None):
        state = state or {}
        self.session = session
        self.pending: List[str] = list(state.get("pending") or [])
        self.pending_since: str = state.get("pending_since") or ""

    def state(self) -> Dict:
        return {"pending": self.pending, "pending_since": self.pending_since}

    def _set(self, name: str, at: str) -> None:
        self.session.attention = {"state": name, "since": at}

    def turn_started(self, at: str) -> None:
        self.pending, self.pending_since = [], ""
        self._set("running", at)

    def turn_ended(self, at: str) -> None:
        self.pending, self.pending_since = [], ""
        self._set("your_turn", at)

    def tool_started(self, tool_id: str, at: str) -> None:
        if not self.pending:
            self.pending_since = at
        self.pending.append(tool_id)
        del self.pending[:-_MAX_PENDING]
        self._set("tool_pending", self.pending_since)

    def tool_finished(self, tool_id: str, at: str) -> None:
        if tool_id not in self.pending:
            return
        self.pending.remove(tool_id)
        if self.pending:
            self._set("tool_pending", self.pending_since)
        else:
            self.pending_since = ""
            self._set("running", at)


def _from_hook(hook: Optional[Dict], read_at: float, now: float) -> Optional[Dict]:
    """The hook notice holds until the file brings a newer line. After approving a long command the file stays
    quiet until it finishes, so the permission request has a deadline and disappears when the tab is focused in the interface."""
    if not hook or hook["at"] <= read_at:
        return None
    limit = PERMISSION_MAX_SECONDS if hook["kind"] == "waiting_permission" else STALE_SECONDS
    if now - hook["at"] > limit:
        return None
    return {"state": hook["kind"], "since": utc_iso(hook["at"]), "source": "hook"}


def resolve(raw: Optional[Dict], now: Optional[float] = None, hook: Optional[Dict] = None) -> Optional[Dict]:
    """State for the interface, or None when there is nothing to say. `maybe_waiting` is an inference: the tool may
    just be slow, so the interface must present it as a possibility."""
    now = time.time() if now is None else now
    raw = raw if isinstance(raw, dict) else {}
    name, since = raw.get("state"), raw.get("since") or ""
    started = epoch(since)
    heard = _from_hook(hook, started or 0, now)
    if heard:
        return heard
    if not started:
        return None
    age = now - started
    if age > STALE_SECONDS or (name == "running" and age > RUNNING_MAX_SECONDS):
        return None
    if name == "tool_pending":
        name = "maybe_waiting" if age >= WAITING_AFTER_SECONDS else "running"
    if name not in ("running", "your_turn", "maybe_waiting"):
        return None
    return {"state": name, "since": since, "source": "jsonl"}
