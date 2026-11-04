"""Site harness route and summary in the agent session."""

from pathlib import Path
import json
import shutil

from tests.helpers import FIXTURES
from tests.server_helpers import ServerTestCase
from tests.test_agents_api import AgentsServerCase, CLAUDE_SID

H = FIXTURES / "harness"


class HarnessApiTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        for name in ("repo", "minimo"):
            shutil.copytree(H / name, self.tmp / name)
        (self.tmp / "vazio").mkdir()
        self.app.store.save("sites", {"repo": str(self.tmp / "repo"), "minimo": str(self.tmp / "minimo"),
                                      "vazio": str(self.tmp / "vazio")})

    def get(self, path):
        status, data, _ = self.request("GET", path)
        self.assertEqual(status, 200, data)
        return data

    def test_cada_formato(self):
        repo = self.get("/api/sites/repo/harness")
        self.assertEqual((repo["tipo"], repo["estado"], repo["proximo"]), ("repo", "ok", "C3"))
        self.assertFalse(repo["pode_instalar"])
        self.assertTrue(Path(repo["contrato"]["absoluto"]).as_posix().endswith("specs/exemplo-uso-e-custo/contract.md"))
        self.assertEqual(repo["resumo"], "exemplo-uso-e-custo: 2 de 5 itens feitos, próximo C3")
        minimo = self.get("/api/sites/minimo/harness")
        self.assertEqual((minimo["tipo"], minimo["status"]), ("minimo", "RUNNING"))
        self.assertEqual([i["estado"] for i in minimo["itens"]], ["feito", "bloqueado", "pendente"])

    def test_sem_harness_e_assinatura(self):
        vazio = self.get("/api/sites/vazio/harness")
        self.assertEqual((vazio["tipo"], vazio["pode_instalar"], vazio["itens"]), ("nenhum", True, []))
        first = self.get("/api/sites/minimo/harness")["assinatura"]
        state = self.tmp / "minimo" / ".vulcan" / "state" / "execution.json"
        data = json.loads(state.read_text())
        data["next"] = "C2"
        state.write_text(json.dumps(data) + "\n\n")
        self.assertNotEqual(self.get("/api/sites/minimo/harness")["assinatura"], first)

    def test_corrompido_e_site_inexistente(self):
        (self.tmp / "repo" / ".harness" / "state.json").write_text("{")
        info = self.get("/api/sites/repo/harness")
        self.assertEqual(info["estado"], "ilegivel")
        status, _, _ = self.request("GET", "/api/sites/nao-existe/harness")
        self.assertEqual(status, 404)
        status, _, _ = self.request("GET", "/api/sites/repo/harness", token=False)
        self.assertEqual(status, 401)


class AgentSessionHarnessTest(AgentsServerCase):
    SID = "44444444-5555-4666-8777-888888888888"

    def env(self):
        env = super().env()
        proj = self.tmp / "proj-harness"
        if not proj.exists():
            shutil.copytree(H / "minimo", proj)
            line = {"type": "user", "timestamp": "2026-10-30T10:00:00Z", "cwd": str(proj),
                    "message": {"role": "user", "content": "continue o contrato"}}
            folder = self.tmp / "claude" / "projects" / "-proj-harness"
            folder.mkdir(parents=True)
            (folder / f"{self.SID}.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
        return env

    def test_sessao_do_projeto_com_harness_traz_a_linha(self):
        self.assertIsNone(self.get(f"/api/agents/sessions/{CLAUDE_SID}")["session"]["harness"])
        self.app.store.save("sites", {"proj": str(self.tmp / "proj-harness")})
        line = self.get(f"/api/agents/sessions/{self.SID}")["session"]["harness"]
        self.assertEqual(line, {"site": "proj", "line": "drive-upload-retry: 1 de 3 itens feitos, próximo C3"})
