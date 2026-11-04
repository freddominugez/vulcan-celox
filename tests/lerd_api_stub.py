"""Local HTTP test server that imitates the Lerd dashboard API."""

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.helpers import FIXTURES

ROUTES = {"/api/sites": "lerd-api-sites.json", "/api/status": "lerd-api-status.json"}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        name = ROUTES.get(self.path)
        if name is None:
            self.send_response(404)
            self.end_headers()
            return
        body = (FIXTURES / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class LerdApiStub:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()


def closed_port_url() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}"
