"""vt-21 C2: a API falsa do Lerd que o sensor usa responde como o Lerd e nunca sai do 127.0.0.1."""

import json
import threading
import urllib.error
import urllib.request

from tests.helpers import TempDirTestCase
from tests.tools.fake_lerd_api import make_server


class FakeLerdTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.server = make_server({"loja": "/x/projeto"}, "2026-10-31T01:10")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return json.loads(r.read())

    def post(self, path, headers):
        req = urllib.request.Request(self.base + path, data=b"{}", method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as err:
            return err.code

    def test_so_loopback(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_csrf_como_o_lerd(self):
        self.assertEqual(self.post("/api/dumps/clear", {"Content-Type": "application/json"}), 403)
        self.assertEqual(self.post("/api/dumps/clear", {"Content-Type": "application/json", "X-Lerd-CSRF": "1"}), 200)

    def test_fixtures_e_ajustes(self):
        sites = {s["name"]: s["path"] for s in self.get("/api/sites")}
        self.assertEqual(sites["loja"], "/x/projeto")
        dumps = self.get("/api/dumps?site=loja")
        self.assertTrue(dumps and all(e["ts"].startswith("2026-10-31T01:10") for e in dumps))
        self.assertTrue(self.get("/api/dumps/status")["enabled"])
        self.assertIn("php_fpms", self.get("/api/status"))
