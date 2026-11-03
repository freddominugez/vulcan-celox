"""Em que pé está o turno de uma sessão: trabalhando, sua vez ou talvez esperando.

O leitor guarda só o fato visto no arquivo (`running`, `tool_pending`, `your_turn`) e a hora. O estado mostrado é
calculado na leitura, porque "faz tempo que a ferramenta não responde" depende do relógio, não do arquivo.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from vulcan_celox.core.agents.model import AgentSession, epoch

WAITING_AFTER_SECONDS = 20
RUNNING_MAX_SECONDS = 600  # sem linha nova por mais que isso, a sessão parou: não está trabalhando
STALE_SECONDS = 6 * 3600  # sinal antigo vira ruído: quem saiu ontem não está esperando resposta
PERMISSION_MAX_SECONDS = 1800
_MAX_PENDING = 64


def utc_iso(at: float) -> str:
    return datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AttentionTracker:
    """Acompanha o turno a partir dos eventos do leitor e deixa o resultado em `session.attention`."""

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
    """O aviso do hook vale até o arquivo trazer linha mais nova. Depois de aprovar um comando longo o arquivo fica
    quieto até ele terminar, então o pedido de permissão tem prazo e some ao focar a aba na interface."""
    if not hook or hook["at"] <= read_at:
        return None
    limit = PERMISSION_MAX_SECONDS if hook["kind"] == "waiting_permission" else STALE_SECONDS
    if now - hook["at"] > limit:
        return None
    return {"state": hook["kind"], "since": utc_iso(hook["at"]), "source": "hook"}


def resolve(raw: Optional[Dict], now: Optional[float] = None, hook: Optional[Dict] = None) -> Optional[Dict]:
    """Estado para a interface, ou None quando não há nada a dizer. `maybe_waiting` é inferência: a ferramenta pode
    só estar demorando, então a interface precisa apresentar como possibilidade."""
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
