"""Home guide, steps checked against the app state and the choice to skip."""

import os
import shutil
from unittest import mock

from tests.helpers import FIXTURES
from tests.test_agents_api import AgentsServerCase


class GuideApiTest(AgentsServerCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("vulcan_celox.server.guide_api.is_windows", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_no_windows_nao_ha_passo_do_lerd(self):
        with mock.patch("vulcan_celox.server.guide_api.is_windows", return_value=True):
            self.assertEqual([s["id"] for s in self.get("/api/guide")["steps"]], ["projetos", "agentes", "terminal"])

    def steps(self, data):
        return {s["id"]: s["ok"] for s in data["steps"]}

    def test_passos_e_pular(self):
        data = self.get("/api/guide")
        ok = self.steps(data)
        self.assertEqual(list(ok), ["lerd", "projetos", "agentes", "terminal"])
        self.assertFalse(ok["lerd"])        # no Lerd in the tests
        self.assertFalse(ok["projetos"])
        self.assertTrue(ok["agentes"])      # Claude Code and Codex fixtures
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

    def test_lerd_e_opcional(self):
        """The guide ends without Lerd, and the step offers installing or dismissing."""
        lerd = self.get("/api/guide")["steps"][0]
        self.assertEqual((lerd["id"], lerd["optional"], lerd["state"], lerd["ok"]), ("lerd", True, "absent", False))
        self.assertIn("lerd.sh/install.sh", lerd["install_command"])
        shutil.copytree(FIXTURES / "node" / "painel", self.tmp / "painel")
        self.app.store.save("node_projects", {"painel": str(self.tmp / "painel")})
        self.app.store.save("guide", {"first_terminal": True})
        self.assertTrue(self.get("/api/guide")["done"])
        status, data, _ = self.request("PUT", "/api/guide", {"lerd_skipped": True})
        self.assertEqual(status, 200)
        self.assertTrue(data["steps"][0]["skipped"])
        self.assertEqual(self.request("PUT", "/api/guide", {"lerd_skipped": "sim"})[0], 400)
        self.assertEqual(self.request("PUT", "/api/guide", {})[0], 400)

    def test_instalar_abre_terminal_com_o_comando_oficial(self):
        """The real terminal is replaced here: a test must never run the installer."""
        session = mock.Mock()
        session.info.return_value = {"id": "abc"}
        with mock.patch.object(self.app, "spawn_terminal", return_value=session) as spawn, \
                mock.patch("vulcan_celox.server.guide_api.is_windows", return_value=False):
            status, info, _ = self.request("POST", "/api/guide/lerd/install", {})
        self.assertEqual((status, info), (201, {"id": "abc"}))
        self.assertEqual(spawn.call_args.kwargs["command"], "curl -fsSL https://lerd.sh/install.sh | bash")
        with mock.patch.object(self.app, "spawn_terminal") as spawn, \
                mock.patch("vulcan_celox.server.guide_api.is_windows", return_value=True):
            self.assertEqual(self.request("POST", "/api/guide/lerd/install", {})[0], 409)
        spawn.assert_not_called()

    def test_lerd_instalado_com_o_app_aberto_e_percebido(self):
        self.assertFalse(self.get("/api/state")["backend"]["available"])
        fake = self.tmp / "bin-lerd"
        fake.write_text("#!/bin/sh\necho lerd version 1.0\n")
        fake.chmod(0o755)
        self.app.env["VULCAN_LERD_BIN"] = str(fake)
        if os.name != "nt":
            self.assertEqual(self.get("/api/state")["backend"]["name"], "lerd")

    def test_caixa_nao_mostrar_mais_liga_e_desliga(self):
        """The Home checkbox records `skipped`; unchecking it makes the guide open again with the app."""
        for value, shown in ((True, False), (False, True), (True, False)):
            status, data, _ = self.request("PUT", "/api/guide", {"skipped": value})
            self.assertEqual(status, 200)
            self.assertEqual((data["skipped"], data["show_on_open"]), (value, shown))
            self.assertEqual(self.get("/api/guide")["skipped"], value)
