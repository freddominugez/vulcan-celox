"""Versões de PHP do Lerd (lista, padrão, instalar, atualizar)."""

import os
from unittest import mock

from tests.helpers import FIXTURES
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.environment import SUPPORTED_PHP, parse_php_list
from vulcan_celox.core.runner import Result


class ParserTest(ServerTestCase):
    def test_saida_real(self):
        # tests/fixtures/lerd-php-list.txt: saída de `lerd php:list` do Lerd 1.37.1 nesta máquina
        self.assertEqual(parse_php_list((FIXTURES / "lerd-php-list.txt").read_text(encoding="utf-8")),
                         [{"version": "8.5", "default": True}])

    def test_varias_versoes(self):
        text = "Installed PHP versions:\n  8.3\n* 8.4\n  8.5 (prerelease)\n\n"
        self.assertEqual(parse_php_list(text), [{"version": "8.3", "default": False}, {"version": "8.4", "default": True},
                                                {"version": "8.5", "default": False}])
        self.assertEqual(parse_php_list(""), [])


class ApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        env.update({"VULCAN_LERD_BIN": str(lerd), "SHELL": "/bin/sh", "PATH": os.environ.get("PATH", "")})
        self.lerd = lerd
        return env

    def setUp(self):
        super().setUp()
        self.fake.default = Result(0, "Installed PHP versions:\n  8.4\n* 8.5\n")
        self.patch = mock.patch.object(self.app.backend, "api_get", return_value={})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.app.terminals.close_all()
        super().tearDown()

    def test_lista_com_instalaveis(self):
        data = self.request("GET", "/api/environment/php")[1]
        self.assertEqual([v["version"] for v in data["installed"]], ["8.4", "8.5"])
        self.assertEqual(data["installable"], [v for v in SUPPORTED_PHP if v not in ("8.4", "8.5")])

    def test_padrao_e_abas(self):
        status, data, _ = self.request("POST", "/api/environment/php/8.4/use")
        self.assertEqual(status, 200, data)
        self.assertEqual(list(self.fake.calls[-1].argv)[1:], ["use", "8.4"])
        for op, args in (("update", ["php:update", "8.5"]), ("install", ["fetch", "8.2"])):
            with self.subTest(op=op):
                version = "8.2" if op == "install" else "8.5"
                status, info, _ = self.request("POST", f"/api/environment/php/{version}/{op}")
                self.assertEqual(status, 201, info)
                self.assertIn(" ".join([str(self.lerd), *args]), " ".join(self.app.terminals.get(info["id"]).argv))

    def test_invalidos(self):
        self.assertEqual(self.request("POST", "/api/environment/php/9.9/use")[0], 400)
        self.assertEqual(self.request("POST", "/api/environment/php/8.4/remove")[0], 404)
        self.assertEqual(self.request("POST", "/api/environment/php/7.0/install")[0], 400)
