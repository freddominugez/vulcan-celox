"""Possível loop: o mesmo comando de teste rodou 3 vezes ou mais sem nenhum commit entre as execuções."""

from __future__ import annotations

from typing import Dict, Optional

from vulcan_terminal.core.agents import rules

THRESHOLD = 3
_MAX_KEYS = 20


class LoopTracker:
    """Conta execuções por teste desde o último commit. Estado serializável para a leitura incremental."""

    def __init__(self, state: Optional[Dict] = None):
        self.runs: Dict[str, Dict] = dict((state or {}).get("runs") or {})

    def state(self) -> Dict:
        return {"runs": self.runs}

    def reset(self) -> None:
        """Chamado pelo montador quando um commit dá certo."""
        self.runs = {}

    def feed(self, text: str, at: str) -> None:
        if rules.publish_level(text):
            return  # publicação não é teste; quem zera é o commit que deu certo (reset)
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
