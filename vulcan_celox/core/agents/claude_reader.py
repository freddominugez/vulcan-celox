"""Leitor incremental dos JSONL do Claude Code (docs/en/agent-file-formats.md, seção 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from vulcan_celox.core.agents import rules
from vulcan_celox.core.agents.attention import AttentionTracker
from vulcan_celox.core.agents.builder import SessionBuilder
from vulcan_celox.core.agents.model import AgentSession, as_int, as_str

# texto de usuário que é o próprio Claude Code falando, não um pedido
NOT_A_PROMPT = ("<command-name>", "<command-message>", "<command-args>", "<local-command-", "<system-reminder>",
                "Caveat:", "[Request interrupted")
_RECENT_IDS = 64


def new_session(path: Path) -> AgentSession:
    return AgentSession(id=Path(path).stem, agent="claude", file_path=str(path))


class ClaudeReader:
    agent = "claude"

    def __init__(self, session: AgentSession, state: Optional[Dict] = None):
        state = state or {}
        self.b = SessionBuilder(session, state.get("builder"))
        self.session = session
        self.att = AttentionTracker(session, state.get("attention"))
        self.cur_id: Optional[str] = state.get("cur_id")
        self.cur_usage: Dict = dict(state.get("cur_usage") or {})
        self.recent_ids = list(state.get("recent_ids") or [])
        self.done_tokens: Dict = dict(state.get("done_tokens") or {})
        # publicação do Bash espera o tool_result: só conta se não voltou com is_error
        self.pending_pub: Dict[str, list] = dict(state.get("pending_pub") or {})
        self.cur_row: Dict = dict(state.get("cur_row") or {})  # linha de uso do turno aberto
        self.usage_rows: list = []

    def state(self) -> Dict:
        return {"builder": self.b.state(), "cur_id": self.cur_id, "cur_usage": self.cur_usage,
                "recent_ids": self.recent_ids, "done_tokens": self.done_tokens, "pending_pub": self.pending_pub,
                "cur_row": self.cur_row, "attention": self.att.state()}

    def drain_usage(self) -> list:
        out, self.usage_rows = self.usage_rows, []
        return out

    def feed(self, obj: dict) -> None:
        kind = obj.get("type")
        if kind == "ai-title":
            title = obj.get("aiTitle")
            if isinstance(title, str) and title.strip():
                self.session.title = title.strip()
            return
        if kind == "system":
            if obj.get("subtype") == "turn_duration" and not obj.get("isSidechain"):
                self.att.turn_ended(as_str(obj.get("timestamp")))
            return
        if kind not in ("user", "assistant"):
            return  # api-request-blob e afins repetem mensagens: contar duplicaria tudo
        at = as_str(obj.get("timestamp"))
        self.b.seen_at(at)
        if obj.get("isSidechain"):
            return  # sub-agente no formato antigo: é atividade, mas não conteúdo da sessão principal
        self.b.set_cwd(obj.get("cwd"))
        self.b.set_branch(obj.get("gitBranch"))
        if isinstance(obj.get("version"), str):
            self.session.cli_version = obj["version"]
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        if kind == "user":
            self._user(obj, message, at)
        else:
            self._assistant(message, at)

    def _user(self, obj: dict, message: dict, at: str) -> None:
        if obj.get("isMeta"):
            return
        content = message.get("content")
        if isinstance(content, list):
            self._tool_results(content, at)
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(as_str(b.get("text")) for b in content if isinstance(b, dict) and b.get("type") == "text")
        else:
            return
        if text.lstrip().startswith("[Request interrupted"):
            self.att.turn_ended(at)
        if text.strip() and not text.lstrip().startswith(NOT_A_PROMPT):
            self.att.turn_started(at)
            self.b.user_turn(text, at)

    def _assistant(self, message: dict, at: str) -> None:
        model = message.get("model")
        if isinstance(model, str) and model and not model.startswith("<"):
            self.session.model = model
        self._tokens(message.get("id"), message.get("usage"), model, at)
        content = message.get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                self.b.assistant_text(block.get("text"), at)
            elif block.get("type") == "tool_use":
                tool_id = block.get("id")
                if isinstance(tool_id, str):
                    self.att.tool_started(tool_id, at)
                for effect in rules.claude_tool_effects(as_str(block.get("name")), block.get("input")):
                    if effect[0] == "command" and isinstance(tool_id, str) and rules.publish_level(effect[1]):
                        self.b.command(effect[1], at, publish=False)
                        self.pending_pub[tool_id] = [effect[1], at]
                        if len(self.pending_pub) > _RECENT_IDS:
                            self.pending_pub.pop(next(iter(self.pending_pub)))
                    else:
                        self.b.apply(effect, at)
        if message.get("stop_reason") == "end_turn":
            self.att.turn_ended(at)

    def _tool_results(self, content: list, at: str) -> None:
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            if isinstance(block.get("tool_use_id"), str):
                self.att.tool_finished(block["tool_use_id"], at)
            pending = self.pending_pub.pop(block.get("tool_use_id"), None) if isinstance(block.get("tool_use_id"), str) else None
            if not pending:
                continue
            if block.get("is_error"):
                self.b.mark_failed(pending[0], pending[1])
            else:
                self.b.publish(pending[0])

    def _tokens(self, mid, usage, model=None, at: str = "") -> None:
        """Um turno vira várias linhas com o mesmo message.id e o mesmo usage: conta uma vez por id."""
        if not isinstance(mid, str) or not isinstance(usage, dict) or mid in self.recent_ids:
            return
        if mid != self.cur_id:
            self._close_current()
            self.cur_id = mid
            self.cur_row = {"key": mid, "at": at}
        self.cur_usage = {"input": as_int(usage.get("input_tokens")), "output": as_int(usage.get("output_tokens")),
                          "cache_read": as_int(usage.get("cache_read_input_tokens")),
                          "cache_write": as_int(usage.get("cache_creation_input_tokens"))}
        total = dict(self.done_tokens)
        for key, value in self.cur_usage.items():
            total[key] = total.get(key, 0) + int(value)
        self.session.tokens = total
        self._usage_row(usage, model)

    def _usage_row(self, usage: dict, model) -> None:
        """Uma linha por turno para o agent_usage. A mesma chave regrava a linha (upsert no índice).
        `<synthetic>` é mensagem do próprio Claude Code (erro, interrupção): não é cobrada e fica de fora."""
        if not isinstance(model, str) or not model or model.startswith("<"):
            return
        write = as_int(usage.get("cache_creation_input_tokens"))
        split = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
        w1h = min(as_int(split.get("ephemeral_1h_input_tokens")), write)
        details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
        self.cur_row.update(model=model, input=as_int(usage.get("input_tokens")),
                            output=as_int(usage.get("output_tokens")),
                            cache_read=as_int(usage.get("cache_read_input_tokens")),
                            cache_write_5m=write - w1h, cache_write_1h=w1h,
                            reasoning=as_int(details.get("thinking_tokens")))
        self.usage_rows.append(dict(self.cur_row))

    def _close_current(self) -> None:
        if not self.cur_id:
            return
        for key, value in self.cur_usage.items():
            self.done_tokens[key] = self.done_tokens.get(key, 0) + int(value)
        self.recent_ids.append(self.cur_id)
        del self.recent_ids[:-_RECENT_IDS]
        self.cur_id, self.cur_usage, self.cur_row = None, {}, {}
