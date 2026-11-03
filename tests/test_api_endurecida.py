"""API endurecida."""

import http.client
import json
import os
import socket

from tests import test_agents_api
from tests.server_helpers import ServerTestCase
from tests.test_pty import wait_for
from tests.test_websocket import RawClient
from vulcan_celox.server.app import VulcanApp
from vulcan_celox.server.websocket import OP_TEXT


class TokenEOrigemTest(ServerTestCase):
    def raw(self, method, path, headers, body=b""):
        conn = http.client.HTTPConnection("127.0.0.1", self.app.server.port, timeout=10)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", f"127.0.0.1:{self.app.server.port}")
        for name, value in headers.items():
            conn.putheader(name, value)
        conn.endheaders(body or None)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        return resp.status, raw

    def test_requisicao_simples_da_auditoria_nao_abre_terminal(self):
        marker = self.tmp / "invadido"
        body = json.dumps({"command": f"touch {marker}"}).encode()
        # token na query e text/plain: o navegador mandaria sem preflight
        status, _ = self.raw("POST", f"/api/terminals?token={self.token}",
                             {"Content-Type": "text/plain", "Content-Length": str(len(body))}, body)
        self.assertEqual(status, 401)
        # mesmo com o token no cabeçalho, corpo que não é JSON é recusado
        status, _ = self.raw("POST", "/api/terminals", {"X-Vulcan-Token": self.token, "Content-Type": "text/plain",
                                                        "Content-Length": str(len(body))}, body)
        self.assertEqual(status, 415)
        self.assertEqual(self.app.terminals.list(), [])
        self.assertFalse(marker.exists())

    def test_tamanho_do_terminal_fora_do_limite(self):
        """Rows/cols fora de 1 a 1000 dão 400 antes de abrir processo."""
        for bad in ({"rows": 70000, "cols": 80}, {"rows": 24, "cols": -3}, {"rows": "x", "cols": 80}):
            with self.subTest(bad=bad):
                status, _, _ = self.request("POST", "/api/terminals", {"cwd": str(self.tmp), **bad})
                self.assertEqual(status, 400)
        self.assertEqual(self.app.terminals.list(), [])

    def test_token_na_query_so_no_websocket(self):
        self.assertEqual(self.request("GET", f"/api/state?token={self.token}", token=False)[0], 401)
        status, info, _ = self.request("POST", "/api/terminals", body={})
        self.assertEqual(status, 201)
        try:
            client = RawClient(self.app.server.port, f"/ws/terminals/{info['id']}?token={self.token}")
            self.assertEqual(client.status, 101)
            client.close()
        finally:
            self.app.terminals.close_all()

    def test_escrita_sem_json(self):
        status, _ = self.raw("POST", "/api/tasks/undo", {"X-Vulcan-Token": self.token, "Content-Length": "0"})
        self.assertEqual(status, 415)
        status, _ = self.raw("POST", "/api/tasks/undo", {"X-Vulcan-Token": self.token, "Content-Length": "0",
                                                         "Content-Type": "application/json; charset=utf-8"})
        self.assertNotEqual(status, 415)
        self.assertEqual(self.request("DELETE", "/api/tags/abc999")[0], 404)  # DELETE sem corpo segue valendo

    def test_origem(self):
        port = self.app.server.port
        evil = self.request("GET", "/api/state", headers={"Origin": "https://evil.example"})[0]
        self.assertEqual(evil, 403)
        self.assertEqual(self.request("GET", "/api/state", headers={"Origin": "null"})[0], 403)
        self.assertEqual(self.request("GET", "/api/state", headers={"Origin": f"http://127.0.0.1:{port}"})[0], 200)
        self.assertEqual(self.request("GET", "/api/state", headers={"Origin": f"http://localhost:{port}"})[0], 200)

    def test_content_length_invalido(self):
        for value in ("-1", "abc"):
            with self.subTest(value=value):
                sock = socket.create_connection(("127.0.0.1", self.app.server.port), timeout=5)
                sock.sendall((f"POST /api/tasks HTTP/1.1\r\nHost: 127.0.0.1:{self.app.server.port}\r\n"
                              f"X-Vulcan-Token: {self.token}\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {value}\r\n\r\n").encode())
                first = sock.recv(64)
                sock.close()
                self.assertTrue(first.startswith(b"HTTP/1.0 400") or first.startswith(b"HTTP/1.1 400"), first)

    def test_open_restrito(self):
        bundle = self.tmp / "Calc.app"
        bundle.mkdir()
        self.assertEqual(self.request("POST", "/api/open", body={"kind": "finder", "target": str(bundle)})[0], 400)
        data = self.app.data_dir
        os.makedirs(data, exist_ok=True)
        script = os.path.join(data, "algo.py")
        with open(script, "w") as fh:
            fh.write("print(1)")
        self.assertEqual(self.request("POST", "/api/open", body={"kind": "file", "target": script})[0], 400)


class ResizeTest(ServerTestCase):
    def env(self):
        env = super().env()
        env["SHELL"] = "/bin/sh"
        env["PATH"] = os.environ.get("PATH", "")
        return env

    def tearDown(self):
        self.app.terminals.close_all()
        super().tearDown()

    def test_resize_invalido_mantem_a_conexao(self):
        status, info, _ = self.request("POST", "/api/terminals", body={})
        self.assertEqual(status, 201)
        client = RawClient(self.app.server.port, f"/ws/terminals/{info['id']}?token={self.token}")
        try:
            for bad in ({"type": "resize", "rows": "x", "cols": 80}, {"type": "resize", "rows": 70000, "cols": 80},
                        {"type": "resize", "rows": 0, "cols": -3}):
                client.send(json.dumps(bad).encode(), OP_TEXT)
            client.send(json.dumps({"type": "resize", "rows": 30, "cols": 100}).encode(), OP_TEXT)
            client.send(b"echo vivo-$((40+2))\n")
            self.assertIn(b"vivo-42", client.read_until(b"vivo-42"))
            pty = self.app.terminals.get(info["id"])
            self.assertTrue(wait_for(lambda: (pty.rows, pty.cols) == (30, 100)), (pty.rows, pty.cols))
        finally:
            client.close()


class IdDeSessaoTest(test_agents_api.AgentsServerCase):
    def test_id_com_hifen_no_inicio(self):
        self.assertEqual(self.request("POST", "/api/agents/sessions/-x/resume", body={})[0], 404)
        self.assertEqual(self.request("GET", "/api/agents/sessions/--help")[0], 404)


class AmbienteTest(ServerTestCase):
    def test_token_curto_do_ambiente(self):
        env = dict(self.env(), VULCAN_TOKEN="curto")
        with self.assertRaises(ValueError):
            VulcanApp(env=env, runner=self.fake)

    def test_base_da_anthropic(self):
        ai = self.app.ai
        for base, ok in (("https://proxy.empresa.com", True), ("http://127.0.0.1:9999", True),
                         ("http://localhost:9999", True), ("http://proxy.empresa.com", False)):
            with self.subTest(base=base):
                self.app.env["VULCAN_ANTHROPIC_BASE_URL"] = base
                if ok:
                    self.assertEqual(ai.base(), base)
                else:
                    with self.assertRaises(Exception):
                        ai.base()
