from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_celox.server.local_http import LocalServer


class BuildIdTest(TempDirTestCase):
    def test_build_muda_quando_a_interface_em_disco_muda(self):
        web = self.tmp / "web"
        web.mkdir()
        (web / "index.html").write_text("<html>v1", encoding="utf-8")
        server = LocalServer(web_root=web)
        try:
            self.assertEqual(server.build_id, server.disk_build_id())
            (web / "index.html").write_text("<html>v2", encoding="utf-8")
            self.assertNotEqual(server.build_id, server.disk_build_id())
        finally:
            server.httpd.server_close()


class BuildApiTest(ServerTestCase):
    def test_rota(self):
        data = self.request("GET", "/api/app/build")[1]
        self.assertEqual((data["outdated"], data["loaded"]), (False, data["installed"]))
        self.assertTrue(data["version"])
