"""Lerd environment state (DNS, nginx, PHP-FPM, watcher, services) and actions on the services.

`lerd-api-status.json` is a real Lerd response. `lerd-api-services-montada.json` was assembled with the fields that the
Lerd 1.37.1 dashboard itself reads from /api/services (name, status "active", version, pinned, connection_url...),
because no service is installed on this machine and installing one would download large images.
"""

import json
import os
from unittest import mock

from tests.helpers import FIXTURES
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.environment import lerd_components, lerd_services


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ParserTest(ServerTestCase):
    def test_componentes(self):
        comps = {c["id"]: c for c in lerd_components(fixture("lerd-api-status.json"))}
        self.assertTrue(comps["dns"]["ok"])
        self.assertIn("php-8.5", comps)
        self.assertIn("8.5", comps["php-8.5"]["label"])
        self.assertIn("watcher", comps)
        self.assertEqual(lerd_components(None), [])

    def test_servicos(self):
        services = lerd_services(fixture("lerd-api-services-montada.json"))
        self.assertEqual([(s["name"], s["active"]) for s in services], [("mysql", True), ("redis", False)])
        self.assertEqual(services[0]["version"], "8.4")
        self.assertEqual(lerd_services([{"sem": "nome"}, "lixo"]), [])


class ApiTest(ServerTestCase):
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
        answers = {"/api/status": fixture("lerd-api-status.json"), "/api/services": fixture("lerd-api-services-montada.json"),
                   "/api/sites": []}
        self.patch = mock.patch.object(self.app.backend, "api_get", side_effect=lambda p, **k: answers.get(p))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        super().tearDown()

    def test_estado(self):
        data = self.request("GET", "/api/environment")[1]
        self.assertEqual(data["backend"], "lerd")
        self.assertTrue(any(c["id"] == "nginx" for c in data["components"]))
        self.assertEqual([s["name"] for s in data["services"]], ["mysql", "redis"])

    def test_acoes_nos_servicos(self):
        for action in ("start", "stop", "restart"):
            with self.subTest(action=action):
                status, data, _ = self.request("POST", f"/api/environment/services/redis/{action}")
                self.assertEqual(status, 200, data)
                self.assertEqual(list(self.fake.calls[-1].argv)[1:], ["service", action, "redis"])
        self.assertEqual(self.request("POST", "/api/environment/services/postgres/start")[0], 404)
        self.assertEqual(self.request("POST", "/api/environment/services/redis/remove")[0], 404)


class CacheTest(ApiTest):
    """The Environment screen refreshes every 15 s; php:list and xdebug status are cached for 60 s."""

    def tearDown(self):
        self.app.terminals.close_all()
        super().tearDown()

    def cli(self, *args):
        return sum(1 for c in self.fake.calls if list(c.argv)[1:1 + len(args)] == list(args))

    def test_dois_gets_um_subprocesso(self):
        from vulcan_celox.core.runner import Result
        self.fake.default = Result(0, "Installed PHP versions:\n* 8.5\n")
        for _ in range(3):
            self.assertEqual(self.request("GET", "/api/environment/php")[0], 200)
            self.assertEqual(self.request("GET", "/api/environment/xdebug")[0], 200)
        self.assertEqual(self.cli("php:list"), 1)
        self.assertEqual(self.cli("xdebug", "status"), 1)

    def test_post_forca_releitura(self):
        from vulcan_celox.core.runner import Result
        self.fake.default = Result(0, "Installed PHP versions:\n* 8.5\n")
        self.request("GET", "/api/environment/php")
        self.request("GET", "/api/environment/xdebug")
        status, info, _ = self.request("POST", "/api/environment/php/8.5/xdebug", {"enabled": False})
        self.assertEqual(status, 201, info)
        before_list, before_xd = self.cli("php:list"), self.cli("xdebug", "status")
        self.request("GET", "/api/environment/php")
        self.request("GET", "/api/environment/xdebug")
        self.assertEqual(self.cli("php:list"), before_list + 1)
        self.assertEqual(self.cli("xdebug", "status"), before_xd + 1)

    def test_prazo_de_60_s(self):
        from vulcan_celox.core.runner import Result
        self.fake.default = Result(0, "Installed PHP versions:\n* 8.5\n")
        with mock.patch("vulcan_celox.server.env_api._now", side_effect=[1000.0, 1061.0]):
            self.request("GET", "/api/environment/php")
            self.request("GET", "/api/environment/php")
        self.assertEqual(self.cli("php:list"), 2)

class SemBackendTest(ServerTestCase):
    def test_vazio(self):
        data = self.request("GET", "/api/environment")[1]
        self.assertEqual((data["backend"], data["services"]), ("local", []))
        self.assertEqual(self.request("POST", "/api/environment/services/redis/start")[0], 409)
