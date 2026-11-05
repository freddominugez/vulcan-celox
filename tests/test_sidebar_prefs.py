"""What the sidebar shows: the server keeps the choice and Settings can never be hidden."""

import re

from tests.server_helpers import ServerTestCase
from tests.test_web_assets import WEB
from vulcan_celox.server.app import SIDEBAR_ITEMS


class SidebarPrefsTest(ServerTestCase):
    def prefs(self, body):
        return self.request("PATCH", "/api/preferences", body=body)

    def test_comeca_mostrando_tudo(self):
        self.assertEqual(self.prefs({})[1]["sidebar_hidden"], [])

    def test_guarda_a_escolha_sem_repetir(self):
        status, data, _ = self.prefs({"sidebar_hidden": ["tags", "tags", "section-node"]})
        self.assertEqual(status, 200)
        self.assertEqual(data["sidebar_hidden"], ["section-node", "tags"])
        self.assertEqual(self.prefs({})[1]["sidebar_hidden"], ["section-node", "tags"])
        self.assertEqual(self.prefs({"sidebar_hidden": []})[1]["sidebar_hidden"], [])

    def test_recusa_item_desconhecido_e_configuracoes(self):
        self.prefs({"sidebar_hidden": ["tags"]})
        for bad in (["config"], ["nao-existe"], "tags", [1]):
            self.assertEqual(self.prefs({"sidebar_hidden": bad})[0], 400, bad)
        self.assertEqual(self.prefs({})[1]["sidebar_hidden"], ["tags"])

    def test_barra_recolhida(self):
        self.assertIsNone(self.prefs({})[1]["sidebar_collapsed"], "sem escolha, a interface decide pela largura")
        self.assertIs(self.prefs({"sidebar_collapsed": True})[1]["sidebar_collapsed"], True)
        self.assertIs(self.prefs({})[1]["sidebar_collapsed"], True)
        self.prefs({"sidebar_hidden": ["tags"]})
        self.assertIs(self.prefs({})[1]["sidebar_collapsed"], True, "esconder item não muda o recolhido")
        for bad in ("sim", 1, None):
            self.assertEqual(self.prefs({"sidebar_collapsed": bad})[0], 400, bad)
        self.assertIs(self.prefs({"sidebar_collapsed": False})[1]["sidebar_collapsed"], False)
        self.assertEqual(self.prefs({})[1]["sidebar_hidden"], ["tags"])

    def test_responde_versao_e_pasta_de_dados(self):
        data = self.prefs({})[1]
        self.assertTrue(data["version"])
        self.assertEqual(data["data_dir"], str(self.app.data_dir))

    def test_catalogo_da_interface_igual_ao_do_servidor(self):
        src = (WEB / "js" / "app-state.mjs").read_text(encoding="utf-8")
        groups = src[src.index("export const NAV_GROUPS"):src.index("export const navById")]
        items = set(re.findall(r'"([a-z-]+)"', " ".join(re.findall(r"items: \[([^\]]*)\]", groups))))
        sections = set(re.findall(r'id: "(section-[a-z]+)"', src))
        self.assertEqual(items - {"config"} | sections, set(SIDEBAR_ITEMS))
        self.assertIn('id: "config"', src)
