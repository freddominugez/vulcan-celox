"""Leitor incremental dos rollouts do Codex CLI (docs/en/agent-file-formats.md, seção 2)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from vulcan_terminal.core.agents import rules
from vulcan_terminal.core.agents.builder import SessionBuilder
from vulcan_terminal.core.agents.model import AgentSession, as_int, as_str, epoch

UUID_TAIL = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
SHELL_TOOLS = ("shell", "container.exec", "exec_command", "local_shell")
# contexto que o Codex injeta como mensagem de usuário
INJECTED = ("<", "#")


def new_session(path: Path) -> AgentSession:
    stem = Path(path).name.split(".jsonl")[0]  # também rollout-...jsonl.zst
    match = UUID_TAIL.search(stem)
    return AgentSession(id=match.group(1) if match else stem, agent="codex", file_path=str(path))


def _texts(content) -> str:
    if not isinstance(content, list):
        return content if isinstance(content, str) else ""
    return "\n".join(b["text"] for b in content if isinstance(b, dict) and isinstance(b.get("text"), str))


def _arguments(payload: dict):
    raw = payload.get("arguments", payload.get("input"))
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


def _command_text(args) -> str:
    if isinstance(args, dict):
        args = args.get("command", args.get("cmd"))
    if isinstance(args, list):
        parts = [str(a) for a in args]
        if len(parts) >= 3 and parts[1] in ("-lc", "-c"):  # ["bash", "-lc", "<script>"]
            return parts[2]
        return " ".join(parts)
    return args if isinstance(args, str) else ""



def session_origin(meta: dict) -> str:
    """Subagente e app desktop não nascem de uma aba do terminal. Terminal e versão antiga: vazio."""
    source = meta.get("source")
    if (isinstance(source, dict) and "subagent" in source) or meta.get("thread_source") == "subagent":
        return "subagent"
    return "desktop" if "desktop" in str(meta.get("originator") or "").lower() else ""


class CodexReader:
    agent = "codex"

    def __init__(self, session: AgentSession, state: Optional[Dict] = None):
        state = state or {}
        self.b = SessionBuilder(session, state.get("builder"))
        self.session = session
        self.meta = bool(state.get("meta"))
        self.items = bool(state.get("items"))  # comandos e arquivos vêm por item_completed: ignorar function_call
        self.ev_turns = int(state.get("ev_turns", 0))
        self.fb_turns = int(state.get("fb_turns", 0))
        self.fb_first: Optional[str] = state.get("fb_first")
        self.last_user: list = list(state.get("last_user") or ["", None])  # [texto, epoch]
        self.last_cmd: List[str] = list(state.get("last_cmd") or ["", ""])
        self.last_total: Dict = dict(state.get("last_total") or {})  # último total acumulado
        self.usage_seq = int(state.get("usage_seq", 0))
        self.usage_rows: list = []

    def state(self) -> Dict:
        return {"builder": self.b.state(), "meta": self.meta, "items": self.items, "ev_turns": self.ev_turns,
                "fb_turns": self.fb_turns, "fb_first": self.fb_first, "last_user": self.last_user,
                "last_cmd": self.last_cmd, "last_total": self.last_total, "usage_seq": self.usage_seq}

    def drain_usage(self) -> list:
        out, self.usage_rows = self.usage_rows, []
        return out

    def feed(self, obj: dict) -> None:
        kind = obj.get("type")
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        at = as_str(obj.get("timestamp"))
        self.b.seen_at(at)  # qualquer linha datada é atividade, inclusive tipos que não lemos
        if kind == "session_meta":
            self._meta(payload)
        elif kind == "turn_context":
            if isinstance(payload.get("model"), str) and payload["model"]:
                self.session.model = payload["model"]
            self.b.set_cwd(payload.get("cwd"))
        elif kind == "event_msg":
            self._event(payload, at)
        elif kind == "response_item":
            self._response(payload, at)

    def _meta(self, p: dict) -> None:
        if self.meta:
            return  # sessão retomada: vale a primeira session_meta
        self.meta = True
        if isinstance(p.get("id"), str) and p["id"]:
            self.session.id = p["id"]
        self.b.set_cwd(p.get("cwd"))
        self.session.cli_version = as_str(p.get("cli_version")) or self.session.cli_version
        self.session.origin = session_origin(p)
        git = p.get("git") if isinstance(p.get("git"), dict) else {}
        self.b.set_branch(git.get("branch") or p.get("git_branch"))
        self.b.seen_at(p.get("timestamp"))

    def _event(self, p: dict, at: str) -> None:
        kind = p.get("type")
        if kind == "user_message":
            self._user(p.get("message"), at)
        elif kind == "agent_message":
            self.b.assistant_text(p.get("message"), at)
        elif kind == "token_count":
            total = (p.get("info") or {}).get("total_token_usage") if isinstance(p.get("info"), dict) else None
            if isinstance(total, dict):
                cached = as_int(total.get("cached_input_tokens"))
                self.b.add_tokens(max(0, as_int(total.get("input_tokens")) - cached), as_int(total.get("output_tokens")),
                                  cached, as_int(total.get("cache_write_input_tokens")), replace=True)
                self._usage(total, at)
        elif kind == "item_completed" and isinstance(p.get("item"), dict):
            self._item(p["item"], at)

    def _usage(self, total: dict, at: str) -> None:
        """O Codex grava o total acumulado; o consumo de cada evento é a diferença para o anterior.
        Um total menor que o anterior (sessão retomada do zero) recomeça a conta a partir dele."""
        cached = as_int(total.get("cached_input_tokens"))
        cur = {"input": max(0, as_int(total.get("input_tokens")) - cached), "output": as_int(total.get("output_tokens")),
               "cache_read": cached, "cache_write_5m": as_int(total.get("cache_write_input_tokens")),
               "reasoning": as_int(total.get("reasoning_output_tokens"))}
        last = self.last_total
        restart = any(cur[k] < as_int(last.get(k)) for k in cur)
        delta = dict(cur) if restart or not last else {k: cur[k] - as_int(last.get(k)) for k in cur}
        self.last_total = cur
        if not any(delta.values()):
            return  # o Codex repete o mesmo total em eventos seguidos
        self.usage_seq += 1
        self.usage_rows.append({"key": f"t{self.usage_seq}", "at": at, "model": self.session.model or "",
                                "cache_write_1h": 0, **delta})

    def _item(self, item: dict, at: str) -> None:
        kind = item.get("type")
        if kind == "UserMessage":
            self._user(_texts(item.get("content")), at)
        elif kind == "AgentMessage":
            self.b.assistant_text(_texts(item.get("content")), at)
        elif kind == "CommandExecution":
            self.items = True
            raw = item.get("parsed_cmd") if isinstance(item.get("parsed_cmd"), list) else []
            parsed = [c["cmd"] for c in raw if isinstance(c, dict) and isinstance(c.get("cmd"), str) and c["cmd"]]
            text = "; ".join(parsed) if parsed else _command_text(item.get("command"))
            self._command(text, at, item.get("exit_code"))
        elif kind == "FileChange" and isinstance(item.get("changes"), dict):
            self.items = True
            for path, change in item["changes"].items():
                change = change if isinstance(change, dict) else {}
                self.b.file(path, rules.CODEX_CHANGE_KINDS.get(change.get("type"), "edit"), at)
                if change.get("move_path"):
                    self.b.file(change["move_path"], "new", at)

    def _response(self, p: dict, at: str) -> None:
        kind = p.get("type")
        if kind == "message" and p.get("role") == "user":
            text = _texts(p.get("content")).strip()
            if text and not text.startswith(INJECTED):
                self.fb_turns += 1
                self.fb_first = self.fb_first or text[:500]
                self._refresh_turns()
            return
        if kind not in ("function_call", "custom_tool_call") or self.items:
            return
        name = p.get("name") or ""
        args = _arguments(p)
        if name == "apply_patch":
            text = args.get("input", args.get("patch", "")) if isinstance(args, dict) else (args or "")
            for effect in rules.patch_effects(text):
                self.b.apply(effect, at)
        elif name in SHELL_TOOLS:
            text = _command_text(args)
            for effect in rules.patch_effects(text):  # apply_patch por heredoc dentro do shell
                self.b.apply(effect, at)
            self._command(text, at, None)

    def _user(self, text, at: str) -> None:
        text = as_str(text).strip()
        when = epoch(at)
        last_text, last_when = self.last_user
        if not text or (text == last_text and (when is None or last_when is None or abs(when - last_when) <= 2)):
            return  # o mesmo pedido chega como user_message e como UserMessage; o mesmo texto noutro turno conta
        self.last_user = [text, when]
        self.ev_turns += 1
        self.b.user_turn(text, at)
        self._refresh_turns()

    def _command(self, text, at: str, exit_code) -> None:
        text = as_str(text).strip()
        if not text or [text, at[:19]] == self.last_cmd:
            return
        self.last_cmd = [text, at[:19]]
        self.b.command(text, at, exit_code if isinstance(exit_code, int) else None)

    def _refresh_turns(self) -> None:
        s = self.session
        if self.ev_turns:
            s.turns = self.ev_turns
        else:
            s.turns = self.fb_turns
            s.first_user_message = s.first_user_message or self.fb_first
