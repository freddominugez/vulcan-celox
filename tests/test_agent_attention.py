"""Turn state read from both agents. The lines are synthetic, in the format seen in real Claude Code and
Codex 0.166.0 sessions, because the anonymized fixtures do not keep `stop_reason` or `turn_duration`."""

import json
import unittest

from tests.helpers import TempDirTestCase
from vulcan_celox.core.agents import attention
from vulcan_celox.core.agents.claude_reader import ClaudeReader, new_session as new_claude
from vulcan_celox.core.agents.codex_reader import CodexReader, new_session as new_codex
from vulcan_celox.core.agents.index import AgentIndex
from vulcan_celox.core.agents.model import epoch
from vulcan_celox.server.agents_api import card

T0 = "2026-11-02T10:00:00Z"
T1 = "2026-11-02T10:00:30Z"
T2 = "2026-11-02T10:01:00Z"
NOW = epoch(T2)


def claude_user(text, at, **extra):
    return {"type": "user", "timestamp": at, "message": {"role": "user", "content": text}, **extra}


def claude_tool(tid, at):
    return {"type": "assistant", "timestamp": at,
            "message": {"id": f"m{tid}", "stop_reason": "tool_use", "content": [{"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": "sleep 900"}}]}}


def claude_result(tid, at):
    return {"type": "user", "timestamp": at, "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": "ok"}]}}


def claude_end(at):
    return {"type": "assistant", "timestamp": at, "message": {"id": "fim", "stop_reason": "end_turn", "content": [{"type": "text", "text": "pronto"}]}}


def read_claude(*lines):
    session = new_claude("/tmp/s.jsonl")
    reader = ClaudeReader(session)
    for line in lines:
        reader.feed(line)
    return session, reader


def codex_event(kind, at):
    return {"type": "event_msg", "timestamp": at, "payload": {"type": kind}}


def read_codex(*lines):
    session = new_codex("/tmp/rollout-2026-11-02T10-00-00-019a0000-0000-7000-8000-000000000000.jsonl")
    reader = CodexReader(session)
    for line in lines:
        reader.feed(line)
    return session


class ClaudeTest(unittest.TestCase):
    def state(self, *lines, now=NOW):
        session, _ = read_claude(*lines)
        return (attention.resolve(session.attention, now) or {}).get("state")

    def test_pedido_novo_trabalha(self):
        self.assertEqual(self.state(claude_user("faça", T2)), "running")

    def test_fim_de_turno_e_sua_vez(self):
        self.assertEqual(self.state(claude_user("faça", T0), claude_end(T1)), "your_turn")

    def test_turn_duration_e_sua_vez(self):
        self.assertEqual(self.state(claude_user("faça", T0), {"type": "system", "subtype": "turn_duration", "timestamp": T1}), "your_turn")

    def test_ferramenta_sem_resposta_e_so_possibilidade(self):
        self.assertEqual(self.state(claude_tool("a", T0)), "maybe_waiting")
        self.assertEqual(self.state(claude_tool("a", T2)), "running")

    def test_comando_longo_com_resposta_volta_a_trabalhar(self):
        self.assertEqual(self.state(claude_tool("a", T0), claude_result("a", T2)), "running")

    def test_duas_ferramentas_contam_da_mais_antiga(self):
        session, _ = read_claude(claude_tool("a", T0), claude_tool("b", T1), claude_result("b", T1))
        self.assertEqual(session.attention, {"state": "tool_pending", "since": T0})

    def test_interrupcao_e_sua_vez(self):
        self.assertEqual(self.state(claude_tool("a", T0), claude_user("[Request interrupted by user]", T1)), "your_turn")

    def test_subagente_nao_encerra_o_turno(self):
        lines = (claude_user("faça", T2), {"type": "system", "subtype": "turn_duration", "timestamp": T2, "isSidechain": True})
        self.assertEqual(self.state(*lines), "running")

    def test_leitura_incremental_lembra_a_ferramenta(self):
        session, reader = read_claude(claude_tool("a", T0))
        again = ClaudeReader(session, json.loads(json.dumps(reader.state())))
        again.feed(claude_result("a", T1))
        self.assertEqual(session.attention, {"state": "running", "since": T1})


class CodexTest(unittest.TestCase):
    def test_turno(self):
        self.assertEqual(read_codex(codex_event("task_started", T0)).attention["state"], "running")
        self.assertEqual(read_codex(codex_event("task_started", T0), codex_event("task_complete", T1)).attention["state"], "your_turn")

    def test_turno_abortado_e_sua_vez(self):
        self.assertEqual(read_codex(codex_event("task_started", T0), codex_event("turn_aborted", T1)).attention["state"], "your_turn")


class ResolveTest(unittest.TestCase):
    def test_sem_dado(self):
        for raw in (None, {}, "x", {"state": "your_turn"}, {"state": "outro", "since": T0}):
            self.assertIsNone(attention.resolve(raw, NOW))

    def test_sinal_antigo_some(self):
        self.assertIsNone(attention.resolve({"state": "your_turn", "since": T0}, epoch(T0) + attention.STALE_SECONDS + 1))
        self.assertIsNone(attention.resolve({"state": "tool_pending", "since": T0}, epoch(T0) + attention.STALE_SECONDS + 1))

    def test_trabalhando_sem_linha_nova_parou(self):
        self.assertIsNone(attention.resolve({"state": "running", "since": T0}, epoch(T0) + attention.RUNNING_MAX_SECONDS + 1))

    def test_espera_longa_continua_visivel(self):
        self.assertEqual(attention.resolve({"state": "tool_pending", "since": T0}, epoch(T0) + 3000)["state"], "maybe_waiting")


class IndiceTest(TempDirTestCase):
    def test_chega_ao_cartao_pelo_indice(self):
        path = self.tmp / "s.jsonl"
        path.write_text("\n".join(json.dumps(x) for x in (claude_user("faça", T0), claude_end(T1))) + "\n", encoding="utf-8")
        index = AgentIndex(self.tmp / "a.db")
        try:
            index.update_file("claude", path)
            session = index.sessions()[0]
            self.assertEqual(session.attention, {"state": "your_turn", "since": T1})
            self.assertIn("attention", card(session))
        finally:
            index.close()


if __name__ == "__main__":
    unittest.main()
