"""Monta um AgentSession a partir de fatos já extraídos pelos leitores; estado serializável para leitura incremental."""

from __future__ import annotations

from typing import Dict, List, Optional

from vulcan_celox.core.agents import rules
from vulcan_celox.core.agents.loops import LoopTracker
from vulcan_celox.core.agents.model import MAX_COMMANDS, AgentSession, CommandRun, FileTouch, SessionEvent, as_int, as_str

MAX_EVENT_TEXT = 2000
_PUB_LEVELS = ("none", "committed", "pushed")
_KIND_RANK = {"read": 0, "edit": 1, "new": 2, "delete": 3}


def clip(text, limit: int = MAX_EVENT_TEXT) -> str:
    text = as_str(text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class SessionBuilder:
    def __init__(self, session: AgentSession, state: Optional[Dict] = None):
        self.session = session
        state = state or {}
        self.pub = int(state.get("pub", 0))
        self.extra: Dict = dict(state.get("extra") or {})
        self.loops = LoopTracker(state.get("loops"))
        self.events: List[SessionEvent] = []
        self._files = {f.path: f for f in session.files}

    def state(self) -> Dict:
        return {"pub": self.pub, "extra": self.extra, "loops": self.loops.state()}

    def drain_events(self) -> List[SessionEvent]:
        out, self.events = self.events, []
        return out

    # ── tempo e identidade ─────────────────────────────────────────────────
    def seen_at(self, at) -> None:
        if not isinstance(at, str) or not at:
            return  # data numérica ou ausente: não serve para ordenar com as ISO
        s = self.session
        if not s.started_at or at < s.started_at:
            s.started_at = at
        if at > s.last_activity_at:
            s.last_activity_at = at

    def set_cwd(self, cwd) -> None:
        if isinstance(cwd, str) and cwd and not self.session.cwd:
            root, worktree = rules.split_worktree(cwd)
            self.session.cwd = cwd
            self.session.project_root = root
            self.session.worktree = worktree
            self.session.project_name = rules.project_name(cwd)

    def set_branch(self, branch) -> None:
        if isinstance(branch, str) and branch and branch != "HEAD":
            self.session.git_branch = branch

    # ── conversa ──────────────────────────────────────────────────────────
    def user_turn(self, text: str, at: str) -> None:
        text = clip(text)
        if not text:
            return
        s = self.session
        s.turns += 1
        if not s.first_user_message:
            s.first_user_message = clip(text, 500)
        self.events.append(SessionEvent(at, "user", text))

    def assistant_text(self, text: str, at: str) -> None:
        text = clip(text)
        if text:
            self.events.append(SessionEvent(at, "assistant", text))

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0, cache_read: int = 0, cache_write: int = 0,
                   replace: bool = False) -> None:
        current = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0} if replace or not self.session.tokens \
            else dict(self.session.tokens)
        for key, value in (("input", input_tokens), ("output", output_tokens),
                           ("cache_read", cache_read), ("cache_write", cache_write)):
            current[key] += as_int(value)
        self.session.tokens = current

    # ── efeitos ────────────────────────────────────────────────────────────
    def apply(self, effect: tuple, at: str, exit_code: Optional[int] = None) -> None:
        if effect[0] == "file":
            self.file(effect[1], effect[2], at)
        elif effect[0] == "command":
            self.command(effect[1], at, exit_code)

    def file(self, path, kind: str, at) -> None:
        if not isinstance(path, str) or not path:
            return
        at = as_str(at)
        known = self._files.get(path)
        if kind == "write":
            kind = "edit" if known else "new"
        if known:
            if _KIND_RANK[kind] > _KIND_RANK[known.kind] and not (known.kind == "new" and kind == "edit"):
                known.kind = kind
            known.last_at = at or known.last_at
        else:
            known = FileTouch(path, kind, at, at)
            self._files[path] = known
            self.session.files.append(known)
        if kind != "read":
            self.pub = 0  # há mudança sem commit de novo
        self._refresh_published()
        self.events.append(SessionEvent(at, "file", path, kind))

    def command(self, text, at, exit_code: Optional[int] = None, publish: bool = True) -> None:
        """Registra o comando. Publica na hora se `publish` e se não falhou; o Claude adia até o tool_result."""
        text = as_str(text).strip()
        at = as_str(at)
        if not text:
            return
        s = self.session
        kind = rules.classify_command(text)
        s.commands.append(CommandRun(clip(text, 1000), at, kind, exit_code))
        if len(s.commands) > MAX_COMMANDS:
            del s.commands[: len(s.commands) - MAX_COMMANDS]
        s.commands_total += 1
        self.loops.feed(text, at)
        if publish and (exit_code is None or exit_code == 0):
            self.publish(text)
        s.loop_alert = self.loops.alert()
        self.events.append(SessionEvent(at, "command", clip(text), kind))

    def publish(self, text: str) -> None:
        """Aplica commit, push e PR na ordem em que aparecem; cada etapa exige a anterior desde a última edição."""
        s = self.session
        for level in rules.publish_sequence(text):
            if level == "committed":
                self.pub = max(self.pub, 1)
                self.loops.reset()
            elif level == "pushed" and self.pub >= 1:
                self.pub = 2
            elif level == "pr_open" and self.pub >= 2:
                s.pr_opened = True
        s.loop_alert = self.loops.alert()
        self._refresh_published()

    def mark_failed(self, text: str, at: str, exit_code: int = 1) -> None:
        for run in reversed(self.session.commands):
            if run.at == at and run.text == clip(text, 1000):
                run.exit_code = exit_code
                return

    def _refresh_published(self) -> None:
        s = self.session
        s.published = "pr_open" if self.pub >= 2 and s.pr_opened else _PUB_LEVELS[self.pub]
