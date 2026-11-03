"""Sessão atual pela API, lembrada entre aberturas do app."""

from tests import test_agents_api
from vulcan_terminal.server.app import VulcanApp

CLAUDE_SID = "11111111-2222-4333-8444-555555555555"
CODEX_SID = "019a0000-1111-7222-8333-444444444444"


class CurrentSessionTest(test_agents_api.AgentsServerCase):
    def test_automatica_por_padrao(self):
        data = self.get("/api/agents/current")
        self.assertTrue(data["automatic"])
        self.assertEqual(data["session"]["id"], CLAUDE_SID)  # a mais recente das fixtures
        self.assertEqual(data["context"]["sessionId"], CLAUDE_SID)
        self.assertEqual(data["context"]["projectName"], "projeto")

    def test_escolher_lembrar_e_voltar_ao_automatico(self):
        status, data, _ = self.request("PUT", "/api/agents/current", body={"session_id": CODEX_SID})
        self.assertEqual((status, data["session"]["id"], data["automatic"]), (200, CODEX_SID, False))
        self.assertEqual(data["context"]["agent"], "Codex")
        other = VulcanApp(env=self.env(), runner=self.fake, token=self.token)  # outra abertura do app, mesma pasta de dados
        try:
            other.agents.refresh()
            self.assertEqual(other.agents.current()["session"]["id"], CODEX_SID)
        finally:
            other.agents.stop()
        status, data, _ = self.request("PUT", "/api/agents/current", body={"session_id": None})
        self.assertEqual((status, data["automatic"], data["session"]["id"]), (200, True, CLAUDE_SID))

    def test_sessao_desconhecida(self):
        status, _, _ = self.request("PUT", "/api/agents/current", body={"session_id": "nao-existe"})
        self.assertEqual(status, 404)
        status, _, _ = self.request("PUT", "/api/agents/current", body={"session_id": 5})
        self.assertEqual(status, 400)
