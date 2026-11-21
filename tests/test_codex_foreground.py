"""Codex in the foreground of a tab: the four states of procinfo.codex_foreground and GET /api/agents/paired?foreground=1."""

import unittest
from unittest import mock

from tests import test_agents_api
from vulcan_celox.core import procinfo

CODEX_SID = "019a0000-1111-7222-8333-444444444444"


class FakeTerminal:
    def __init__(self, alive=True, processes=None):
        self.alive = alive
        self.processes = processes

    def foreground(self):
        return self.processes


class CodexForegroundTest(unittest.TestCase):
    def test_aba_inexistente_ou_encerrada_fica_closed(self):
        self.assertEqual(procinfo.codex_foreground(None), "closed")
        self.assertEqual(procinfo.codex_foreground(FakeTerminal(alive=False, processes=[("codex", "codex")])), "closed")

    def test_sem_como_saber_fica_unknown(self):
        self.assertEqual(procinfo.codex_foreground(FakeTerminal(processes=None)), "unknown")
        self.assertEqual(procinfo.codex_foreground(FakeTerminal(processes=[])), "unknown")

    def test_codex_pelo_executavel_ou_por_componente_do_caminho(self):
        for procs in ([("codex", "codex")], [("node", "node /opt/homebrew/bin/codex resume")],
                      [("zsh", "-zsh"), ("codex", "/Users/dev/.local/bin/codex --model x")]):
            with self.subTest(procs=procs):
                self.assertEqual(procinfo.codex_foreground(FakeTerminal(processes=procs)), "codex")

    def test_outro_programa_fica_other(self):
        for procs in ([("zsh", "-zsh")], [("vim", "vim codex.txt")], [("claude", "claude")], [("node", "node /srv/codexito.js")]):
            with self.subTest(procs=procs):
                self.assertEqual(procinfo.codex_foreground(FakeTerminal(processes=procs)), "other")


class PairedForegroundApiTest(test_agents_api.AgentsServerCase):
    def test_foreground_1_acrescenta_foreground_e_chosen(self):
        tabs = {"aba00000000c": FakeTerminal(processes=[("codex", "codex")]),
                "aba00000000s": FakeTerminal(processes=[("zsh", "-zsh")])}
        status, _, _ = self.request("PUT", "/api/agents/current", body={"session_id": CODEX_SID})
        self.assertEqual(status, 200)
        with mock.patch.object(self.app.terminals, "get", side_effect=tabs.get):
            plain = self.get("/api/agents/paired?terminal=aba00000000c")
            self.assertNotIn("foreground", plain)
            self.assertNotIn("chosen", plain)
            cases = {"aba00000000c": "codex", "aba00000000s": "other", "aba0000000zz": "closed"}
            for terminal, expected in cases.items():
                with self.subTest(terminal=terminal):
                    data = self.get(f"/api/agents/paired?terminal={terminal}&foreground=1")
                    self.assertEqual(data["foreground"], expected)
                    self.assertEqual(data["chosen"], CODEX_SID)
        status, _, _ = self.request("PUT", "/api/agents/current", body={"session_id": None})
        self.assertEqual(status, 200)
        self.assertIsNone(self.get("/api/agents/paired?terminal=aba0000000zz&foreground=1")["chosen"])


if __name__ == "__main__":
    unittest.main()
