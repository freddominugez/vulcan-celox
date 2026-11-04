import json
import os
import time
from pathlib import Path

from tests.server_helpers import ServerTestCase
from tests.test_ai_config import KEY, FakeTransport
from vulcan_celox.core.keychain import MemoryKeyStore


def wait_job(test, target, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jobs = [j for j in test.request("GET", "/api/ai/jobs")[1]["jobs"] if j["target"] == target]
        if jobs and jobs[0]["status"] != "running":
            return jobs[0]
        time.sleep(0.05)
    test.fail("tarefa de IA não terminou")


class SlowTransport(FakeTransport):
    def __init__(self, *responses, delay=0.0):
        super().__init__(*responses)
        self.delay = delay

    def __call__(self, method, url, headers, body, timeout):
        if url.endswith("/v1/messages"):
            time.sleep(self.delay)
        return super().__call__(method, url, headers, body, timeout)


ANSWER = {"model": "claude-sonnet-5", "stop_reason": "end_turn",
          "content": [{"type": "text", "text": "# Migrations da loja\n\n## Resumo\nRodou as migrations."}]}


class AiDocsBase(ServerTestCase):
    def env(self):
        env = super().env()
        env["SHELL"] = "/bin/sh"
        env["PATH"] = os.environ.get("PATH", "")
        return env

    def setUp(self):
        super().setUp()
        (self.tmp / "loja").mkdir()
        self.app.store.save("sites", {"loja": str(self.tmp / "loja")})
        self.app.keystore = MemoryKeyStore()
        self.transport = SlowTransport((200, ANSWER))
        self.app.ai_transport = self.transport

    def closed_session(self):
        info = self.request("POST", "/api/terminals", body={"site": "loja"})[1]
        self.app.hub.sessions.add_commands(info["id"], ["export DB_PASSWORD=segredo123", "php artisan migrate"])
        self.request("POST", "/api/tasks", body={"terminal": info["id"], "title": "Rodar seeders"})
        self.request("DELETE", f"/api/terminals/{info['id']}")
        return info["id"]


class AiDocsTest(AiDocsBase):
    def test_sem_chave_409(self):
        sid = self.closed_session()
        preview = self.request("GET", f"/api/ai/preview/session/{sid}")[1]
        self.assertFalse(preview["configured"])
        self.assertEqual(preview["redactions"], 1)
        self.assertEqual(self.request("POST", f"/api/ai/docs/session/{sid}")[0], 409)
        self.assertEqual(self.transport.calls, [])

    def test_gera_documentacao_mascarada_e_indice(self):
        self.app.keystore.set(KEY)
        sid = self.closed_session()
        status, job, _ = self.request("POST", f"/api/ai/docs/session/{sid}")
        self.assertEqual((status, job["status"]), (202, "running"))
        done = wait_job(self, sid)
        self.assertEqual(done["status"], "done", done)
        doc = Path(done["file"])
        self.assertTrue(doc.name.endswith(f"{sid}.doc.md"))
        text = doc.read_text(encoding="utf-8")
        self.assertIn("# Migrations da loja", text)
        self.assertIn("Gerado por IA (claude-sonnet-5)", text)

        sent = json.loads(self.transport.calls[-1]["body"])
        prompt = sent["messages"][0]["content"]
        self.assertIn("php artisan migrate", prompt)
        self.assertIn("Rodar seeders", prompt)
        self.assertNotIn("segredo123", prompt)
        self.assertIn("1 segredos mascarados", done["message"])

        self.assertIn(doc.name, self.request("GET", "/api/sessions/tree")[1]["closed"][0]["memory_file"][:-3] + ".doc.md")
        self.assertTrue(self.request("GET", "/api/sessions/tree")[1]["closed"][0]["has_doc"])
        index = self.request("GET", "/api/index/general")[1]["markdown"]
        self.assertIn(".doc.md", index)
        self.assertIn("Rodou as migrations", self.request("GET", f"/api/sessions/{sid}/doc")[1]["markdown"])

    def test_em_andamento_409_e_falha_legivel(self):
        self.app.keystore.set(KEY)
        sid = self.closed_session()
        self.transport.delay = 0.6
        self.assertEqual(self.request("POST", f"/api/ai/docs/session/{sid}")[0], 202)
        self.assertEqual(self.request("POST", f"/api/ai/docs/session/{sid}")[0], 409)
        self.assertEqual(wait_job(self, sid)["status"], "done")

        self.app.ai_transport = FakeTransport((401, {"error": {"message": "invalid x-api-key"}}))
        self.request("POST", f"/api/ai/docs/session/{sid}")
        time.sleep(0.1)
        failed = wait_job(self, sid)
        self.assertEqual(failed["status"], "failed")
        self.assertIn("chave recusada", failed["message"])
        self.assertEqual(self.request("GET", "/api/sessions/abc123/doc")[0], 404)


GENERAL = {"model": "claude-sonnet-5", "stop_reason": "end_turn",
           "content": [{"type": "text", "text": "# Documentação dos projetos\n\n## loja\n### Visão geral\nLoja em Laravel."}]}


class AiGeneralDocsTest(AiDocsBase):
    def test_documentacao_geral(self):
        self.assertEqual(self.request("GET", "/api/index/documentation")[0], 404)
        self.app.keystore.set(KEY)
        self.assertEqual(self.request("POST", "/api/ai/docs/general")[0], 409)  # no sessions
        sid = self.closed_session()
        self.request("POST", f"/api/ai/docs/session/{sid}")
        self.assertEqual(wait_job(self, sid)["status"], "done")

        self.app.ai_transport = SlowTransport((200, GENERAL))
        preview = self.request("GET", "/api/ai/preview/general")[1]
        self.assertEqual(preview["stats"]["sessions"], 1)
        status, job, _ = self.request("POST", "/api/ai/docs/general")
        self.assertEqual(status, 202)
        done = wait_job(self, "all")
        self.assertEqual(done["status"], "done", done)
        self.assertTrue(done["file"].endswith("DOCUMENTACAO.md"))

        prompt = json.loads(self.app.ai_transport.calls[-1]["body"])["messages"][0]["content"]
        self.assertIn("Documentação da sessão:", prompt)  # uses the session documentation already generated
        self.assertIn(".doc.md", prompt)
        self.assertNotIn("vulcan:documentacao", prompt)
        self.assertNotIn("segredo123", prompt)

        data = self.request("GET", "/api/index/documentation")[1]
        self.assertIn("# Documentação dos projetos", data["markdown"])
        self.assertIn("(DOCUMENTACAO.md)", self.request("GET", "/api/index/general")[1]["markdown"])
