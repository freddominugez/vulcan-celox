"""Which paths printed in a tab exist inside a known root."""

import json
import os
from types import SimpleNamespace

from tests.test_agents_api import AgentsServerCase
from tests.test_node_api import FakeTerminals

TAB = "0000abcd"
SID = "99999999-5555-4666-8777-888888888888"


class CodeResolveTest(AgentsServerCase):
    def setUp(self):
        super().setUp()
        self.project = (self.tmp / "projeto").resolve()
        (self.project / "sub").mkdir(parents=True)
        (self.project / "sub" / "a.py").write_text("x", encoding="utf-8")
        (self.project / ".env").write_text("x", encoding="utf-8")
        (self.tmp / "fora.txt").write_text("x", encoding="utf-8")
        self.real_terminals = self.app.terminals
        self.app.terminals = FakeTerminals()
        self.app.terminals.items = {TAB: SimpleNamespace(cwd=str(self.project))}

    def tearDown(self):
        self.app.terminals = self.real_terminals
        super().tearDown()

    def resolve(self, *candidates, terminal=TAB):
        status, data, _ = self.request("POST", "/api/code/resolve", {"terminal": terminal, "candidates": list(candidates)})
        return status, data

    def test_relativo_e_absoluto(self):
        status, data = self.resolve("sub/a.py", str(self.project / "sub" / "a.py"), "./sub/a.py", "sub")
        self.assertEqual(status, 200)
        self.assertEqual(data["results"]["sub/a.py"]["path"], str(self.project / "sub" / "a.py"))
        self.assertEqual(data["results"]["sub/a.py"]["kind"], "file")
        self.assertIn(str(self.project / "sub" / "a.py"), data["results"])
        self.assertEqual(data["results"]["sub"]["kind"], "dir")

    def test_inexistente_nao_responde(self):
        self.assertEqual(self.resolve("nada.py")[1]["results"], {})

    def test_fora_da_raiz(self):
        results = self.resolve("../fora.txt", str(self.tmp / "fora.txt"), "/etc/hosts")[1]["results"]
        self.assertEqual(results, {})

    def test_link_para_fora(self):
        os.symlink(self.tmp / "fora.txt", self.project / "link.txt")
        self.assertEqual(self.resolve("link.txt")[1]["results"], {})

    def test_sensivel_volta_marcado(self):
        self.assertTrue(self.resolve(".env")[1]["results"][".env"]["sensitive"])
        self.assertFalse(self.resolve("sub/a.py")[1]["results"]["sub/a.py"]["sensitive"])

    def test_aba_na_pasta_dos_agentes_nao_vale(self):
        self.app.terminals.items[TAB] = SimpleNamespace(cwd=str(self.tmp / "claude"))
        self.assertEqual(self.resolve("settings.json", "projects")[1]["results"], {})

    def test_limite_de_50(self):
        self.assertEqual(self.resolve(*["a.py"] * 51)[0], 400)
        self.assertEqual(self.resolve(*["a.py"] * 50)[0], 200)

    def test_aba_inexistente(self):
        self.assertEqual(self.resolve("a.py", terminal="zzz")[0], 404)

    def test_corpo_invalido(self):
        self.assertEqual(self.request("POST", "/api/code/resolve", {"terminal": TAB, "candidates": "a"})[0], 400)
        self.assertEqual(self.request("POST", "/api/code/resolve", {"terminal": TAB, "candidates": [1]})[0], 400)

    def test_guarda_por_5_segundos(self):
        self.assertIn("sub/a.py", self.resolve("sub/a.py")[1]["results"])
        (self.project / "sub" / "a.py").unlink()
        self.assertIn("sub/a.py", self.resolve("sub/a.py")[1]["results"])
        self.app.code.resolved.clear()
        self.assertEqual(self.resolve("sub/a.py")[1]["results"], {})

    def test_sessao_pareada_vem_no_resultado(self):
        path = self.tmp / "claude" / "projects" / "-x" / f"{SID}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"type": "user", "timestamp": "2026-11-02T10:00:00Z", "cwd": str(self.project),
                                    "message": {"role": "user", "content": "x"}}) + "\n", encoding="utf-8")
        self.app.agents.refresh()
        self.app.agents.paired_with = lambda terminal: self.app.agents.index.session(SID) if terminal == TAB else None
        self.assertEqual(self.resolve("sub/a.py")[1]["results"]["sub/a.py"]["session"], SID)

    def test_abrir_no_editor_confere_de_novo(self):
        body = {"kind": "terminal_file", "terminal": TAB}
        self.assertEqual(self.request("POST", "/api/open", {**body, "target": "sub/a.py"})[0], 200)
        self.assertEqual(self.request("POST", "/api/open", {**body, "target": ".env"})[0], 403)
        self.assertEqual(self.request("POST", "/api/open", {**body, "target": "../fora.txt"})[0], 403)
        self.assertEqual(self.request("POST", "/api/open", {**body, "target": "sub"})[0], 403)
