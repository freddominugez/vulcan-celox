"""vt-02 C7: remover site em três níveis (lista, backend, pasta para a Lixeira), nunca apagando em definitivo."""

import os
from unittest import mock

from tests.server_helpers import ServerTestCase


class ManualTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.pasta = self.tmp / "rascunho"
        self.pasta.mkdir()
        (self.pasta / "index.php").write_text("<?php")
        self.app.store.save("sites", {"rascunho": str(self.pasta)})

    def test_remover_da_lista_e_mandar_para_a_lixeira(self):
        status, data, _ = self.request("POST", "/api/sites/rascunho/remove", body={"level": "list"})
        self.assertEqual(status, 200, data)
        self.assertEqual(self.app.store.load("sites", {}), {})
        self.assertTrue(self.pasta.is_dir())  # a pasta continua
        # nome digitado errado não faz nada
        self.assertEqual(self.request("POST", "/api/sites/trash", body={"name": "rascunho", "confirm": "Rascunho"})[0], 400)
        self.assertTrue(self.pasta.is_dir())
        status, data, _ = self.request("POST", "/api/sites/trash", body={"name": "rascunho", "confirm": "rascunho"})
        self.assertEqual(status, 200, data)
        self.assertFalse(self.pasta.exists())
        moved = data["moved_to"]
        self.assertTrue(os.path.isdir(moved) or moved == str(self.pasta))  # Lixeira do sistema ou lixeira/ do app
        system_trash = any("osascript" in c.argv[0] or "gio" in c.argv[0] for c in self.fake.calls)
        self.assertTrue(system_trash or "/lixeira/" in moved, moved)  # sem Finder nem gio: lixeira/ do app

    def test_lixeira_so_para_site_removido_pelo_app(self):
        # ainda na lista: recusa
        self.assertEqual(self.request("POST", "/api/sites/trash", body={"name": "rascunho", "confirm": "rascunho"})[0], 409)
        self.assertEqual(self.request("POST", "/api/sites/trash", body={"name": "outro", "confirm": "outro"})[0], 409)
        self.assertTrue(self.pasta.is_dir())

    def test_nivel_invalido(self):
        self.assertEqual(self.request("POST", "/api/sites/rascunho/remove", body={"level": "tudo"})[0], 400)
        self.assertEqual(self.request("POST", "/api/sites/rascunho/remove", body={"level": "backend"})[0], 409)


class LerdTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        env["VULCAN_LERD_BIN"] = str(lerd)
        return env

    def setUp(self):
        super().setUp()
        self.pasta = self.tmp / "loja"
        self.pasta.mkdir()
        self.rows = [{"name": "loja", "domain": "loja.test", "path": str(self.pasta)}]
        self.patch = mock.patch.object(self.app.backend, "api_get",
                                       side_effect=lambda p, **k: list(self.rows) if p == "/api/sites" else {})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        super().tearDown()

    def test_desregistrar_e_depois_lixeira(self):
        self.assertEqual(self.request("POST", "/api/sites/loja/remove", body={"level": "list"})[0], 409)
        status, data, _ = self.request("POST", "/api/sites/loja/remove", body={"level": "backend"})
        self.assertEqual(status, 200, data)
        self.assertEqual(list(self.fake.calls[-1].argv)[1:], ["unlink", "loja"])
        # enquanto o backend ainda lista o site, a pasta não vai para a Lixeira
        self.assertEqual(self.request("POST", "/api/sites/trash", body={"name": "loja", "confirm": "loja"})[0], 409)
        self.rows.clear()  # o Lerd já não lista o site
        status, data, _ = self.request("POST", "/api/sites/trash", body={"name": "loja", "confirm": "loja"})
        self.assertEqual(status, 200, data)
        self.assertFalse(self.pasta.exists())

    def test_falha_do_backend_nao_libera_a_lixeira(self):
        from vulcan_terminal.core.runner import Result
        self.fake.default = Result(1, "", "site em uso")
        data = self.request("POST", "/api/sites/loja/remove", body={"level": "backend"})[1]
        self.assertFalse(data["ok"])
        self.rows.clear()
        self.assertEqual(self.request("POST", "/api/sites/trash", body={"name": "loja", "confirm": "loja"})[0], 409)
        self.assertTrue(self.pasta.is_dir())
