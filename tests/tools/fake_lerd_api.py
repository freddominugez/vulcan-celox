"""API falsa do Lerd para o sensor (vt-21 C2): responde como a do Lerd 1.37.1 com as fixtures reais de tests/fixtures.

Só stdlib, só 127.0.0.1, porta escolhida pelo sistema (impressa na primeira linha). POST exige `X-Lerd-CSRF: 1`,
como o Lerd. Nunca fala com o Lerd de verdade.

uso: python3 -I tests/tools/fake_lerd_api.py [--site-path nome=pasta] [--dumps-at AAAA-MM-DDTHH:MM] [--sites-alternam S]

--sites-alternam S: a cada S segundos um site extra aparece ou some da lista (vt-29 C4: a tela não pode perder o
texto digitado quando a lista de sites muda).
"""

import argparse
import http.server
import json
import sys
import time
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FILES = {"/api/status": "lerd-api-status.json", "/api/sites": "lerd-api-sites.json",
         "/api/services": "lerd-api-services-montada.json", "/api/dumps": "lerd-api-dumps.json"}


def build(site_paths, dumps_at):
    data = {route: json.loads((FIXTURES / name).read_text(encoding="utf-8")) for route, name in FILES.items()}
    for site in data["/api/sites"]:
        if site.get("name") in site_paths:
            site["path"] = site_paths[site["name"]]
    if dumps_at:  # põe os eventos dentro da janela de uma sessão de agente das fixtures
        for event in data["/api/dumps"]:
            event["ts"] = dumps_at + event["ts"][16:]
    data["/api/dumps/status"] = {"enabled": True, "listening": True, "addr": "tcp:127.0.0.1:9913",
                                 "count": len(data["/api/dumps"]), "capacity": 5000}
    data["/api/node-versions"] = [str(data["/api/status"].get("node_default") or "22")]
    return data


def make_server(site_paths=None, dumps_at="", sites_alternam=0.0):
    data = build(site_paths or {}, dumps_at)
    extra = dict(data["/api/sites"][0], name="alterna", domain="alterna.test", path="/Users/dev/alterna") \
        if data["/api/sites"] else None

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, payload=None):
            body = json.dumps(payload).encode() if payload is not None else b""
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            route = self.path.split("?", 1)[0]
            if route == "/api/sites" and sites_alternam and extra and int(time.time() / sites_alternam) % 2:
                return self.send(200, data[route] + [extra])
            if route in data:
                return self.send(200, data[route])
            self.send(404, {"error": "not found"})

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if self.headers.get("X-Lerd-CSRF") != "1":
                return self.send(403, {"error": "csrf"})
            self.send(200, {})

    return http.server.HTTPServer(("127.0.0.1", 0), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-path", action="append", default=[])
    parser.add_argument("--dumps-at", default="")
    parser.add_argument("--sites-alternam", type=float, default=0.0)
    args = parser.parse_args(argv)
    server = make_server(dict(item.split("=", 1) for item in args.site_path), args.dumps_at, args.sites_alternam)
    print(server.server_port, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
