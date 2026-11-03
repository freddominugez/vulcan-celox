"""Node pelo Lerd (padrão, gerenciador, instaladas; instalar, tornar padrão e remover).

As instaladas vêm de GET /api/node-versions, a rota que o painel do Lerd 1.37.1 usa; nesta máquina ela respondeu
["24","26"], o mesmo que `mise ls node`.
"""

import os
from unittest import mock

from tests.server_helpers import ServerTestCase


class NodeApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        self.lerd = lerd
        env.update({"VULCAN_LERD_BIN": str(lerd), "SHELL": "/bin/sh", "PATH": os.environ.get("PATH", "")})
        return env

    def setUp(self):
        super().setUp()
        answers = {"/api/status": {"node_default": "22", "node_manager": "mise"}, "/api/node-versions": ["24", "26"]}
        self.patch = mock.patch.object(self.app.backend, "api_get", side_effect=lambda p, **k: answers.get(p))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.app.terminals.close_all()
        super().tearDown()

    def test_estado(self):
        data = self.request("GET", "/api/environment/node")[1]
        self.assertEqual(data, {"default": "22", "manager": "mise", "installed": ["24", "26"]})

    def test_acoes(self):
        status, info, _ = self.request("POST", "/api/environment/node/20/install")
        self.assertEqual(status, 201, info)
        self.assertIn(f"{self.lerd} node:install 20", " ".join(self.app.terminals.get(info["id"]).argv))
        status, data, _ = self.request("POST", "/api/environment/node/24/use")
        self.assertEqual((status, list(self.fake.calls[-1].argv)[1:]), (200, ["node:use", "24"]))

    def test_versoes(self):
        for good in ("20", "22.11.0", "lts"):
            with self.subTest(good=good):
                self.assertIn(self.request("POST", f"/api/environment/node/{good}/use")[0], (200,))
        self.assertEqual(self.request("POST", "/api/environment/node/abc/use")[0], 400)

    def test_remover_so_com_confirmacao(self):
        before = len(self.fake.calls)
        self.assertEqual(self.request("POST", "/api/environment/node/24/remove")[0], 400)
        self.assertEqual(len([c for c in self.fake.calls[before:] if "node:uninstall" in c.argv]), 0)
        status, data, _ = self.request("POST", "/api/environment/node/24/remove", body={"confirm": True})
        self.assertEqual((status, list(self.fake.calls[-1].argv)[1:]), (200, ["node:uninstall", "24"]))
