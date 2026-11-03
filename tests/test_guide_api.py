"""Guia do Início, passos conferidos pelo estado do app e escolha de pular."""

import shutil

from tests.helpers import FIXTURES
from tests.test_agents_api import AgentsServerCase


class GuideApiTest(AgentsServerCase):
    def steps(self, data):
        return {s["id"]: s["ok"] for s in data["steps"]}

    def test_passos_e_pular(self):
        data = self.get("/api/guide")
        ok = self.steps(data)
        self.assertEqual(list(ok), ["lerd", "projetos", "agentes", "terminal"])
        self.assertFalse(ok["lerd"])        # sem Lerd nos testes
        self.assertFalse(ok["projetos"])
        self.assertTrue(ok["agentes"])      # fixtures do Claude Code e do Codex
        self.assertFalse(ok["terminal"])
        self.assertTrue(data["show_on_open"])
        shutil.copytree(FIXTURES / "node" / "painel", self.tmp / "painel")
        self.app.store.save("node_projects", {"painel": str(self.tmp / "painel")})
        self.assertTrue(self.steps(self.get("/api/guide"))["projetos"])
        status, data, _ = self.request("PUT", "/api/guide", {"skipped": True})
        self.assertEqual(status, 200)
        self.assertEqual((data["skipped"], data["show_on_open"]), (True, False))
        status, _, _ = self.request("PUT", "/api/guide", {"skipped": "sim"})
        self.assertEqual(status, 400)
        self.assertTrue(self.get("/api/guide")["skipped"])

    def test_caixa_nao_mostrar_mais_liga_e_desliga(self):
        """A caixa do Início grava `skipped`; desmarcar volta a abrir o guia com o app."""
        for value, shown in ((True, False), (False, True), (True, False)):
            status, data, _ = self.request("PUT", "/api/guide", {"skipped": value})
            self.assertEqual(status, 200)
            self.assertEqual((data["skipped"], data["show_on_open"]), (value, shown))
            self.assertEqual(self.get("/api/guide")["skipped"], value)
