"""Adding a site (link or park a folder) through the app API."""

import os

from tests.server_helpers import ServerTestCase
from vulcan_celox.server.sites_api import suggest_domain, validate_domain


class DominioTest(ServerTestCase):
    def test_validacao(self):
        self.assertEqual(validate_domain("loja-2"), (True, "loja-2"))
        for bad, suggestion in (("Loja", "loja"), ("loja.test", "loja"), ("www.loja", "loja"), ("", ""),
                                ("minha loja", "minha-loja"), ("-loja", "loja")):
            with self.subTest(bad=bad):
                ok, suggested = validate_domain(bad)
                self.assertFalse(ok)
                self.assertEqual(suggested, suggestion)

    def test_sugestao_pelo_nome_da_pasta(self):
        self.assertEqual(suggest_domain("/Users/dev/Code/www.Minha_Loja"), "minha-loja")
        self.assertEqual(suggest_domain("/Users/dev/Code/blog.test"), "blog")


class AdicionarSemBackendTest(ServerTestCase):
    def test_sem_backend_409(self):
        pasta = self.tmp / "loja"
        pasta.mkdir()
        status, data, _ = self.request("POST", "/api/sites", body={"kind": "link", "path": str(pasta), "domain": "loja"})
        self.assertEqual(status, 409)
        self.assertIn("Lerd ou Valet", data["error"])


class AdicionarComLerdTest(ServerTestCase):
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
        self.pasta = self.tmp / "Loja"
        self.pasta.mkdir()

    def test_linkar(self):
        status, data, _ = self.request("POST", "/api/sites", body={"kind": "link", "path": str(self.pasta), "domain": "loja"})
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])
        call = self.fake.calls[-1]
        self.assertEqual(list(call.argv)[1:], ["link", "loja"])
        self.assertEqual(call.cwd, str(self.pasta))

    def test_parkear(self):
        status, data, _ = self.request("POST", "/api/sites", body={"kind": "park", "path": str(self.tmp)})
        self.assertEqual(status, 200, data)
        self.assertEqual(list(self.fake.calls[-1].argv)[1:], ["park", str(self.tmp)])

    def test_entradas_invalidas(self):
        casos = [({"kind": "link", "path": str(self.tmp / "nao-existe"), "domain": "loja"}, 400),
                 ({"kind": "link", "path": str(self.pasta), "domain": "Loja"}, 400),
                 ({"kind": "outro", "path": str(self.pasta)}, 400),
                 ({"kind": "link", "path": "relativa", "domain": "loja"}, 400)]
        for body, expected in casos:
            with self.subTest(body=body):
                status, data, _ = self.request("POST", "/api/sites", body=body)
                self.assertEqual(status, expected, data)
        self.assertEqual(self.fake.calls, [])
        status, data, _ = self.request("POST", "/api/sites", body={"kind": "link", "path": str(self.pasta), "domain": "Loja"})
        self.assertEqual(data["suggestion"], "loja")

    def test_falha_do_lerd_volta_com_a_saida(self):
        from vulcan_celox.core.runner import Result
        self.fake.default = Result(1, "", "a pasta não parece um projeto PHP")
        status, data, _ = self.request("POST", "/api/sites", body={"kind": "link", "path": str(self.pasta), "domain": "loja"})
        self.assertEqual(status, 200)
        self.assertFalse(data["ok"])
        self.assertIn("projeto PHP", data["output"])

    def test_sugestao(self):
        data = self.request("GET", f"/api/sites/suggest?path={self.pasta}")[1]
        self.assertEqual(data["domain"], "loja")
