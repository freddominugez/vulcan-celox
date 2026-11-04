"""Possible loop: the same test command ran 3 times or more with no commit between the runs."""

from __future__ import annotations

from typing import Dict, Optional

from vulcan_celox.core.agents import rules

THRESHOLD = 3
_MAX_KEYS = 20


class LoopTracker:
    """Counts runs per test since the last commit. Serializable state for incremental reading."""

    def __init__(self, state: Optional[Dict] = None):
        self.runs: Dict[str, Dict] = dict((state or {}).get("runs") or {})

    def state(self) -> Dict:
        return {"runs": self.runs}

    def reset(self) -> None:
        """Called by the builder when a commit succeeds."""
        self.runs = {}

    def feed(self, text: str, at: str) -> None:
        if rules.publish_level(text):
            return  # a publish is not a test; what resets is the commit that succeeded (reset)
        key = rules.test_key(text)
        if not key:
            return
        run = self.runs.get(key)
        if run:
            run["count"] += 1
            run["last_at"] = at
        else:
            self.runs[key] = {"count": 1, "since": at, "last_at": at}
            if len(self.runs) > _MAX_KEYS:
                oldest = min(self.runs, key=lambda k: self.runs[k]["last_at"])
                del self.runs[oldest]

    def alert(self) -> Optional[Dict]:
        hits = [(r["count"], r["last_at"], key) for key, r in self.runs.items() if r["count"] >= THRESHOLD]
        if not hits:
            return None
        count, _last, key = max(hits)
        run = self.runs[key]
        return {"command": key, "count": count, "since": run["since"], "last_at": run["last_at"]}
