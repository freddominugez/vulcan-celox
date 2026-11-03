"""Ações rápidas do site (banco, diagnóstico, painel do Lerd)."""

import os
import shlex
from unittest import mock

from tests.server_helpers import ServerTestCase


class SemBackendTest(ServerTestCase):
    def test_409(self):
        self.app.store.save("sites", {"loja": str(self.tmp)})
        status, data, _ = self.request("POST", "/api/sites/loja/actions/db")
        self.assertEqual(status, 409, data)


class AcoesTest(ServerTestCase):
    def env(self):
        env = super().env()
        self.lerd = self.tmp / "bin" / "lerd"
        self.lerd.parent.mkdir(parents=True, exist_ok=True)
        self.lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(self.lerd, 0o755)
        env.update({"VULCAN_LERD_BIN": str(self.lerd), "SHELL": "/bin/sh", "PATH": os.environ.get("PATH", "")})
        return env

    def setUp(self):
        super().setUp()
        self.pasta = self.tmp / "loja"
        self.pasta.mkdir()
        row = {"name": "loja", "domain": "loja.test", "path": str(self.pasta), "tls": True, "php_version": "8.4"}
        self.patch = mock.patch.object(self.app.backend, "api_get", side_effect=lambda p, **k: [row] if p == "/api/sites" else {})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.app.terminals.close_all()
        super().tearDown()

    def action(self, name):
        return self.request("POST", f"/api/sites/loja/actions/{name}")

    def test_banco_e_diagnostico_em_aba_do_site(self):
        for name, args in (("db", ["db:shell"]), ("doctor", ["site:doctor"])):
            with self.subTest(name=name):
                status, info, _ = self.action(name)
                self.assertEqual(status, 201, info)
                pty = self.app.terminals.get(info["id"])
                self.assertEqual(pty.cwd, str(self.pasta))
                self.assertIn(shlex.join([str(self.lerd), *args]), " ".join(pty.argv))

    def test_painel_do_lerd_no_site(self):
        status, data, _ = self.action("dashboard")
        self.assertEqual(status, 200, data)
        opened = list(self.fake.calls[-1].argv)
        self.assertTrue(opened[-1].endswith("/#sites/loja.test"), opened)

    def test_acao_desconhecida(self):
        self.assertEqual(self.action("rm")[0], 404)
        self.assertEqual(self.request("POST", "/api/sites/fantasma/actions/db")[0], 404)
