import base64
import io
import json
import os
import socket
import time
import unittest

from tests.server_helpers import ServerTestCase
from vulcan_terminal.server.websocket import (OP_BINARY, OP_CLOSE, OP_TEXT, accept_key, encode_frame,
                                              read_frame)


class FrameTest(unittest.TestCase):
    def test_chave_do_rfc(self):
        self.assertEqual(accept_key("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

    def test_roundtrip_tamanhos_e_mascara(self):
        for size in (0, 5, 125, 126, 200, 65535, 65536, 70000):
            payload = os.urandom(size)
            for mask in (False, True):
                frame = encode_frame(payload, OP_BINARY, mask=mask)
                fin, opcode, data = read_frame(io.BytesIO(frame))
                self.assertEqual((fin, opcode, data), (True, OP_BINARY, payload), (size, mask))

    def test_cabecalho_estendido(self):
        self.assertEqual(encode_frame(b"x" * 126)[1], 126)
        self.assertEqual(encode_frame(b"x" * 65536)[1], 127)


class RawClient:
    def __init__(self, port, path):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\n"
                   f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                   f"Origin: http://127.0.0.1:{port}\r\n\r\n")
        self.sock.sendall(request.encode())
        self.stream = self.sock.makefile("rb")
        status = self.stream.readline()
        self.headers = {}
        while True:
            line = self.stream.readline().decode().strip()
            if not line:
                break
            name, _, value = line.partition(":")
            self.headers[name.lower()] = value.strip()
        self.status = int(status.split()[1])
        self.expected_accept = accept_key(key)

    def send(self, data: bytes, opcode=OP_BINARY):
        self.sock.sendall(encode_frame(data, opcode, mask=True))

    def read_until(self, needle: bytes, timeout=8.0):
        buf = b""
        deadline = time.monotonic() + timeout
        self.sock.settimeout(timeout)
        while needle not in buf and time.monotonic() < deadline:
            fin, opcode, data = read_frame(self.stream)
            if opcode == OP_BINARY:
                buf += data
            elif opcode == OP_TEXT:
                buf += b"[text]" + data
        return buf

    def close(self):
        try:
            self.sock.sendall(encode_frame(b"", OP_CLOSE, mask=True))
        finally:
            self.sock.close()


class WebSocketIntegrationTest(ServerTestCase):
    def env(self):
        env = super().env()
        env["SHELL"] = "/bin/sh"
        env["PATH"] = os.environ.get("PATH", "")
        return env

    def test_terminal_completo(self):
        status, info, _ = self.request("POST", "/api/terminals", body={"cwd": str(self.tmp), "title": "teste"})
        self.assertEqual(status, 201)
        self.assertEqual(self.request("GET", "/api/terminals")[1]["terminals"][0]["title"], "teste")

        client = RawClient(self.app.server.port, f"/ws/terminals/{info['id']}?token={self.token}")
        self.assertEqual(client.status, 101)
        self.assertEqual(client.headers["sec-websocket-accept"], client.expected_accept)
        client.send(json.dumps({"type": "resize", "rows": 40, "cols": 120}).encode(), OP_TEXT)
        client.send(b"echo vulcan$((1+1)); stty size\n")
        out = client.read_until(b"40 120")
        self.assertIn(b"vulcan2", out)
        client.close()

        # reconexão recebe o histórico
        again = RawClient(self.app.server.port, f"/ws/terminals/{info['id']}?token={self.token}")
        self.assertIn(b"vulcan2", again.read_until(b"vulcan2"))
        again.send(b"exit\n")
        self.assertIn(b'"type": "exit"', again.read_until(b'"type": "exit"'))
        again.sock.close()

        self.assertEqual(self.request("PATCH", f"/api/terminals/{info['id']}", body={"title": "novo"})[1]["title"],
                         "novo")
        self.assertEqual(self.request("DELETE", f"/api/terminals/{info['id']}")[0], 200)
        self.assertEqual(self.request("DELETE", f"/api/terminals/{info['id']}")[0], 404)

    def test_ws_sem_token_e_origem_estranha(self):
        info = self.request("POST", "/api/terminals", body={"cwd": str(self.tmp)})[1]
        sem_token = RawClient(self.app.server.port, f"/ws/terminals/{info['id']}")
        self.assertEqual(sem_token.status, 401)
        sem_token.sock.close()
        sock = socket.create_connection(("127.0.0.1", self.app.server.port), timeout=5)
        port = self.app.server.port
        sock.sendall((f"GET /ws/terminals/{info['id']}?token={self.token} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                      "Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: eA==\r\n"
                      "Sec-WebSocket-Version: 13\r\nOrigin: https://evil.example\r\n\r\n").encode())
        self.assertIn(b" 403 ", sock.recv(200))  # vt-20 C3: origem estranha cai antes do upgrade
        sock.close()

    def test_criar_com_pasta_invalida_e_site_inexistente(self):
        self.assertEqual(self.request("POST", "/api/terminals", body={"cwd": "/nao/existe"})[0], 400)
        self.assertEqual(self.request("POST", "/api/terminals", body={"site": "fantasma"})[0], 404)
