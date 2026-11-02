"""vt-19 C4: retomar uma sessão de agente numa aba nova, na pasta e no tema dela."""

import json

from tests import test_agents_api
from tests.test_pty import wait_for

CLAUDE_ID = "44444444-5555-4666-8777-888888888888"
CODEX_ID = "019a7777-0000-7000-8000-000000000001"


class ResumeApiTest(test_agents_api.AgentsServerCase):
    def setUp(self):
        super().setUp()
        self.project = self.tmp / "loja"
        self.project.mkdir()
        claude = self.tmp / "claude" / "projects" / "-loja" / f"{CLAUDE_ID}.jsonl"
        claude.parent.mkdir(parents=True)
        claude.write_text(json.dumps({"type": "user", "timestamp": "2026-10-31T10:00:00Z", "cwd": str(self.project),
                                      "message": {"content": "oi"}}) + "\n")
        codex = self.tmp / "codex" / "sessions" / "2026" / "10" / "31" / f"rollout-2026-10-31T10-00-00-{CODEX_ID}.jsonl"
        codex.parent.mkdir(parents=True)
        codex.write_text(json.dumps({"timestamp": "2026-10-31T10:00:00Z", "type": "session_meta",
                                     "payload": {"id": CODEX_ID, "cwd": str(self.project)}}) + "\n")
        self.app.agents.refresh()

    def tearDown(self):
        self.app.terminals.close_all()
        super().tearDown()

    def resume(self, sid):
        status, data, _ = self.request("POST", f"/api/agents/sessions/{sid}/resume", body={})
        return status, data

    def test_claude_retoma_com_o_id_na_pasta_da_sessao(self):
        status, info = self.resume(CLAUDE_ID)
        self.assertEqual(status, 201, info)
        self.assertEqual(info["cwd"], str(self.project))
        self.assertIn(info["theme"], ("homebrew", "classico", "oceano", "ardosia"))
        pty = self.app.terminals.get(info["id"])
        expected = f"claude --resume {CLAUDE_ID}".encode()
        self.assertTrue(wait_for(lambda: expected in pty.history()), pty.history())
        self.assertEqual([c["cmd"] for c in self.app.hub.sessions.get(info["id"]).commands], [f"claude --resume {CLAUDE_ID}"])

    def test_codex_usa_o_subcomando_resume(self):
        status, info = self.resume(CODEX_ID)
        self.assertEqual(status, 201, info)
        pty = self.app.terminals.get(info["id"])
        self.assertTrue(wait_for(lambda: f"codex resume {CODEX_ID}".encode() in pty.history()), pty.history())

    def test_tema_da_aba_pareada_e_reaproveitado(self):
        record = self.app.hub.sessions.create("aba000000777", "loja", None, str(self.project), theme="ardosia")
        record.created_at = "2026-10-31T09:59:59Z"
        status, info = self.resume(CLAUDE_ID)
        self.assertEqual(info["theme"], "ardosia")

    def test_erros(self):
        status, _ = self.resume("nao-existe")
        self.assertEqual(status, 404)
        status, data = self.resume("11111111-2222-4333-8444-555555555555")  # fixture com pasta que não existe aqui
        self.assertEqual(status, 409)
        self.assertIn("pasta", data["error"])
