"""Attention signals route: who shows up, with the hook taking precedence over the file."""

import json
import time
from datetime import datetime, timezone

from tests.test_agents_api import AgentsServerCase
from vulcan_celox.core.agents import attention_hook

SID = "33333333-4444-4555-8666-777777777777"


def iso(at):
    return datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AttentionApiTest(AgentsServerCase):
    def write_session(self, *lines):
        path = self.tmp / "claude" / "projects" / "-Users-dev-loja" / f"{SID}.jsonl"
        path.write_text("".join(json.dumps(o) + "\n" for o in lines), encoding="utf-8")
        self.app.agents.refresh()

    def items(self):
        return {i["session"]: i for i in self.get("/api/agents/attention")["items"]}

    def fim_de_turno(self, at):
        return {"type": "assistant", "timestamp": iso(at), "cwd": "/Users/dev/loja", "message": {"id": "f", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}}

    def test_sua_vez_aparece_e_sessao_antiga_nao(self):
        self.write_session(self.fim_de_turno(time.time() - 10))
        items = self.items()
        self.assertEqual(items[SID]["state"], "your_turn")
        self.assertEqual(items[SID]["source"], "jsonl")
        self.assertEqual(items[SID]["project"], "loja")
        self.assertNotIn("11111111-2222-4333-8444-555555555555", items)  # October fixture: past the deadline

    def test_trabalhando_nao_entra(self):
        self.write_session({"type": "user", "timestamp": iso(time.time() - 5), "cwd": "/Users/dev/loja", "message": {"role": "user", "content": "faça"}})
        self.assertNotIn(SID, self.items())

    def test_hook_mais_novo_vence(self):
        self.write_session(self.fim_de_turno(time.time() - 60))
        folder = attention_hook.attention_dir(self.app.data_dir)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{SID}.json").write_text(json.dumps({"session_id": SID, "kind": "waiting_permission", "at": time.time() - 1}))
        got = self.items()[SID]
        self.assertEqual((got["state"], got["source"]), ("waiting_permission", "hook"))

    def test_exige_token(self):
        self.assertEqual(self.request("GET", "/api/agents/attention", token=False)[0], 401)
