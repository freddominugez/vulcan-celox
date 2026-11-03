"""Novo terminal com tema da rotação, agente digitado ao abrir e preferência de não perguntar a pasta."""

from tests.server_helpers import ServerTestCase
from tests.test_pty import wait_for


class NewTerminalApiTest(ServerTestCase):
    def tearDown(self):
        self.app.terminals.close_all()
        super().tearDown()

    def create(self, **body):
        return self.request("POST", "/api/terminals", body={"cwd": str(self.tmp), **body})[:2]

    def test_tres_cliques_seguem_a_rotacao(self):
        themes = [self.create(theme="auto")[1]["theme"] for _ in range(3)]
        self.assertEqual(themes, ["homebrew", "classico", "oceano"])

    def test_agente_digitado_e_registrado_para_o_pareamento(self):
        status, info = self.create(theme="auto", agent="claude")
        self.assertEqual(status, 201)
        pty = self.app.terminals.get(info["id"])
        self.assertTrue(wait_for(lambda: b"claude" in pty.history()), pty.history())
        record = self.app.hub.sessions.get(info["id"])
        self.assertEqual([c["cmd"] for c in record.commands], ["claude"])
        status, codex = self.create(agent="codex")
        self.assertEqual([c["cmd"] for c in self.app.hub.sessions.get(codex["id"]).commands], ["codex"])

    def test_agente_invalido(self):
        for agent in ("rm -rf /", "bash", 5):
            with self.subTest(agent=agent):
                self.assertEqual(self.create(agent=agent)[0], 400)

    def test_preferencias_do_novo_terminal(self):
        status, data, _ = self.request("GET", "/api/themes")
        self.assertEqual(data["new_terminal"], {"skip_folder": False, "agent": "shell"})
        status, data, _ = self.request("PATCH", "/api/preferences", body={"new_terminal": {"skip_folder": True, "agent": "codex"}})
        self.assertEqual((status, data["new_terminal"]), (200, {"skip_folder": True, "agent": "codex"}))
        self.assertEqual(self.request("GET", "/api/themes")[1]["new_terminal"]["agent"], "codex")
        status, _, _ = self.request("PATCH", "/api/preferences", body={"new_terminal": {"agent": "outro"}})
        self.assertEqual(status, 400)
