"""Estado do PR pelo gh: preferência desligada não executa nada, e toda falha cai na estimativa com rótulo."""

import json
import unittest
from pathlib import Path

from tests.test_agents_api import AgentsServerCase
from vulcan_celox.core.pr_status import FIELDS, PrStatus, checks_summary, gh_bin
from vulcan_celox.core.runner import FakeRunner, Result

GH = "/bin/gh-falso"
ARGV = [GH, "pr", "view", "--json", FIELDS]
ENV = {"VULCAN_GH_BIN": GH}
BOM = {"number": 12, "state": "OPEN", "isDraft": True, "url": "https://github.com/x/y/pull/12",
       "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}, {"state": "PENDING"}, {"conclusion": "SKIPPED"}]}


class PrStatusTest(unittest.TestCase):
    def status(self, result, clock=lambda: 0.0):
        self.runner = FakeRunner()
        self.runner.respond(ARGV, result)
        self.pr = PrStatus(self.runner, ENV, clock=clock)
        return self.pr.status("/projeto")

    def test_pr_real(self):
        data = self.status(Result(0, json.dumps(BOM)))
        self.assertEqual(data, {"source": "gh", "number": 12, "state": "OPEN", "draft": True, "url": BOM["url"],
                                "checks": {"total": 4, "passed": 2, "failed": 1, "pending": 1}})
        self.assertEqual(self.runner.calls[0].cwd, "/projeto")

    def test_gh_ausente(self):
        pr = PrStatus(FakeRunner(), {"VULCAN_GH_BIN": ""})
        self.assertEqual(pr.status("/x"), {"source": "heuristic", "reason": "no_gh"})
        self.assertEqual(pr.runner.calls, [])
        self.assertEqual(self.status(Result(127))["reason"], "no_gh")

    def test_sem_login(self):
        self.assertEqual(self.status(Result(4, "", "To get started with GitHub CLI, please run: gh auth login")),
                         {"source": "heuristic", "reason": "no_login"})

    def test_sem_pr(self):
        self.assertEqual(self.status(Result(1, "", 'no pull requests found for branch "x"')),
                         {"source": "gh", "reason": "no_pr", "number": None})

    def test_json_invalido(self):
        self.assertEqual(self.status(Result(0, "<html>"))["reason"], "invalid")
        self.assertEqual(self.status(Result(0, "[]"))["reason"], "invalid")

    def test_outra_falha_e_prazo(self):
        self.assertEqual(self.status(Result(1, "", "boom"))["reason"], "failed")
        self.assertEqual(self.status(Result(-1, timed_out=True))["reason"], "timeout")

    def test_url_estranha_nao_passa(self):
        self.assertEqual(self.status(Result(0, json.dumps({**BOM, "url": "javascript:alert(1)"})))["url"], "")

    def test_cache_de_60_segundos(self):
        now = [0.0]
        self.status(Result(0, json.dumps(BOM)), clock=lambda: now[0])
        now[0] = 59.0
        self.pr.status("/projeto")
        self.assertEqual(len(self.runner.calls), 1)
        now[0] = 61.0
        self.pr.status("/projeto")
        self.assertEqual(len(self.runner.calls), 2)

    def test_checagens_lixo(self):
        self.assertEqual(checks_summary("x")["total"], 0)
        self.assertEqual(checks_summary([1, {}])["total"], 1)

    def test_override_do_binario(self):
        self.assertEqual(gh_bin({"VULCAN_GH_BIN": "/a"}), "/a")
        self.assertIsNone(gh_bin({"VULCAN_GH_BIN": ""}))


class RotaTest(AgentsServerCase):
    SID = "11111111-2222-4333-8444-555555555555"

    def calls(self):
        return [c for c in self.fake.calls if "pr" in c.argv and "view" in c.argv]

    def test_desligada_por_padrao_nao_executa_nada(self):
        self.assertFalse(self.request("PATCH", "/api/preferences", {})[1]["pr_status"])
        data = self.get(f"/api/agents/pr?session={self.SID}")
        self.assertEqual(data, {"source": "heuristic", "reason": "off"})
        self.assertEqual(self.calls(), [])

    def test_ligada_consulta_so_pasta_conhecida(self):
        self.app.env["VULCAN_GH_BIN"] = GH
        self.assertTrue(self.request("PATCH", "/api/preferences", {"pr_status": True})[1]["pr_status"])
        self.assertEqual(self.get("/api/agents/pr?path=/etc")["reason"], "unknown_folder")
        self.assertEqual(self.calls(), [])
        self.get(f"/api/agents/pr?session={self.SID}")
        self.assertEqual(len(self.calls()), 1)

    def test_valor_invalido(self):
        self.assertEqual(self.request("PATCH", "/api/preferences", {"pr_status": "sim"})[0], 400)

    def test_sessao_desconhecida(self):
        self.request("PATCH", "/api/preferences", {"pr_status": True})
        self.assertEqual(self.request("GET", "/api/agents/pr?session=zzz")[0], 404)
