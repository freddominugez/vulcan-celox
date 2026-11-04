from tests.server_helpers import ServerTestCase


class ServerSecurityTest(ServerTestCase):
    def test_sem_token(self):
        status, data, _ = self.request("GET", "/api/state", token=False)
        self.assertEqual(status, 401)
        self.assertIn("token", data["error"])

    def test_token_errado(self):
        self.assertEqual(self.request("GET", "/api/state", token="outro")[0], 401)

    def test_token_na_query(self):
        # in the API the token comes only through the header; the query is valid only on the WebSocket (test_api_endurecida)
        self.assertEqual(self.request("GET", f"/api/state?token={self.token}", token=False)[0], 401)

    def test_host_estranho(self):
        self.assertEqual(self.request("GET", "/api/state", host="evil.example")[0], 421)
        self.assertEqual(self.request("GET", "/", host=f"192.168.0.10:{self.app.server.port}")[0], 421)
        self.assertEqual(self.request("GET", "/api/state", host=f"localhost:{self.app.server.port}")[0], 200)

    def test_path_traversal(self):
        for path in ("/../core/store.py", "/%2e%2e/core/store.py", "/vendor/../../core/store.py"):
            self.assertEqual(self.request("GET", path, token=False)[0], 404, path)

    def test_estaticos(self):
        status, body, resp = self.request("GET", "/", token=False)
        self.assertEqual(status, 200)
        self.assertTrue(resp.getheader("Content-Type").startswith("text/html"))
        self.assertIn("default-src 'self'", resp.getheader("Content-Security-Policy"))
        self.assertIn(b"<html", body)
        status, _, resp = self.request("GET", "/vendor/xterm.js", token=False)
        self.assertEqual((status, resp.getheader("Content-Type")), (200, "text/javascript; charset=utf-8"))

    def test_interface_lida_na_abertura(self):
        from vulcan_celox.server.local_http import LocalServer
        web = self.tmp / "web"
        (web / "js").mkdir(parents=True)
        (web / "index.html").write_text("<html>v1", encoding="utf-8")
        (web / "js" / "app.mjs").write_text("// v1", encoding="utf-8")
        (web / ".DS_Store").write_text("x", encoding="utf-8")
        server = LocalServer(web_root=web)
        try:
            (web / "index.html").write_text("<html>v2", encoding="utf-8")
            self.assertEqual(server.assets["index.html"], b"<html>v1")
            self.assertEqual(sorted(server.assets), ["index.html", "js/app.mjs"])
        finally:
            server.httpd.server_close()

    def test_rota_inexistente_e_metodo(self):
        self.assertEqual(self.request("GET", "/api/nada")[0], 404)
        self.assertEqual(self.request("DELETE", "/api/state")[0], 405)


class ServerRoutesTest(ServerTestCase):
    def test_state(self):
        status, data, _ = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(data["backend"]["name"], "local")
        self.assertEqual(data["sites"], [])
        self.assertIn("summary", data["status"])
        self.assertEqual(data["progress"]["overall"]["label"], "sem tarefas")

    def test_site_manual_com_flags(self):
        projeto = self.tmp / "loja"
        projeto.mkdir()
        (projeto / "artisan").write_text("", encoding="utf-8")
        self.app.store.save("sites", {"loja": str(projeto)})
        site = self.request("GET", "/api/state")[1]["sites"][0]
        self.assertEqual((site["name"], site["has_artisan"], site["exists"], site["url"]),
                         ("loja", True, True, "http://loja.test"))

    def test_servico_sem_backend(self):
        self.assertEqual(self.request("POST", "/api/services/start", body={})[0], 409)
        self.assertEqual(self.request("POST", "/api/services/explodir", body={})[0], 404)

    def test_servico_com_backend(self):
        from vulcan_celox.core.backends.base import EnvStatus
        from vulcan_celox.core.backends.lerd import LerdBackend
        self.app.backend = LerdBackend(self.tmp / "lerd", runner=self.fake, api_base="http://127.0.0.1:1")
        # the command finished, but nothing answers: that is reported, without blaming a progress line
        status, data, _ = self.request("POST", "/api/services/restart", body={})
        self.assertEqual((status, data["ok"]), (200, False))
        self.assertIn("não respondeu", data["output"])
        self.assertEqual([c.argv[-1] for c in self.fake.calls if c.argv[-1] != "--version"], ["stop", "start"])  # asking the version is a read
        self.app.backend.status = lambda: EnvStatus(True, "")
        self.assertEqual(self.request("POST", "/api/services/start", body={})[1]["ok"], True)

    def test_open(self):
        self.assertEqual(self.request("POST", "/api/open", body={"kind": "url", "target": "file:///etc"})[0], 400)
        self.assertEqual(self.request("POST", "/api/open", body={"kind": "finder", "target": "/nao/existe"})[0], 400)
        status, _, _ = self.request("POST", "/api/open", body={"kind": "url", "target": "http://loja.test"})
        self.assertEqual(status, 200)
        from vulcan_celox.core.oscompat import open_argv
        self.assertEqual(list(self.fake.calls[-1].argv), open_argv("url", "http://loja.test", self.app.env))
        self.assertEqual(self.request("POST", "/api/open", body={"kind": "dashboard"})[0], 409)

    def test_json_invalido(self):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.app.server.port, timeout=10)
        conn.request("POST", "/api/open", body="{x", headers={"Host": f"127.0.0.1:{self.app.server.port}",
                                                             "X-Vulcan-Token": self.token,
                                                             "Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 400)


class KeepAliveBodyTest(ServerTestCase):
    def test_corpo_nao_lido_nao_corrompe_proxima_requisicao(self):
        import http.client
        import json as _json

        @self.app.server.route("POST", "/api/teste/ignora-corpo")
        def _ignora(_req):
            return 202, {"ok": True}

        conn = http.client.HTTPConnection("127.0.0.1", self.app.server.port, timeout=5)
        headers = {"Host": f"127.0.0.1:{self.app.server.port}", "X-Vulcan-Token": self.token,
                   "Content-Type": "application/json"}
        conn.request("POST", "/api/teste/ignora-corpo", body=_json.dumps({"x": 1}), headers=headers)
        first = conn.getresponse()
        first.read()
        self.assertEqual(first.status, 202)
        conn.request("GET", "/api/state", headers=headers)
        second = conn.getresponse()
        second.read()
        self.assertEqual(second.status, 200)
        conn.request("POST", "/api/nada", body="{}", headers=headers)
        third = conn.getresponse()
        third.read()
        conn.request("GET", "/api/state", headers=headers)
        self.assertEqual(conn.getresponse().status, 200)
        conn.close()
