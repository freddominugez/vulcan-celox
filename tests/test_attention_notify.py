"""System notification: preference, safe command and text without conversation content."""

import unittest
from pathlib import Path
from unittest import mock

from tests.server_helpers import ServerTestCase

ROOT = Path(__file__).resolve().parent.parent
MODULE = (ROOT / "vulcan_celox" / "web" / "js" / "attention-notify.mjs").read_text(encoding="utf-8")


class PreferenciaTest(ServerTestCase):
    def test_ligado_por_padrao_e_lembrado(self):
        self.assertTrue(self.request("PATCH", "/api/preferences", {})[1]["attention_notify"])
        self.assertFalse(self.request("PATCH", "/api/preferences", {"attention_notify": False})[1]["attention_notify"])
        self.assertFalse(self.request("PATCH", "/api/preferences", {})[1]["attention_notify"])

    def test_valor_invalido(self):
        self.assertEqual(self.request("PATCH", "/api/preferences", {"attention_notify": "sim"})[0], 400)


class RotaTest(ServerTestCase):
    def post_notice(self, body, platform="linux", which="/usr/bin/notify-send"):
        with mock.patch("vulcan_celox.server.agents_api.sys.platform", platform), \
                mock.patch("vulcan_celox.server.agents_api.shutil.which", return_value=which):
            return self.request("POST", "/api/agents/notice", body)

    def notify_calls(self):
        return [list(c.argv) for c in self.fake.calls if c.argv and c.argv[0] == "notify-send"]

    def test_linux_usa_notify_send_com_separador(self):
        status, data, _ = self.post_notice({"title": "--urgency=critical", "text": "loja: sua vez"})
        self.assertEqual((status, data["sent"]), (200, True))
        self.assertEqual(self.notify_calls()[-1], ["notify-send", "--", "--urgency=critical", "loja: sua vez"])

    def test_sem_notify_send_nao_falha(self):
        self.assertFalse(self.post_notice({"title": "a", "text": "b"}, which=None)[1]["sent"])

    def test_macos_fica_com_a_casca(self):
        self.assertFalse(self.post_notice({"title": "a", "text": "b"}, platform="darwin")[1]["sent"])
        self.assertEqual(self.notify_calls(), [])

    def test_texto_limitado_e_sem_quebra(self):
        self.post_notice({"title": "a\nb", "text": "x" * 500})
        call = self.notify_calls()[-1]
        self.assertEqual((call[2], len(call[3])), ("a b", 160))

    def test_exige_token(self):
        self.assertEqual(self.request("POST", "/api/agents/notice", {"title": "a"}, token=False)[0], 401)


class TextoTest(unittest.TestCase):
    def test_aviso_nao_usa_o_texto_do_terminal(self):
        corpo = MODULE[MODULE.index("export function noticeText"):MODULE.index("export function noticesEnabled")]
        self.assertNotIn("event.text", corpo)
        self.assertNotIn("last_agent_message", MODULE)

    def test_so_avisa_com_a_janela_sem_foco(self):
        self.assertIn("if (!enabled || document.hasFocus()) return;", MODULE)


if __name__ == "__main__":
    unittest.main()
