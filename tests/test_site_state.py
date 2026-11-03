"""HTTPS, PHP e Node do site a partir do registro do Lerd, e as ações que os mudam."""

import json
import os
import shlex
from unittest import mock

from tests.helpers import FIXTURES
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.backends.lerd import site_from_row


class LeituraTest(ServerTestCase):
    def test_campos_do_registro(self):
        rows = json.loads((FIXTURES / "lerd-api-sites.json").read_text(encoding="utf-8"))
        sites = [site_from_row(r) for r in rows]
        for row, site in zip(rows, sites):
            with self.subTest(site=row["name"]):
                self.assertEqual(site.secured, bool(row["tls"]))
                self.assertEqual(site.php, str(row["php_version"] or ""))
                self.assertEqual(site.node, str(row["node_version"] or ""))
                self.assertEqual(site.url.split("://")[0], "https" if row["tls"] else "http")


class AcoesTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        env["VULCAN_LERD_BIN"] = str(lerd)
        env["SHELL"] = "/bin/sh"
        env["PATH"] = os.environ.get("PATH", "")
        return env

    def setUp(self):
        super().setUp()
        self.pasta = self.tmp / "loja"
        self.pasta.mkdir()
        row = {"name": "loja", "domain": "loja.test", "path": str(self.pasta), "tls": False, "php_version": "8.4",
               "node_version": "22"}
        status = {"php_fpms": [{"version": "8.4", "running": True}, {"version": "8.5", "running": True}],
                  "php_default": "8.5", "node_default": "22"}
        backend = self.app.backend
        self.patch = mock.patch.object(backend, "api_get",
                                       side_effect=lambda p, **k: [row] if p == "/api/sites" else status)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.app.terminals.close_all()
        super().tearDown()

    def patch_site(self, body):
        return self.request("PATCH", "/api/sites/loja", body=body)

    def test_https_liga_e_desliga(self):
        status, data, _ = self.patch_site({"secured": True})
        self.assertEqual(status, 200, data)
        self.assertEqual(list(self.fake.calls[-1].argv)[1:], ["secure", "loja"])
        self.patch_site({"secured": False})
        self.assertEqual(list(self.fake.calls[-1].argv)[1:], ["unsecure", "loja"])

    def test_php_abre_aba_com_o_isolate_na_pasta(self):
        status, info, _ = self.patch_site({"php": "8.5"})
        self.assertEqual(status, 201, info)
        pty = self.app.terminals.get(info["id"])
        self.assertEqual(pty.cwd, str(self.pasta))
        self.assertEqual(pty.site, "loja")
        self.assertIn(shlex.join([str(self.tmp / "bin" / "lerd"), "isolate", "8.5"]), " ".join(pty.argv))

    def test_node_abre_aba_com_o_isolate_node(self):
        status, info, _ = self.patch_site({"node": "20"})
        self.assertEqual(status, 201, info)
        self.assertIn("isolate:node 20", " ".join(self.app.terminals.get(info["id"]).argv))

    def test_valores_invalidos(self):
        for body in ({"php": "7.1"}, {"php": "-8"}, {"node": "abc"}, {"node": "--x"}, {}, {"secured": "sim"}):
            with self.subTest(body=body):
                self.assertEqual(self.patch_site(body)[0], 400)
        self.assertEqual(self.request("PATCH", "/api/sites/fantasma", body={"secured": True})[0], 404)
        self.assertEqual(self.app.terminals.list(), [])

    def test_versoes_para_o_seletor(self):
        data = self.request("GET", "/api/sites/loja/versions")[1]
        self.assertEqual([v["version"] for v in data["php"]], ["8.4", "8.5"])
        self.assertEqual(data["current"], {"php": "8.4", "node": "22", "secured": False})
        self.assertIn(".php-version", data["writes"]["php"])
        self.assertIn("APP_URL", data["writes"]["secure"])
