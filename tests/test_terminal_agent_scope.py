"""An agent selection belongs to one tab; legacy preferences cannot launch it elsewhere."""

from unittest.mock import patch

from tests.server_helpers import ServerTestCase


class TerminalAgentScopeTest(ServerTestCase):
    def test_preferencia_antiga_nao_vira_padrao(self):
        self.app.store.save("new_terminal", {"skip_folder": True, "agent": "codex"})
        self.assertEqual(self.request("GET", "/api/themes")[1]["new_terminal"],
                         {"skip_folder": True, "agent": "shell"})

    def test_cliente_antigo_nao_persiste_agente(self):
        data = self.request("PATCH", "/api/preferences", {"new_terminal": {"skip_folder": True, "agent": "codex"}})[1]
        self.assertEqual(data["new_terminal"], {"skip_folder": True, "agent": "shell"})
        self.assertEqual(self.app.store.load("new_terminal", {})["agent"], "shell")

    def test_agente_explicito_so_vai_para_a_aba_pedida(self):
        with patch.object(self.app, "spawn_terminal") as spawn:
            spawn.return_value.info.return_value = {"id": "abc"}
            for agent, expected in (("codex", "codex"), (None, None), ("claude", "claude"), ("shell", None)):
                body = {"cwd": str(self.tmp)}
                if agent is not None:
                    body["agent"] = agent
                self.assertEqual(self.request("POST", "/api/terminals", body)[0], 201)
                self.assertEqual(spawn.call_args.kwargs["typed"], expected)
        self.assertEqual(self.app.new_terminal_prefs()["agent"], "shell")
