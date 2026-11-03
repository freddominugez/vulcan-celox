"""O prompt vai como colagem, sem Enter, só para a aba pareada à sessão."""
import unittest

from tests import test_agents_api
from tests.test_node_api import FakePty, FakeTerminals
from vulcan_terminal.core import prompts

CLAUDE_SID = "11111111-2222-4333-8444-555555555555"
TAB = "0000abcd"


class PromptsSendTest(test_agents_api.AgentsServerCase):
    def setUp(self):
        super().setUp()
        self.real_terminals = self.app.terminals
        self.app.terminals = FakeTerminals()
        self.paired = FakePty(TAB, "loja")
        self.paired.foreground = lambda: [("claude", "claude --resume x")]  # o agente em primeiro plano na aba
        self.other = FakePty("0000ffff", "outra")
        self.app.terminals.items = {TAB: self.paired, "0000ffff": self.other}
        self.get("/api/prompts")  # cria os exemplos
        self.real_decorate = self.app.agents.decorate
        self.pair_with = TAB

        def decorate(sessions):
            out = self.real_decorate(sessions)
            for s in out:
                s.pairing_id = self.pair_with if s.id == CLAUDE_SID else None
            return out

        self.app.agents.decorate = decorate

    def tearDown(self):
        self.app.agents.decorate = self.real_decorate
        self.app.terminals = self.real_terminals
        super().tearDown()

    def send(self, body):
        status, data, _ = self.request("POST", "/api/prompts/send", body=body)
        return status, data

    def test_cola_so_na_aba_pareada_sem_enter(self):
        status, data = self.send({"prompt": "seguranca", "session": CLAUDE_SID})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["terminal"], TAB)
        self.assertEqual(self.other.written, [])
        (sent,) = self.paired.written
        self.assertTrue(sent.startswith(prompts.PASTE_START) and sent.endswith(prompts.PASTE_END))
        inner = sent[len(prompts.PASTE_START):-len(prompts.PASTE_END)]
        self.assertIn(f"sessão {CLAUDE_SID}".encode(), inner)
        self.assertNotIn(b"\r", sent)
        self.assertNotIn(b"\n", sent)  # o exemplo é uma linha: nada de Enter nem fora nem dentro da colagem

    def test_valores_dos_campos_e_controle_removido(self):
        status, _ = self.send({"prompt": "seguranca", "session": CLAUDE_SID,
                               "values": {"branch": "feat/x\x1b[201~\r rm -rf"}})
        self.assertEqual(status, 200)
        sent = self.paired.written[0]
        self.assertEqual(sent.count(b"\x1b"), 2)  # só o início e o fim da colagem
        self.assertIn(b"branch feat/x[201~ rm -rf", sent)
        self.assertNotIn(b"\r", sent)

    def test_sem_aba_pareada_409_com_a_sugestao(self):
        self.pair_with = None
        status, data = self.send({"prompt": "seguranca", "session": CLAUDE_SID})
        self.assertEqual(status, 409)
        self.assertEqual((data["needs_terminal"], data["session"]), (True, CLAUDE_SID))
        self.paired.alive, self.pair_with = False, TAB
        status, data = self.send({"prompt": "seguranca", "session": CLAUDE_SID})
        self.assertEqual(status, 409)
        self.assertEqual(self.paired.written, [])

    def test_agente_fechou_e_a_aba_voltou_ao_shell_409(self):
        """Depois que o agente sai, a aba pareada vira shell comum; o prompt não pode cair no shell."""
        self.paired.foreground = lambda: [("-zsh", "-zsh")]
        status, data = self.send({"prompt": "seguranca", "session": CLAUDE_SID})
        self.assertEqual(status, 409, data)
        self.assertEqual((data["needs_terminal"], data["session"]), (True, CLAUDE_SID))
        self.assertEqual(self.paired.written, [])
        self.paired.foreground = lambda: [("-zsh", "-zsh"), ("node", "node /opt/homebrew/bin/codex")]
        status, _ = self.send({"prompt": "seguranca", "session": CLAUDE_SID})
        self.assertEqual(status, 409)  # outro agente na aba também não serve
        self.paired.foreground = lambda: [("-zsh", "-zsh"), ("2.1.316", "/Users/dev/.local/share/claude/versions/2.1.316")]
        status, _ = self.send({"prompt": "seguranca", "session": CLAUDE_SID})
        self.assertEqual(status, 200)  # o binário nativo do Claude Code também conta

    def test_outra_sessao_mais_nova_na_mesma_aba_409(self):
        """A sessão escolhida acabou e outra do mesmo agente começou na aba: o prompt iria para a nova."""
        real = self.app.agents.paired_with
        self.app.agents.paired_with = lambda tab: type("S", (), {"id": "outra-sessao"})() if tab == TAB else None
        self.addCleanup(setattr, self.app.agents, "paired_with", real)
        status, data = self.send({"prompt": "seguranca", "session": CLAUDE_SID})
        self.assertEqual(status, 409, data)
        self.assertEqual(self.paired.written, [])

    def test_aba_parada_503(self):
        """A aba não leu a colagem no prazo: 503 em vez de prender a thread HTTP."""
        self.paired.write = lambda data: False
        status, data = self.send({"prompt": "seguranca", "session": CLAUDE_SID})
        self.assertEqual(status, 503, data)
        self.assertEqual(data["terminal"], TAB)

    def test_variavel_vazia_e_validacao(self):
        status, data = self.send({"prompt": "seguranca", "session": CLAUDE_SID, "values": {}})
        self.assertEqual(status, 200)
        path = self.app.prompts.global_dir / "ticket.md"  # na raiz: categoria Outros (sem depender de maiúsculas na pasta)
        path.write_text("---\nid: ticket\ntitle: Ticket\n---\nResolva o ticket {{ticket}}.\n", encoding="utf-8")
        status, data = self.send({"prompt": "ticket", "session": CLAUDE_SID})
        self.assertEqual(status, 400)
        self.assertEqual(data["missing"], ["ticket"])
        status, _ = self.send({"prompt": "ticket", "session": CLAUDE_SID, "values": {"ticket": "ABC-9"}})
        self.assertEqual(status, 200)
        self.assertIn(b"Resolva o ticket ABC-9.", self.paired.written[-1])
        for bad in ({}, {"prompt": "nao-existe", "session": CLAUDE_SID}, {"prompt": "seguranca", "session": "x"},
                    {"prompt": "seguranca", "values": {"branch": 1}}, {"prompt": "seguranca", "values": {"b": "x" * 2001}}):
            status, _ = self.send(bad)
            self.assertIn(status, (400, 404), bad)


class PasteBytesTest(unittest.TestCase):
    def test_valor_da_sessao_nao_fecha_a_colagem_nem_aperta_enter(self):
        data, missing = prompts.paste_bytes("x {{cwd}} y {{branch}}",
                                            {"cwd": "/tmp/a\x1b[201~\rrm x\r", "branch": "b\nc"}, {})
        self.assertEqual(missing, [])
        inner = data[len(prompts.PASTE_START):-len(prompts.PASTE_END)]
        self.assertNotIn(b"\x1b", inner)
        self.assertNotIn(b"\r", inner)
        self.assertNotIn(b"\n", inner)
        self.assertEqual(inner, b"x /tmp/a[201~ rm x y b c")
